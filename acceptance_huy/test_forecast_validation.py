"""Independent expectations for the offline replay/forecast evaluation boundary."""

from datetime import date, datetime, timedelta
from contextlib import closing
from hashlib import sha256
import json
import sqlite3

import pytest

from logistics_an_nguyen.validation import ForecastCase, Outcome, summarize
from logistics_an_nguyen import validation
from logistics_an_nguyen.replay import ReleaseReader, ReplaySnapshot


TICK = datetime.fromisoformat("2026-10-25T12:00:00+07:00")
CUTOFF = TICK + timedelta(hours=72)


def case(order_id="o1", **changes):
    return ForecastCase(**(dict(
        order_id=order_id, tick_at=TICK, guaranteed_date=date(2026, 10, 25),
        carrier_id="c1", service_level="standard", stage="station",
        late_probability=0.25, revised_eta=TICK + timedelta(hours=4),
        cohort_id="cohort-1",
    ) | changes))


def test_hand_calculated_metrics_and_unknown_label_bounds():
    cases = [case(), case("o2", late_probability=0.75, revised_eta=TICK + timedelta(hours=20)),
             case("o3", late_probability=0.5),
             case("o4", late_probability=None, revised_eta=None, cohort_id=None)]
    outcomes = {
        (TICK, "o1"): Outcome(delivered_at=TICK + timedelta(hours=2)),
        (TICK, "o2"): Outcome(delivered_at=TICK + timedelta(hours=26)),
    }
    result = summarize(cases, outcomes, followup_hours=72)
    assert result["active_observations"] == 4
    assert result["forecast_count"] == 3
    assert result["forecast_coverage"] == 0.75
    assert result["outcome_counts"] == {"delivered": 2, "unobserved": 1}
    assert result["eta_scored"] == 2
    assert result["eta_mae_hours"] == 4.0  # abs(+2) and abs(-6)
    assert result["eta_bias_hours"] == -2.0
    assert result["risk_known_labels"] == 2
    assert result["risk_unknown_labels"] == 1
    assert result["lateness_brier_complete_case"] == 0.0625
    assert result["always_on_time_brier_complete_case"] == 0.5
    assert result["lateness_brier_lower_bound"] == pytest.approx(0.125)
    assert result["lateness_brier_upper_bound"] == pytest.approx(0.125)
    assert result["always_on_time_brier_lower_bound"] == pytest.approx(1 / 3)
    assert result["always_on_time_brier_upper_bound"] == pytest.approx(2 / 3)


def test_unknown_outcomes_are_not_invented_and_empty_metrics_are_null():
    result = summarize([case(late_probability=0.2)], {}, followup_hours=72)
    assert result["eta_mae_hours"] is None
    assert result["lateness_brier_complete_case"] is None
    assert result["risk_known_labels"] == 0
    assert result["risk_unknown_labels"] == 1
    assert result["lateness_brier_lower_bound"] == pytest.approx(0.04)
    assert result["lateness_brier_upper_bound"] == pytest.approx(0.64)
    empty = summarize([], {}, followup_hours=72)
    assert empty["forecast_coverage"] is None
    assert empty["lateness_brier_lower_bound"] is None


def test_immature_guarantee_excludes_even_an_observed_on_time_delivery():
    item = case(guaranteed_date=date(2026, 10, 29))
    result = summarize([item], {(TICK, "o1"): Outcome(delivered_at=TICK + timedelta(hours=2))},
                       followup_hours=72)
    assert result["eta_scored"] == 1
    assert result["risk_exclusion_counts"] == {"deadline_after_followup": 1}
    assert result["risk_known_labels"] == result["risk_unknown_labels"] == 0


@pytest.mark.parametrize(("delivered", "label"), [
    ("2026-10-25T23:59:59+07:00", 0), ("2026-10-26T00:00:00+07:00", 1),
])
def test_vietnam_deadline_boundary(delivered, label):
    result = summarize([case(late_probability=0.0)],
                       {(TICK, "o1"): Outcome(delivered_at=datetime.fromisoformat(delivered))},
                       followup_hours=72)
    assert result["observed_late_fraction"] == label
    assert result["lateness_brier_complete_case"] == label


def test_terminal_and_delayed_past_delivery_are_not_scored_as_future_delivery():
    cases = [case("cancel"), case("past"), case("conflict"), case("return_after_delivery")]
    outcomes = {
        (TICK, "cancel"): Outcome(terminal_at=TICK + timedelta(hours=1)),
        (TICK, "past"): Outcome(delivered_at=TICK),
        (TICK, "conflict"): Outcome(delivered_at=TICK + timedelta(hours=2), terminal_at=TICK + timedelta(hours=1)),
        (TICK, "return_after_delivery"): Outcome(delivered_at=TICK + timedelta(hours=1), terminal_at=TICK + timedelta(hours=2)),
    }
    result = summarize(cases, outcomes, followup_hours=72)
    assert result["outcome_counts"] == {"terminal_before_delivery": 2, "delivery_already_happened": 1, "delivered": 1}
    assert result["eta_scored"] == result["risk_known_labels"] == 1
    assert result["risk_unknown_labels"] == 0


