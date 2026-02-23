from __future__ import annotations

import argparse
from pathlib import Path

from nztbdo_labeling.pipeline import latest_events_file, run_labeling_for_session


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NZTBDO auto-labeling for session logs.")
    parser.add_argument(
        "--logs-root",
        default="data/logs",
        help="Path to logs root with session folders.",
    )
    parser.add_argument(
        "--labels-root",
        default="data/labels",
        help="Path to labels output root.",
    )
    parser.add_argument(
        "--events-file",
        default="",
        help="Explicit events.jsonl path. If omitted, latest session is used.",
    )
    parser.add_argument("--pre-ticks", type=int, default=2)
    parser.add_argument("--post-ticks", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logs_root = Path(args.logs_root)
    labels_root = Path(args.labels_root)

    if args.events_file:
        events_path = Path(args.events_file)
    else:
        found = latest_events_file(logs_root)
        if found is None:
            print("No session events found.")
            return
        events_path = found

    summary = run_labeling_for_session(
        events_path=events_path,
        labels_root=labels_root,
        pre_ticks=args.pre_ticks,
        post_ticks=args.post_ticks,
    )
    print(
        f"session={summary.session_id} events={summary.events_total} "
        f"episodes={summary.episodes_total} output={summary.output_path}"
    )


if __name__ == "__main__":
    main()
