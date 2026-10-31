"""Run a local A2 replay assessment without contacts or financial effects."""

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from .adapter import ReleaseAdapter, REQUIRED_FEEDS
from .models import FeedHealth, parse_instant, utc_iso
from .replay import ReleaseReader
from .service import assessment_payload, evaluate_tick


ROOT = Path(__file__).resolve().parents[1]


def runtime_health(state_path: Path, tick_at: datetime) -> tuple[FeedHealth, ...]:
    """Read actual A3 snapshots only; missing state never implies healthy feeds."""
    if not state_path.exists():
        return ()
    with sqlite3.connect(state_path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute(
            "SELECT feed, status, checked_at FROM feed_health "
            "WHERE tick_at <= ? ORDER BY tick_at DESC", (utc_iso(tick_at),),
        )
        latest = {}
        for feed, status, checked_at in rows:
            if feed not in latest:
                latest[feed] = FeedHealth(feed, status, parse_instant(checked_at, "checked_at"))
        return tuple(latest.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tick", required=True, help="Replay time as ISO 8601 with timezone")
    parser.add_argument("--core", type=Path, default=ROOT / "data/release_main/core_14d.sqlite")
    parser.add_argument("--state", type=Path, default=ROOT / "runs/state.sqlite")
    parser.add_argument("--output", type=Path, default=ROOT / "runs/a2")
    args = parser.parse_args()
    tick_at = parse_instant(args.tick, "tick")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "runs").resolve()):
        parser.error("--output must be inside repository runs/")
    with ReleaseReader(args.core) as reader:
        snapshot = reader.snapshot(tick_at)
    orders = ReleaseAdapter(snapshot).orders()
    health = runtime_health(args.state, tick_at)
    result = evaluate_tick(orders, tick_at=tick_at, feed_health=health)
    output.mkdir(parents=True, exist_ok=True)
    stamp = utc_iso(tick_at).replace(":", "").replace("-", "")
    assessments_path = output / f"{stamp}.jsonl"
    with assessments_path.open("w", encoding="utf-8") as stream:
        for assessment in result.assessments:
            stream.write(json.dumps(assessment_payload(assessment), ensure_ascii=False, allow_nan=False) + "\n")
    summary = {
        "tick_at": utc_iso(tick_at), "visible_orders": len(snapshot.orders),
        "assessed_orders": len(orders), "cancelled_orders_excluded": len(snapshot.orders) - len(orders),
        "visible_scans": len(snapshot.scans), "visible_attempts": len(snapshot.attempts),
        "orders_with_baseline_forecast": sum(any(e["fact_code"] == "forecast_method" for e in o.evidence) for o in orders),
        "statuses": dict(Counter(a.status for a in result.assessments)),
        "supervisor_questions": len(result.questions),
        "health_feeds_present": sorted(h.feed for h in health), "required_feeds": REQUIRED_FEEDS,
        "forecast_note": "Uncalibrated visible-history baseline; no truth/heldout data used.",
        "assessments_file": str(assessments_path),
    }
    (output / f"{stamp}.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
