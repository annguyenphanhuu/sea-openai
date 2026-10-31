"""Read-only, allowlisted as-of projection of the inspected release schema.

Only this harness layer opens release files. The estimator receives a projection,
never a database connection, final outcomes from the future, or truth labels.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3

from .models import VIETNAM, aware, parse_instant


@dataclass(frozen=True, slots=True)
class ReplaySnapshot:
    tick_at: datetime
    orders: tuple[dict, ...]
    scans: tuple[dict, ...]
    attempts: tuple[dict, ...]
    reports: tuple[dict, ...]
    seller_prepare_days: int | None = None

    def __post_init__(self) -> None:
        if self.seller_prepare_days is not None and (
            type(self.seller_prepare_days) is not int or self.seller_prepare_days < 0
        ):
            raise ValueError("seller_prepare_days must be a nonnegative integer or null")


class ReleaseReader:
    """Project release_main without changing sim_clock or touching other datasets."""

    def __init__(self, core_path: Path | str) -> None:
        path = Path(core_path).resolve(strict=True)
        self.connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA query_only = ON")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ReleaseReader":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def snapshot(self, tick_at: datetime) -> ReplaySnapshot:
        """Filter ingestion first; tables lacking ingestion use documented availability."""
        aware(tick_at, "tick_at")
        # Source timestamps have second precision and a uniform +07:00 offset.
        cutoff = tick_at.astimezone(VIETNAM).isoformat(timespec="seconds")
        # Older/minimal projections omit optional metadata; preserve unknowns as NULL.
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(orders)")}
        metadata = ", ".join(
            field if field in columns else f"NULL AS {field}"
            for field in ("customer_id", "payment_method", "items_value_vnd")
        )
        queries = (
            ("SELECT order_id, created_at, guaranteed_date, carrier_id, service_level, "
             f"{metadata}, "
             "CASE WHEN cancelled_at <= ? THEN cancelled_at END AS cancelled_at "
             "FROM orders WHERE created_at <= ? ORDER BY order_id", (cutoff, cutoff)),
            ("SELECT event_id, order_id, status, location_type, location_id, event_at, "
             "ingested_at, carrier_event_id FROM scan_events "
             "WHERE ingested_at <= ? AND event_at <= ? ORDER BY event_at, event_id", (cutoff, cutoff)),
            ("SELECT attempt_id, order_id, attempt_no, attempt_at, outcome, reason_code, "
             "call_attempts FROM delivery_attempts WHERE attempt_at <= ? "
             "ORDER BY attempt_at, attempt_id", (cutoff,)),
            ("SELECT report_id, trip_id, reported_at, reported_by, reason_code, driver_note "
             "FROM linehaul_reports WHERE reported_at <= ? ORDER BY reported_at, report_id", (cutoff,)),
        )
        projected = [tuple(dict(row) for row in self.connection.execute(sql, args))
                     for sql, args in queries]
        # Release policy is static configuration without event/ingestion timestamps.
        # Older projections may omit it; never silently invent the two-day limit.
        seller_prepare_days = None
        if self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='policy'"
        ).fetchone():
            rows = self.connection.execute(
                "SELECT value FROM policy WHERE key='seller_prepare_days'"
            ).fetchall()
            if rows:
                value = rows[0]["value"]
                if len(rows) != 1 or not isinstance(value, str) or not value.isascii() or not value.isdecimal():
                    raise ValueError("policy.seller_prepare_days must be a nonnegative integer string")
                seller_prepare_days = int(value)
        return ReplaySnapshot(tick_at, *projected, seller_prepare_days=seller_prepare_days)


def handover_milestones(
    scans: tuple[dict, ...], created: dict[str, datetime], tick_at: datetime,
) -> dict[str, tuple[datetime, datetime, str]]:
    """Select the first visible handover, with stable ingestion/record tie breaks."""
    handovers = {}
    for row in scans:
        if row["order_id"] not in created or row["status"] != "handed_over":
            continue
        ingested_at = parse_instant(row["ingested_at"], "handover ingested_at")
        if ingested_at > tick_at:
            continue
        event_at = parse_instant(row["event_at"], "handover event_at")
        if event_at > tick_at:
            continue
        if event_at < created[row["order_id"]]:
            raise ValueError("handed_over event cannot precede order creation")
        if event_at > ingested_at:
            raise ValueError("handed_over event cannot follow its ingestion")
        candidate = (event_at, ingested_at, row["event_id"])
        previous = handovers.get(row["order_id"])
        if previous is None or candidate < previous:
            handovers[row["order_id"]] = candidate
    return handovers


STAGES = (
    "created", "packed", "handed_over", "sorting_center", "linehaul_departed",
    "linehaul_arrived", "station", "out_for_delivery", "failed", "delivered",
    "returning", "returned", "lost", "damaged", "waiting_to_return", "return_failed",
)
TERMINAL = frozenset({"delivered", "returning", "returned", "lost", "damaged",
                      "waiting_to_return", "return_failed"})


def grouped(rows: tuple[dict, ...], key: str) -> dict[str, list[dict]]:
    result = defaultdict(list)
    for row in rows:
        result[row[key]].append(row)
    return dict(result)


def deduplicate_scans(rows: list[dict]) -> list[dict]:
    """Deduplicate visible carrier retries and near-identical internal scans."""
    result = []
    carrier_ids = set()
    previous = {}
    for row in sorted(rows, key=lambda item: (
        item["event_at"], STAGES.index(item["status"]), item["event_id"],
    )):
        carrier_key = (row["order_id"], row["carrier_event_id"])
        if row["carrier_event_id"] and carrier_key in carrier_ids:
            continue
        key = (row["order_id"], row["status"], row["location_type"], row["location_id"])
        event_at = datetime.fromisoformat(row["event_at"])
        if not row["carrier_event_id"] and key in previous and (
            event_at - previous[key]
        ).total_seconds() < 120:
            continue
        result.append(row)
        previous[key] = event_at
        if row["carrier_event_id"]:
            carrier_ids.add(carrier_key)
    return result
