# SkillDecay

**SkillDecay** is a research prototype for studying **skill debt** in self-evolving LLM agents. It asks a simple question: when agents keep accumulating reusable skills, when should they forget, quarantine, or deprecate them?

The repository contains:

- **SkillDecay**: a lightweight self-forgetting maintenance layer for skill libraries.
- **SkillDebtBench**: a controllable benchmark for stale, over-specific, and conflicting skills.
- **Executable Coding SkillDebtBench**: temporary Python repositories with patch application and unit-test validation.

## Why this matters

Recent self-evolving agents focus on creating, retrieving, and optimizing skills. Append-only skill libraries can become harmful when tools, tasks, APIs, or models drift. We call this phenomenon **skill debt**.

SkillDecay tracks three low-cost signals:

- `utility`: whether recent invocations helped task success.
- `staleness`: whether validations or post-drift outcomes fail.
- `conflict`: whether a skill causes contradictory behavior.

Skills move through a lifecycle:

```text
active -> suspect -> quarantined -> deprecated
                         |-> revived
```

## Repository layout

```text
src/skilldecay/                 Core lifecycle states, scores, and policies
benchmarks/skill_debt_bench/    Controllable synthetic SkillDebtBench
benchmarks/coding_skill_debt/   Coding and executable coding benchmarks
scripts/                        Experiment, plotting, and diagnosis utilities
data/                           Small derived result tables only
figures/                        Generated SVG figures
configs/                        Example local API environment template
```

## Installation

```powershell
git clone https://github.com/Refrainwww/skilldecay
cd skill-related
python -m pip install -e .
$env:PYTHONPATH='src;.'
```

No API key is needed for the core benchmarks.

## Quick start

Run the main controllable benchmark:

```powershell
python -m scripts.run_skilldebtbench --output-dir data/skilldebtbench --steps 180 --drift-step 80 --seeds 20 --pollution-rates 0,0.1,0.25,0.5,0.75
python -m scripts.summarize_skilldebtbench data/skilldebtbench/summaries.csv --pollution-rate 0.25 --output data/skilldebtbench/main_table.md
python -m scripts.plot_skilldebtbench data/skilldebtbench/summaries.csv --output-dir figures
```

Run the ablation:

```powershell
python -m scripts.run_skilldebtbench --output-dir data/ablation --steps 180 --drift-step 80 --seeds 20 --pollution-rates 0.25 --modes skill_decay,decay_no_utility,decay_no_staleness,decay_no_conflict
python -m scripts.summarize_skilldebtbench data/ablation/summaries.csv --pollution-rate 0.25 --output data/ablation/ablation_table.md
```

Run executable coding tasks:

```powershell
python -m benchmarks.coding_skill_debt.exec_benchmark --output-dir data/coding_exec_skill_debt --seeds 5
```

Run dry-run diagnosis evaluation:

```powershell
python -m scripts.llm_diagnose_failures data/coding_exec_skill_debt/records.csv --output data/diagnosis/dryrun_labels.jsonl --limit 40 --dry-run
python -m scripts.evaluate_diagnosis data/diagnosis/dryrun_labels.jsonl --output data/diagnosis/diagnosis_report.md
```

## Current result snapshot

Small derived tables are included for convenience:

- `data/skilldebtbench/main_table.md`
- `data/ablation/ablation_table.md`
- `data/coding_exec_skill_debt/table.md`

Large raw logs are ignored by git and can be regenerated.

## Optional LLM diagnosis

Copy the template and fill local credentials:

```powershell
Copy-Item configs/env.example.ps1 .env.local.ps1
. .\.env.local.ps1
```

Then remove `--dry-run` from `scripts.llm_diagnose_failures`. Keep limits small to control API cost.

## License

MIT License. See `LICENSE`.

