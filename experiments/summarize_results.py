from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev


def fmt(values: list[float]) -> str:
    if len(values) == 1:
        return f"{values[0]:.3f}"
    average = mean(values)
    deviation = stdev(values)
    return f"{average:.3f} +/- {deviation:.3f}"

def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m experiments.summarize_results data/results.json")
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for run in data["runs"]:
        summary = run["summary"]
        mode = summary["mode"]
        for metric, value in summary.items():
            if isinstance(value, (int, float)) and metric != "seed":
                grouped[mode][metric].append(float(value))

    metrics = [
        "task_success",
        "post_drift_success",
        "token_cost",
        "harmful_skill_invocation_rate",
        "skill_reuse_precision",
        "final_active_library_size",
        "decisions",
    ]
    print("| mode | " + " | ".join(metrics) + " |")
    print("|---" * (len(metrics) + 1) + "|")
    for mode, values in grouped.items():
        print("| " + mode + " | " + " | ".join(fmt(values[metric]) for metric in metrics) + " |")


if __name__ == "__main__":
    main()
