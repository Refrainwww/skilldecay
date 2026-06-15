from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


def main() -> None:
    parser = argparse.ArgumentParser(description="Create lightweight SVG figures for SkillDebtBench.")
    parser.add_argument("summaries_csv", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(args.summaries_csv.open(encoding="utf-8")))
    write_pollution_svg(rows, args.output_dir / "pollution_success.svg", "task_success")
    write_pollution_svg(rows, args.output_dir / "pollution_harmful.svg", "harmful_skill_invocation_rate")
    print(f"wrote {args.output_dir}")


def write_pollution_svg(rows: list[dict], path: Path, metric: str) -> None:
    grouped: dict[str, dict[float, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row["mode"]][float(row["pollution_rate"])].append(float(row[metric]))

    width, height = 760, 460
    margin = 60
    rates = sorted({rate for by_rate in grouped.values() for rate in by_rate})
    max_y = max(mean(values) for by_rate in grouped.values() for values in by_rate.values())
    min_y = min(mean(values) for by_rate in grouped.values() for values in by_rate.values())
    y_pad = max(0.02, (max_y - min_y) * 0.1)
    min_y = max(0.0, min_y - y_pad)
    max_y = min(1.0 if metric != "token_cost" else max_y + y_pad, max_y + y_pad)
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#17becf", "#7f7f7f"]

    def x_pos(rate: float) -> float:
        if len(rates) == 1:
            return width / 2
        return margin + (rate - min(rates)) / (max(rates) - min(rates)) * (width - 2 * margin)

    def y_pos(value: float) -> float:
        return height - margin - (value - min_y) / max(1e-9, max_y - min_y) * (height - 2 * margin)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    svg.append('<rect width="100%" height="100%" fill="white"/>')
    svg.append(f'<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="black"/>')
    svg.append(f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="black"/>')
    svg.append(f'<text x="{width/2}" y="30" text-anchor="middle" font-family="Arial" font-size="18">{metric} vs skill debt pollution</text>')
    svg.append(f'<text x="{width/2}" y="{height-15}" text-anchor="middle" font-family="Arial" font-size="13">pollution rate</text>')
    svg.append(f'<text x="18" y="{height/2}" transform="rotate(-90 18,{height/2})" text-anchor="middle" font-family="Arial" font-size="13">{metric}</text>')

    for index, (mode, by_rate) in enumerate(sorted(grouped.items())):
        points = []
        for rate in rates:
            if rate in by_rate:
                points.append((x_pos(rate), y_pos(mean(by_rate[rate]))))
        if not points:
            continue
        color = colors[index % len(colors)]
        point_string = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        svg.append(f'<polyline points="{point_string}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in points:
            svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')
        legend_y = margin + index * 18
        svg.append(f'<rect x="{width-margin+8}" y="{legend_y-10}" width="10" height="10" fill="{color}"/>')
        svg.append(f'<text x="{width-margin+24}" y="{legend_y}" font-family="Arial" font-size="11">{mode}</text>')

    for rate in rates:
        x = x_pos(rate)
        svg.append(f'<text x="{x:.1f}" y="{height-margin+18}" text-anchor="middle" font-family="Arial" font-size="11">{rate:g}</text>')
    for tick in range(5):
        value = min_y + tick / 4 * (max_y - min_y)
        y = y_pos(value)
        svg.append(f'<line x1="{margin-4}" y1="{y:.1f}" x2="{margin}" y2="{y:.1f}" stroke="black"/>')
        svg.append(f'<text x="{margin-8}" y="{y+4:.1f}" text-anchor="end" font-family="Arial" font-size="11">{value:.2f}</text>')
    svg.append("</svg>")
    path.write_text("\n".join(svg), encoding="utf-8")


if __name__ == "__main__":
    main()
