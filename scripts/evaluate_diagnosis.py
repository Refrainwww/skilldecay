from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


LABELS = ["clean", "stale", "over_specific", "conflicting", "unknown"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate skill-debt diagnosis labels.")
    parser.add_argument("labels_jsonl", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/diagnosis/diagnosis_report.md"))
    args = parser.parse_args()

    pairs = []
    with args.labels_jsonl.open(encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            gold = item["sample"].get("debt_type", "clean")
            pred = item.get("label", "unknown")
            pairs.append((gold, pred))

    report = render_report(pairs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(report)


def render_report(pairs: list[tuple[str, str]]) -> str:
    confusion = Counter(pairs)
    lines = ["# Diagnosis Report", "", "| label | precision | recall | f1 | support |", "|---|---|---|---|---|"]
    for label in LABELS:
        tp = confusion[(label, label)]
        fp = sum(count for (gold, pred), count in confusion.items() if pred == label and gold != label)
        fn = sum(count for (gold, pred), count in confusion.items() if gold == label and pred != label)
        support = tp + fn
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        lines.append(f"| {label} | {precision:.3f} | {recall:.3f} | {f1:.3f} | {support} |")
    accuracy = sum(gold == pred for gold, pred in pairs) / len(pairs) if pairs else 0.0
    lines.extend(["", f"Accuracy: {accuracy:.3f}"])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
