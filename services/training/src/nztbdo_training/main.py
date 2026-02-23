from __future__ import annotations

import argparse
import json
from pathlib import Path

from nztbdo_training.dataset_builder import build_flat_dataset
from nztbdo_training.offline_eval import evaluate_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build NZTBDO training dataset and print offline metrics.")
    parser.add_argument("--labels-root", default="data/labels")
    parser.add_argument("--dataset-file", default="data/processed/dataset_v1.jsonl")
    parser.add_argument("--metrics-file", default="data/processed/metrics_v1.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    labels_root = Path(args.labels_root)
    dataset_file = Path(args.dataset_file)
    metrics_file = Path(args.metrics_file)

    build_summary = build_flat_dataset(labels_root, dataset_file)
    metrics = evaluate_dataset(dataset_file)

    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    metrics_file.write_text(json.dumps(metrics, ensure_ascii=True, indent=2), encoding="utf-8")

    print(
        f"dataset_rows={build_summary['rows']} dataset_file={dataset_file} "
        f"metrics_file={metrics_file}"
    )
    print(json.dumps(metrics, ensure_ascii=True))


if __name__ == "__main__":
    main()
