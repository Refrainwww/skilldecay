from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from benchmarks.skill_debt_bench import BenchmarkConfig, RetrievalMode, run_benchmark


DEFAULT_MODES = [
    RetrievalMode.NO_SKILL,
    RetrievalMode.STATIC,
    RetrievalMode.RECENCY,
    RetrievalMode.LRU,
    RetrievalMode.LFU,
    RetrievalMode.VALIDATION_GATED,
    RetrievalMode.HEALTH_SCORE,
    RetrievalMode.SKILL_DECAY,
    RetrievalMode.ORACLE,
]


def parse_rates(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SkillDebtBench experiments.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/skilldebtbench"))
    parser.add_argument("--steps", type=int, default=180)
    parser.add_argument("--drift-step", type=int, default=80)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--pollution-rates", type=parse_rates, default=parse_rates("0,0.1,0.25,0.5,0.75"))
    parser.add_argument("--modes", type=str, default=",".join(mode.value for mode in DEFAULT_MODES))
    args = parser.parse_args()

    modes = [RetrievalMode(part.strip()) for part in args.modes.split(",") if part.strip()]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict] = []
    records: list[dict] = []
    decisions: list[dict] = []

    for pollution_rate in args.pollution_rates:
        for seed in range(args.seeds):
            config = BenchmarkConfig(
                seed=seed,
                steps=args.steps,
                drift_step=args.drift_step,
                pollution_rate=pollution_rate,
            )
            for mode in modes:
                result = run_benchmark(mode, config)
                summaries.append(result.summary)
                records.extend(result.records)
                decisions.extend(result.decisions)

    write_json(args.output_dir / "results.json", {"summaries": summaries, "records": records, "decisions": decisions})
    write_csv(args.output_dir / "summaries.csv", summaries)
    write_csv(args.output_dir / "records.csv", records)
    write_csv(args.output_dir / "decisions.csv", decisions)
    print(f"wrote {args.output_dir}")


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
