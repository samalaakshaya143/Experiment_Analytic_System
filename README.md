# Experiment Analytics System

A standard-library Python project for generating and analyzing synthetic A/B experiments. It validates experiment records, measures purchase and support-contact rates, checks sample-ratio mismatch (SRM), and summarizes treatment effects with confidence intervals and guardrail decisions.

All included records are synthetic. The datasets contain documented edge cases for validation and analysis practice; see `data/full/ground_truth.csv` for their labels.

## Requirements

- Python 3.7 or newer
- No third-party Python packages

## Run the analysis

You can run the analysis using the database included in this repository. You do not need to generate data first.

1. Open a terminal in the project folder (the folder containing `README.md`).
2. Check that Python 3.7 or newer is available:

   ```powershell
   python --version
   ```

3. Start the analysis:

   ```powershell
   python src/main.py
   ```

The program runs these steps in order:

1. Opens `database/experiments.db` and checks that it contains the expected records and valid database references.
2. Stops and reports failed checks if the database is invalid.
3. Calculates purchase and support-contact rates, checks whether assignment counts match the experiment allocation ratios, and compares treatment with control.
4. Prints a summary for each experiment and saves the full summary to `reports/analysis_summary.csv`.

When it finishes successfully, the terminal prints `Analysis report saved to reports/analysis_summary.csv`. Open that CSV file to review the results. The checks expect 10 experiments, 50,000 audience members, 20 experiment results, valid foreign-key references, and five labelled edge cases.

This project uses only Python's standard library, so no package installation is required.

## Optional: generate synthetic data

Data generation is a separate task; it is not required to run the included analysis. The generator creates CSV and JSON source tables, a SQLite seed script, checksums, a manifest, and a validation summary:

```powershell
python src/generate_data.py
```

By default, it generates 50,000 eligible users across 10 experiments in `outputs/full`, using a fixed seed for reproducibility. You can set the user count, seed, and output directory:

```powershell
python src/generate_data.py --scale 50000 --seed 20261022 --out outputs/full
```

The generator clears the contents of the selected output directory before writing. Use a dedicated output directory; do not select `data/full` or `data/starter` unless you intend to replace those files.

Generating data does not update `database/experiments.db`. To load generated data into a SQLite database, use the generated `seed.sql` file with SQLite, then run the analysis command. The checked-in sample datasets are in `data/full` and `data/starter`; each contains CSV and JSON tables and its own `seed.sql` script.

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