import math
import sqlite3


def check_randomization(db_path="database/experiments.db", threshold=0.001):
    connection = sqlite3.connect(db_path)
    results = []

    try:
        experiments = connection.execute(
            "SELECT experiment_id, name FROM experiments ORDER BY experiment_id"
        ).fetchall()

        for experiment_id, name in experiments:
            variants = connection.execute(
                """
                SELECT variant_id, allocation_ratio
                FROM variants
                WHERE experiment_id = ?
                ORDER BY variant_id
                """,
                (experiment_id,),
            ).fetchall()

            # Ignore the deliberately injected duplicate-variant assignment.
            counts = {}
            for variant_id, _ in variants:
                count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM assignments
                    WHERE experiment_id = ?
                      AND variant_id = ?
                      AND assignment_id NOT LIKE '%-DUPVAR'
                    """,
                    (experiment_id, variant_id),
                ).fetchone()[0]
                counts[variant_id] = count

            total = sum(counts.values())
            chi_square = 0.0

            for variant_id, allocation_ratio in variants:
                expected = total * float(allocation_ratio)
                observed = counts[variant_id]
                if expected > 0:
                    chi_square += (observed - expected) ** 2 / expected

            # The generated experiments have two variants, so this uses 1 degree of freedom.
            p_value = math.erfc(math.sqrt(chi_square / 2.0))
            status = "SRM warning" if p_value < threshold else "OK"

            results.append((experiment_id, name, counts, p_value, status))

    finally:
        connection.close()

    for experiment_id, name, counts, p_value, status in results:
        print("{} | {} | counts={} | p-value={:.6f} | {}".format(
            experiment_id, name, counts, p_value, status
        ))

    return results


if __name__ == "__main__":
    check_randomization()