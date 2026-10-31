"""Offline candidate-forecast validation with equal, explicit observation windows."""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
from statistics import mean
import tempfile
from typing import Iterable

from .adapter import ReleaseAdapter
from .models import VIETNAM, aware, nonempty, parse_instant, probability, utc_iso
from .replay import ReleaseReader, ReplaySnapshot, TERMINAL


ROOT = Path(__file__).resolve().parents[1]
MODEL = "kaplan_meier_carrier_service_stage_v1"


@dataclass(frozen=True, slots=True)
class ForecastCase:
    order_id: str
    tick_at: datetime
    guaranteed_date: date
    carrier_id: str
    service_level: str
    stage: str
    late_probability: float | None
    revised_eta: datetime | None
    cohort_id: str | None

    def __post_init__(self) -> None:
        for name in ("order_id", "carrier_id", "service_level", "stage"):
            nonempty(getattr(self, name), name)
        aware(self.tick_at, "tick_at")
        if type(self.guaranteed_date) is not date:
            raise ValueError("guaranteed_date must be a date")
        if self.late_probability is not None:
            probability(self.late_probability, "late_probability")
            nonempty(self.cohort_id, "cohort_id")
        elif self.revised_eta is not None or self.cohort_id is not None:
            raise ValueError("a missing forecast cannot have ETA or cohort metadata")
        if self.revised_eta is not None:
            if aware(self.revised_eta, "revised_eta") < self.tick_at:
                raise ValueError("forecast ETA cannot precede prediction tick")


@dataclass(frozen=True, slots=True)
class Outcome:
    delivered_at: datetime | None = None
    terminal_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("delivered_at", "terminal_at"):
            value = getattr(self, name)
            if value is not None:
                aware(value, name)


def _window(hours: int) -> timedelta:
    if type(hours) is not int or hours <= 0:
        raise ValueError("followup_hours must be a positive integer")
    try:
        return timedelta(hours=hours)
    except OverflowError as error:
        raise ValueError("followup_hours is too large") from error


def _average(values: list[float]) -> float | None:
    return mean(values) if values else None


def _outcome_kind(outcome: Outcome, tick: datetime, cutoff: datetime) -> str:
    if any(value is not None and value > cutoff for value in (outcome.delivered_at, outcome.terminal_at)):
        raise ValueError("outcome exceeds its follow-up cutoff")
    if outcome.terminal_at is not None and (
        outcome.delivered_at is None or outcome.terminal_at <= outcome.delivered_at
    ):
        return "terminal_before_delivery"
    if outcome.delivered_at is None:
        return "unobserved"
    return "delivery_already_happened" if outcome.delivered_at <= tick else "delivered"


def summarize(
    cases: Iterable[ForecastCase], outcomes: dict[tuple[datetime, str], Outcome], *,
    followup_hours: int,
) -> dict:
    """Score explicit labels; absence of a delivery is never a lateness label."""
    window = _window(followup_hours)
    cases = tuple(cases)
    keys = {(row.tick_at, row.order_id) for row in cases}
    if len(keys) != len(cases):
        raise ValueError("duplicate forecast observation")
    forecasts = [row for row in cases if row.late_probability is not None]
    outcome_counts, risk_exclusions = Counter(), Counter()
    eta_errors, labels, losses, unknown_probabilities = [], [], [], []
    bins = [dict(lower=i / 5, upper=(i + 1) / 5, known=[], predicted=[], unknown=0) for i in range(5)]
    for row in forecasts:
        cutoff = row.tick_at + window
        outcome = outcomes.get((row.tick_at, row.order_id), Outcome())
        kind = _outcome_kind(outcome, row.tick_at, cutoff)
        outcome_counts[kind] += 1
        if kind == "delivered" and row.revised_eta is not None:
            eta_errors.append((row.revised_eta - outcome.delivered_at).total_seconds() / 3600)

        deadline = datetime.combine(row.guaranteed_date + timedelta(days=1), time.min, VIETNAM)
        if row.tick_at >= deadline:
            risk_exclusions["already_late_at_prediction"] += 1
        elif deadline > cutoff:
            # Do not include only early successes from a still-immature cohort.
            risk_exclusions["deadline_after_followup"] += 1
        elif kind in ("terminal_before_delivery", "delivery_already_happened"):
            risk_exclusions[kind] += 1
        else:
            predicted = row.late_probability
            bucket = bins[min(4, int(predicted * 5))]
            if kind == "unobserved":
                unknown_probabilities.append(predicted)
                bucket["unknown"] += 1
            else:
                label = int(outcome.delivered_at >= deadline)
                labels.append(label)
                losses.append((predicted - label) ** 2)
                bucket["known"].append(label)
                bucket["predicted"].append(predicted)

    risk_total = len(labels) + len(unknown_probabilities)
    lower_loss = sum(losses) + sum(min(p ** 2, (1 - p) ** 2) for p in unknown_probabilities)
    upper_loss = sum(losses) + sum(max(p ** 2, (1 - p) ** 2) for p in unknown_probabilities)
    return dict(
        active_observations=len(cases), distinct_orders=len({row.order_id for row in cases}),
        distinct_forecast_orders=len({row.order_id for row in forecasts}),
        forecast_count=len(forecasts), no_forecast_count=len(cases) - len(forecasts),
        forecast_coverage=len(forecasts) / len(cases) if cases else None,
        eta_available=sum(row.revised_eta is not None for row in forecasts),
        outcome_counts=dict(sorted(outcome_counts.items())),
        eta_scored=len(eta_errors), eta_mae_hours=_average([abs(value) for value in eta_errors]),
        eta_bias_hours=_average(eta_errors),
        eta_within_24h_fraction=_average([int(abs(value) <= 24) for value in eta_errors]),
        risk_exclusion_counts=dict(sorted(risk_exclusions.items())),
        risk_known_labels=len(labels), risk_unknown_labels=len(unknown_probabilities),
        risk_label_coverage=len(labels) / risk_total if risk_total else None,
        observed_late_fraction=_average(labels),
        lateness_brier_complete_case=_average(losses),
        always_on_time_brier_complete_case=_average(labels),
        lateness_brier_lower_bound=lower_loss / risk_total if risk_total else None,
        lateness_brier_upper_bound=upper_loss / risk_total if risk_total else None,
        always_on_time_brier_lower_bound=sum(labels) / risk_total if risk_total else None,
        always_on_time_brier_upper_bound=(sum(labels) + len(unknown_probabilities)) / risk_total if risk_total else None,
        calibration_bins=[dict(
            lower=b["lower"], upper=b["upper"], known_labels=len(b["known"]), unknown_labels=b["unknown"],
            mean_prediction_complete_case=_average(b["predicted"]), observed_late_fraction=_average(b["known"]),
        ) for b in bins],
    )