def test_already_late_forecast_still_scores_eta_but_not_risk():
    item = case(guaranteed_date=date(2026, 10, 24))
    result = summarize([item], {(TICK, "o1"): Outcome(delivered_at=TICK + timedelta(hours=2))}, followup_hours=72)
    assert result["eta_mae_hours"] == 2
    assert result["risk_exclusion_counts"] == {"already_late_at_prediction": 1}


def test_future_outcomes_and_duplicate_observations_rejected():
    with pytest.raises(ValueError, match="cutoff"):
        summarize([case()], {(TICK, "o1"): Outcome(delivered_at=CUTOFF + timedelta(seconds=1))}, followup_hours=72)
    with pytest.raises(ValueError, match="duplicate"):
        summarize([case(), case()], {}, followup_hours=72)


@pytest.mark.parametrize("value", [True, -0.1, 1.1, float("nan"), float("inf")])
def test_invalid_probability_rejected(value):
    with pytest.raises(ValueError):
        case(late_probability=value)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "core.sqlite"
    with closing(sqlite3.connect(":memory:")) as db:
        db.executescript("""
            CREATE TABLE orders(order_id,created_at,guaranteed_date,carrier_id,service_level,cancelled_at);
            CREATE TABLE scan_events(event_id,order_id,status,location_type,location_id,event_at,ingested_at,carrier_event_id);
            CREATE TABLE delivery_attempts(attempt_id,order_id,attempt_no,attempt_at,outcome,reason_code,call_attempts);
            CREATE TABLE linehaul_reports(report_id,trip_id,reported_at,reported_by,reason_code,driver_note);
        """)
        for i in range(25):
            db.execute("INSERT INTO orders VALUES (?,?,?,?,?,NULL)",
                       (f"h{i}", "2026-10-23T10:00:00+07:00", "2026-10-24", "c1", "standard"))
            db.execute("INSERT INTO delivery_attempts VALUES (?,?,1,?,'delivered',NULL,1)",
                       (f"a{i}", f"h{i}", "2026-10-24T10:00:00+07:00"))
        for order_id, created, guaranteed, carrier in [
            ("o1", "2026-10-25T10:00:00+07:00", "2026-10-25", "c1"),
            ("o2", "2026-10-26T10:00:00+07:00", "2026-10-26", "c1"),
            ("no_model", "2026-10-25T11:00:00+07:00", "2026-10-25", "c2"),
        ]:
            db.execute("INSERT INTO orders VALUES (?,?,?,?,?,NULL)", (order_id, created, guaranteed, carrier, "standard"))
        for order_id, delivered in [("o1", "2026-10-26T12:00:00+07:00"), ("o2", "2026-10-27T12:00:00+07:00")]:
            db.execute("INSERT INTO delivery_attempts VALUES (?,?,1,?,'delivered',NULL,1)", ("a-" + order_id, order_id, delivered))
        db.commit()
        with closing(sqlite3.connect(path)) as target:
            db.backup(target)
    return path


def run(source, **changes):
    return validation.validate_release(source, **(dict(
        ticks=[TICK], followup_hours=72, observed_through=CUTOFF,
    ) | changes))


def test_runner_uses_equal_windows_and_freezes_all_predictions_first(source, monkeypatch):
    calls = []

    class TracedReader(ReleaseReader):
        def snapshot(self, tick_at):
            calls.append(tick_at)
            return super().snapshot(tick_at)

    monkeypatch.setattr(validation, "ReleaseReader", TracedReader)
    next_tick = TICK + timedelta(days=1)
    before = sha256(source.read_bytes()).hexdigest()
    report = run(source, ticks=[next_tick, TICK], observed_through=CUTOFF + timedelta(days=1))
    assert calls == [TICK, next_tick, CUTOFF, CUTOFF + timedelta(days=1)]
    assert report["source_sha256"] == sha256(source.read_bytes()).hexdigest() == before
    assert report["summary"]["active_observations"] == 4
    assert report["summary"]["distinct_orders"] == 3
    assert report["summary"]["forecast_count"] == report["summary"]["no_forecast_count"] == 2
    assert report["summary"]["eta_mae_hours"] == 2.0
    assert {(row["carrier_id"], row["service_level"], row["stage"]) for row in report["groups"]} == {
        ("c1", "standard", "created"), ("c2", "standard", "created"),
    }
    assert sum(row["active_observations"] for row in report["groups"]) == 4
    assert all(datetime.fromisoformat(row["outcome_cutoff"].replace("Z", "+00:00")) -
               datetime.fromisoformat(row["tick_at"].replace("Z", "+00:00")) == timedelta(hours=72)
               for row in report["ticks"])


