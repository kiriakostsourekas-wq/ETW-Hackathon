from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from batteryhack.config import PROCESSED_DIR
from batteryhack.results_validation import (
    DEFAULT_MIN_PAIRED_RATIO,
    format_validation_report,
    validate_research_outputs,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate ML and strategy-comparison processed research artifacts."
    )
    parser.add_argument(
        "--processed-dir",
        default=str(PROCESSED_DIR),
        help="Directory containing processed research CSV/JSON artifacts.",
    )
    parser.add_argument(
        "--min-paired-ratio",
        type=float,
        default=DEFAULT_MIN_PAIRED_RATIO,
        help=(
            "Minimum acceptable paired UK-baseline days as a fraction of headline "
            "evaluated_days."
        ),
    )
    parser.add_argument(
        "--ml-artifact-set",
        default="auto",
        choices=("auto", "default", "scarcity"),
        help="Which ML research artifact family to reconcile against.",
    )
    args = parser.parse_args()

    result = validate_research_outputs(
        Path(args.processed_dir),
        min_paired_ratio=args.min_paired_ratio,
        ml_artifact_set=args.ml_artifact_set,
    )
    print(format_validation_report(result))
    raise SystemExit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