def predict_snapshot(snapshot: ReplaySnapshot) -> tuple[ForecastCase, ...]:
    """Freeze candidate forecasts; no outcome snapshot or A3 authority is supplied."""
    source_orders = {row["order_id"]: row for row in snapshot.orders}
    cases = []
    for order in ReleaseAdapter(snapshot).orders():
        if any(item["ingested_at"] > snapshot.tick_at for item in order.evidence):
            raise ValueError("prediction evidence exceeds snapshot tick")
        facts = {item["fact_code"]: item["value"] for item in order.evidence if item["is_structured"]}
        stage = facts.get("logistics_stage", "created")
        if "delivered_at" in facts or stage in TERMINAL:
            continue
        has_forecast = "forecast_method" in facts
        if has_forecast and facts["forecast_method"] != MODEL:
            raise ValueError("unsupported forecast method")
        cohorts = {item["record_id"] for item in order.evidence if item["fact_code"] == "forecast_method"}
        if has_forecast and len(cohorts) != 1:
            raise ValueError("forecast must have one cohort identity")
        row = source_orders[order.order_id]
        cases.append(ForecastCase(
            order.order_id, snapshot.tick_at, order.guaranteed_date,
            row["carrier_id"], row["service_level"], stage,
            facts["late_probability"] if has_forecast else None,
            parse_instant(facts["revised_eta"], "revised_eta") if has_forecast and facts["revised_eta"] else None,
            next(iter(cohorts)) if has_forecast else None,
        ))
    return tuple(sorted(cases, key=lambda row: row.order_id))


def observed_outcomes(snapshot: ReplaySnapshot) -> dict[str, Outcome]:
    """Extract first visible deliveries and non-delivery terminal events as of cutoff."""
    cutoff = aware(snapshot.tick_at, "outcome cutoff")
    visible_orders = {row["order_id"] for row in snapshot.orders
                      if parse_instant(row["created_at"], "created_at") <= cutoff}
    deliveries, terminals = {}, {}

    def record(target: dict, order_id: str, value: str) -> None:
        instant = parse_instant(value, "outcome event")
        if order_id in visible_orders and instant <= cutoff:
            target[order_id] = min(instant, target.get(order_id, instant))

    for row in snapshot.orders:
        if row["cancelled_at"]:
            record(terminals, row["order_id"], row["cancelled_at"])
    for row in snapshot.scans:
        if parse_instant(row["ingested_at"], "outcome ingested_at") > cutoff:
            continue
        if row["status"] == "delivered":
            record(deliveries, row["order_id"], row["event_at"])
        elif row["status"] in TERMINAL:
            record(terminals, row["order_id"], row["event_at"])
    for row in snapshot.attempts:
        if row["outcome"] == "delivered":
            record(deliveries, row["order_id"], row["attempt_at"])
    return {order_id: Outcome(deliveries.get(order_id), terminals.get(order_id))
            for order_id in visible_orders}


def _case_payload(row: ForecastCase) -> dict:
    return dict(
        order_id=row.order_id, tick_at=utc_iso(row.tick_at), guaranteed_date=row.guaranteed_date.isoformat(),
        carrier_id=row.carrier_id, service_level=row.service_level, stage=row.stage,
        late_probability=row.late_probability, revised_eta=utc_iso(row.revised_eta) if row.revised_eta else None,
        cohort_id=row.cohort_id,
    )