def test_future_outcome_change_does_not_change_prediction_fingerprint(source):
    first = run(source)
    with closing(sqlite3.connect(source)) as db, db:
        db.execute("UPDATE delivery_attempts SET attempt_at='2026-10-27T12:00:00+07:00' WHERE order_id='o1'")
    later = run(source)
    assert first["prediction_sha256"] == later["prediction_sha256"]
    assert first["summary"]["eta_mae_hours"] == 2
    assert later["summary"]["eta_mae_hours"] == 26
    assert first["source_sha256"] != later["source_sha256"]


def test_outcome_reader_hides_late_ingestion_and_future_terminal_events():
    orders = (dict(order_id="o1", created_at=TICK.isoformat(), cancelled_at=(CUTOFF + timedelta(seconds=1)).isoformat()),)
    future_scan = dict(order_id="o1", status="delivered", event_at=(TICK + timedelta(hours=1)).isoformat(),
                       ingested_at=(CUTOFF + timedelta(seconds=1)).isoformat())
    future_attempt = dict(order_id="o1", outcome="delivered", attempt_at=(CUTOFF + timedelta(seconds=1)).isoformat())
    snapshot = ReplaySnapshot(CUTOFF, orders, (future_scan,), (future_attempt,), ())
    assert validation.observed_outcomes(snapshot)["o1"] == Outcome()
    at_boundary = dict(future_scan, ingested_at=CUTOFF.isoformat())
    visible = validation.observed_outcomes(ReplaySnapshot(CUTOFF, orders, (at_boundary,), (), ()))
    assert visible["o1"].delivered_at == TICK + timedelta(hours=1)


@pytest.mark.parametrize("changes", [
    {"ticks": []}, {"ticks": [TICK, TICK]}, {"ticks": [TICK.replace(tzinfo=None)]},
    {"followup_hours": 0}, {"followup_hours": -1}, {"followup_hours": True},
    {"observed_through": CUTOFF - timedelta(seconds=1)},
])
def test_invalid_or_truncated_windows_rejected_before_opening_source(tmp_path, changes):
    with pytest.raises(ValueError):
        run(tmp_path / "does-not-exist.sqlite", **changes)


def test_equivalent_timezone_and_tick_order_produce_identical_report(source):
    utc_tick = datetime.fromisoformat("2026-10-25T05:00:00+00:00")
    assert run(source) == run(source, ticks=[utc_tick])
    assert run(source) == run(source)


def test_cli_writes_atomic_report_inside_runtime_only(source, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(validation, "ROOT", tmp_path)
    output = tmp_path / "runs" / "audit"
    args = ["--core", str(source), "--tick", TICK.isoformat(), "--observed-through", CUTOFF.isoformat(), "--output", str(output)]
    before = sha256(source.read_bytes()).hexdigest()
    validation.main(args)
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["eta_mae_hours"] == 2
    assert json.loads(capsys.readouterr().out)["report_file"] == str(output / "report.json")
    assert not list(output.glob("*.tmp"))
    assert sha256(source.read_bytes()).hexdigest() == before
    with pytest.raises(SystemExit) as error:
        validation.main(args[:-1] + [str(tmp_path / "outside")])
    assert error.value.code == 2
    assert not (tmp_path / "outside").exists()
    capsys.readouterr()
    with pytest.raises(SystemExit):
        validation.main(args + ["--followup-hours", "0"])
    assert json.loads((output / "report.json").read_text(encoding="utf-8")) == report


def test_terminal_cancellation_is_counted_separately_in_release_run(source):
    with closing(sqlite3.connect(source)) as db, db:
        db.execute("UPDATE orders SET cancelled_at='2026-10-25T18:00:00+07:00' WHERE order_id='o1'")
    report = run(source)
    assert report["summary"]["forecast_count"] == 1
    assert report["summary"]["outcome_counts"] == {"terminal_before_delivery": 1}
    assert report["summary"]["eta_scored"] == report["summary"]["risk_known_labels"] == 0


def test_truth_named_source_rejected(source):
    blocked = source.with_name("truth_main.sqlite")
    source.rename(blocked)
    with pytest.raises(ValueError, match="truth and heldout"):
        run(blocked)
