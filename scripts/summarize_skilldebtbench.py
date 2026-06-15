from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev


METRICS = [
    "task_success",
    "post_drift_success",
    "early_recovery_success",
    "token_cost",
    "harmful_skill_invocation_rate",
    "skill_reuse_precision",
    "validation_failure_rate",
    "conflict_observation_rate",
    "final_active_library_size",
]


def fmt(values: list[float]) -> str:
    if len(values) <= 1:
        return f"{values[0]:.3f}" if values else "nan"
    return f"{mean(values):.3f} +/- {stdev(values):.3f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize SkillDebtBench CSV results.")
    parser.add_argument("summaries_csv", type=Path)
    parser.add_argument("--pollution-rate", type=float, default=0.25)
    parser.add_argument("--output", type=Path, default=Path("data/skilldebtbench/main_table.md"))
    args = parser.parse_args()

    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    with args.summaries_csv.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if abs(float(row["pollution_rate"]) - args.pollution_rate) > 1e-9:
                continue
            mode = row["mode"]
            for metric in METRICS:
                grouped[mode][metric].append(float(row[metric]))

    lines = []
    lines.append("| mode | " + " | ".join(METRICS) + " |")
    lines.append("|---" * (len(METRICS) + 1) + "|")
    for mode in sorted(grouped):
        lines.append("| " + mode + " | " + " | ".join(fmt(grouped[mode][metric]) for metric in METRICS) + " |")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
