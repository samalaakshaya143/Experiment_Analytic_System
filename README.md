# Experiment Analytics System

A standard-library Python project for generating and analyzing synthetic A/B experiments. It validates experiment records, measures purchase and support-contact rates, checks sample-ratio mismatch (SRM), and summarizes treatment effects with confidence intervals and guardrail decisions.

All included records are synthetic. The datasets contain documented edge cases for validation and analysis practice; see `data/full/ground_truth.csv` for their labels.

## Requirements

- Python 3.7 or newer
- No third-party Python packages

## Run the analysis

From the project root, run:

```powershell
python src/main.py
```

The runner validates `database/experiments.db` first. If validation passes, it calculates metrics and randomization checks, then writes the experiment-level summary to `reports/analysis_summary.csv`. The database must contain the supplied experiment data; the repository includes a database file at that path.

The validation expects 10 experiments, 50,000 audience members, 20 experiment results, valid foreign-key references, and five labelled edge cases. If validation fails, analysis stops and prints the failed checks.

## Generate synthetic data

The generator creates CSV and JSON files, a SQLite seed script, checksums, a manifest, and a validation summary:

```powershell
python src/generate_data.py
```

By default, it generates 50,000 eligible users across 10 experiments in `outputs/full`, using a fixed seed for reproducibility. Options can change the scale, seed, and output directory:

```powershell
python src/generate_data.py --scale 50000 --seed 20261022 --out outputs/full
```

The generator clears the contents of the selected output directory before writing. Choose a dedicated output directory; do not point it at `data/full` or `data/starter` unless you intend to replace those files.

The checked-in datasets are in `data/full` and `data/starter`. Each includes CSV and JSON versions of the source tables, plus `seed.sql` for loading the records into a fresh SQLite database. The default analysis command reads `database/experiments.db`; generating a dataset does not automatically replace that database.

## Analysis details

- Purchase conversion and support-contact rates use assigned users as the denominator (intention-to-treat).
- Events count only when they occur after assignment and within each experiment's conversion window.
- The randomization check compares observed assignment counts with each variant's configured allocation ratio; the SRM warning threshold is a p-value below 0.001.
- The analysis compares treatment and control purchase rates, reports a two-sided p-value and a normal-approximation 95% confidence interval, and checks the support-contact guardrail.
- Decisions flag SRM warnings or guardrail failures before recommending a positive treatment effect.

These calculations are intended for a synthetic, educational dataset and are not a substitute for a production experimentation platform or statistical review.

## Project layout

```text
data/          Sample datasets and SQL seed scripts
database/      SQLite database used by the analysis runner
reports/       Generated analysis summary
src/
	analysis.py      Treatment-effect analysis and report generation
	generate_data.py Synthetic dataset generator
	main.py          Validation-then-analysis entry point
	metrics.py       Purchase and support metric calculations
	randomization.py Sample-ratio mismatch checks
	validation.py    Database integrity and expected-count checks
```