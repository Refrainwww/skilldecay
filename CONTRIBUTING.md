# Contributing

Thanks for your interest in SkillDecay.

## Development setup

```powershell
python -m pip install -e .
$env:PYTHONPATH='src;.'
python -m compileall -q src benchmarks scripts
```

## Running experiments

Prefer small smoke tests before large sweeps:

```powershell
python -m scripts.run_skilldebtbench --output-dir data/skilldebtbench --steps 60 --drift-step 25 --seeds 2 --pollution-rates 0.25
python -m benchmarks.coding_skill_debt.exec_benchmark --output-dir data/coding_exec_skill_debt --seeds 1
```

## Secrets

Do not commit API keys or `.env.local.ps1`. Use `configs/env.example.ps1` as a template.