def _fingerprint(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_release(
    core_path: Path | str, *, ticks: Iterable[datetime], followup_hours: int,
    observed_through: datetime,
) -> dict:
    """Run equal-window evaluation. observed_through is a caller-declared bound."""
    window = _window(followup_hours)
    observed_through = aware(observed_through, "observed_through")
    ticks = tuple(aware(tick, "tick") for tick in ticks)
    if not ticks or len(set(ticks)) != len(ticks):
        raise ValueError("provide nonempty, distinct ticks")
    ticks = tuple(sorted(ticks))
    try:
        if any(tick + window > observed_through for tick in ticks):
            raise ValueError("every full follow-up window must end by observed_through")
    except OverflowError as error:
        raise ValueError("follow-up window exceeds the datetime range") from error
    path = Path(core_path).resolve(strict=True)
    if any(part.lower() in {"truth", "heldout", "release_heldout"} for part in path.parts) or path.name.lower().startswith("truth"):
        raise ValueError("truth and heldout sources are not allowed")
    before = _fingerprint(path)
    cases = []
    with ReleaseReader(path) as reader:
        for tick in ticks:
            cases.extend(predict_snapshot(reader.snapshot(tick)))
    # Only immutable scalar forecasts cross this boundary. Labels never enter fitting.
    frozen = tuple(cases)
    prediction_hash = hashlib.sha256(json.dumps(
        [_case_payload(row) for row in frozen], sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    outcomes = {}
    with ReleaseReader(path) as reader:
        for tick in ticks:
            labels = observed_outcomes(reader.snapshot(tick + window))
            outcomes.update({(tick, order_id): outcome for order_id, outcome in labels.items()})
    if _fingerprint(path) != before:
        raise ValueError("source database changed during evaluation")

    groups = defaultdict(list)
    for row in frozen:
        groups[(row.carrier_id, row.service_level, row.stage)].append(row)
    return dict(
        report_version="a2_forecast_validation_v1", model=MODEL,
        source_path=str(path), source_sha256=before, source_unchanged=True,
        prediction_sha256=prediction_hash, followup_hours=followup_hours,
        observed_through=utc_iso(observed_through), observed_through_is_user_declared=True,
        predictions_frozen_before_outcome_read=True, a3_health_created=False,
        summary=summarize(frozen, outcomes, followup_hours=followup_hours),
        ticks=[dict(
            tick_at=utc_iso(tick), outcome_cutoff=utc_iso(tick + window),
            **summarize((row for row in frozen if row.tick_at == tick), outcomes, followup_hours=followup_hours),
        ) for tick in ticks],
        groups=[dict(
            carrier_id=key[0], service_level=key[1], stage=key[2],
            **summarize(rows, outcomes, followup_hours=followup_hours),
        ) for key, rows in sorted(groups.items())],
        limitations=[
            "Candidate baseline evaluation only; no A3 trust, contact permission, or production assessment is inferred.",
            "observed_through is caller-declared, not proof of feed completeness. Missing deliveries remain unknown.",
            "Equal follow-up reduces window imbalance but does not remove censoring or complete-case selection bias.",
            "Terminal-before-delivery and delayed past delivery are excluded from risk scoring and reported separately.",
            "Brier bounds cover unresolved binary labels in the nonterminal risk cohort; they are not confidence intervals or censoring-adjusted estimates.",
            "ETA error is forecast minus actual. MAE and calibration bins describe observed deliveries only.",
            "Orders can repeat across ticks; observations are correlated. Small groups are descriptive, not deployment approval.",
            "No truth or heldout data is used; no model parameters are tuned by this report.",
        ],
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tick", action="append", required=True, help="Aware ISO timestamp; repeat for multiple ticks")
    parser.add_argument("--followup-hours", type=int, default=72)
    parser.add_argument("--observed-through", required=True, help="Caller-declared end of available observation time")
    parser.add_argument("--core", type=Path, default=ROOT / "data/release_main/core_14d.sqlite")
    parser.add_argument("--output", type=Path, default=ROOT / "runs/a2-validation")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    target = output / "report.json"
    if not output.is_relative_to((ROOT / "runs").resolve()):
        parser.error("--output must be inside repository runs/")
    if target.resolve() == args.core.resolve():
        parser.error("output cannot overwrite the source database")
    try:
        report = validate_release(
            args.core, ticks=[parse_instant(tick, "tick") for tick in args.tick],
            followup_hours=args.followup_hours,
            observed_through=parse_instant(args.observed_through, "observed_through"),
        )
        output.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output,
                                             prefix="report-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            temporary.replace(target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.error(str(error))
    print(json.dumps(dict(report_file=str(target), summary=report["summary"],
                          ticks=[{key: row[key] for key in ("tick_at", "outcome_cutoff", "forecast_count", "eta_mae_hours", "risk_unknown_labels")}
                                 for row in report["ticks"]]), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
