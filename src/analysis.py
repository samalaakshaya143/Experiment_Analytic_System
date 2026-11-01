import csv
import math
import sqlite3

from metrics import calculate_metrics
from randomization import check_randomization


def analyze_experiments(db_path="database/experiments.db",
                       report_path="reports/analysis_summary.csv"):
    # Reuse the metrics and randomization checks you already ran.
    metric_rows = calculate_metrics(db_path)
    randomization_rows = check_randomization(db_path)

    srm_by_experiment = {
        row[0]: {"p_value": row[3], "status": row[4]}
        for row in randomization_rows
    }

    connection = sqlite3.connect(db_path)
    try:
        guardrails = connection.execute(
            """
            SELECT experiment_id, threshold
            FROM guardrail_metrics
            """
        ).fetchall()
    finally:
        connection.close()

    threshold_by_experiment = {
        experiment_id: float(threshold)
        for experiment_id, threshold in guardrails
    }

    by_experiment = {}
    for row in metric_rows:
        by_experiment.setdefault(row["experiment_id"], {})[
            row["variant_name"]
        ] = row

    results = []

    for experiment_id, variants in sorted(by_experiment.items()):
        control = variants["control"]
        treatment = variants["treatment"]

        control_rate = control["purchase_rate"]
        treatment_rate = treatment["purchase_rate"]
        effect = treatment_rate - control_rate

        standard_error = math.sqrt(
            control_rate * (1 - control_rate) / control["assigned"]
            + treatment_rate * (1 - treatment_rate) / treatment["assigned"]
        )

        if standard_error:
            z_score = effect / standard_error
            p_value = math.erfc(abs(z_score) / math.sqrt(2))
        else:
            p_value = 1.0

        ci_low = effect - 1.96 * standard_error
        ci_high = effect + 1.96 * standard_error

        support_difference = (
            treatment["support_rate"] - control["support_rate"]
        )
        guardrail_status = (
            "FAIL"
            if support_difference > threshold_by_experiment[experiment_id]
            else "PASS"
        )
        srm_status = srm_by_experiment[experiment_id]["status"]

        if srm_status == "SRM warning":
            decision = "Investigate randomization before interpreting results"
        elif guardrail_status == "FAIL":
            decision = "Guardrail failed; do not recommend treatment"
        elif p_value < 0.05 and effect > 0:
            decision = "Evidence of a positive treatment effect"
        else:
            decision = "No clear evidence of a positive treatment effect"

        results.append({
            "experiment_id": experiment_id,
            "control_rate": control_rate,
            "treatment_rate": treatment_rate,
            "absolute_effect": effect,
            "ci95_low": ci_low,
            "ci95_high": ci_high,
            "p_value": p_value,
            "support_rate_difference": support_difference,
            "guardrail_status": guardrail_status,
            "srm_status": srm_status,
            "decision": decision,
        })

    fieldnames = list(results[0].keys())

    with open(report_path, "w", newline="", encoding="utf-8") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    for row in results:
        print(
            "{} | effect={:.2%} | 95% CI [{:.2%}, {:.2%}] | "
            "p={:.4f} | SRM={} | guardrail={} | {}".format(
                row["experiment_id"],
                row["absolute_effect"],
                row["ci95_low"],
                row["ci95_high"],
                row["p_value"],
                row["srm_status"],
                row["guardrail_status"],
                row["decision"],
            )
        )

    print("Analysis report saved to {}".format(report_path))
    return results


if __name__ == "__main__":
    analyze_experiments()