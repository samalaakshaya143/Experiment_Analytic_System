from datetime import datetime
import sqlite3


def parse_datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def calculate_metrics(db_path="database/experiments.db"):
    connection = sqlite3.connect(db_path)
    summaries = []

    try:
        experiments = connection.execute(
            """
            SELECT experiment_id, conversion_window_days
            FROM experiments
            ORDER BY experiment_id
            """
        ).fetchall()

        for experiment_id, window_days in experiments:
            variants = connection.execute(
                """
                SELECT variant_id, name
                FROM variants
                WHERE experiment_id = ?
                ORDER BY variant_id
                """,
                (experiment_id,),
            ).fetchall()

            for variant_id, variant_name in variants:
                # Exclude the deliberately injected duplicate assignment.
                assignments = connection.execute(
                    """
                    SELECT assignment_id, assigned_at
                    FROM assignments
                    WHERE experiment_id = ?
                      AND variant_id = ?
                      AND assignment_id NOT LIKE '%-DUPVAR'
                    """,
                    (experiment_id, variant_id),
                ).fetchall()

                assignment_times = {
                    assignment_id: parse_datetime(assigned_at)
                    for assignment_id, assigned_at in assignments
                }
                purchase_users = set()
                support_users = set()

                events = connection.execute(
                    """
                    SELECT assignment_id, event_name, occurred_at
                    FROM conversion_events
                    WHERE experiment_id = ?
                      AND variant_id = ?
                    """,
                    (experiment_id, variant_id),
                ).fetchall()

                for assignment_id, event_name, occurred_at in events:
                    if assignment_id not in assignment_times:
                        continue

                    elapsed = (
                        parse_datetime(occurred_at) - assignment_times[assignment_id]
                    ).total_seconds() / 86400

                    # Count events only when they occur after assignment and within
                    # the experiment's declared conversion window.
                    if 0 <= elapsed <= int(window_days):
                        if event_name == "purchase":
                            purchase_users.add(assignment_id)
                        elif event_name == "support_contact":
                            support_users.add(assignment_id)

                assigned = len(assignment_times)
                purchase_rate = len(purchase_users) / assigned if assigned else 0
                support_rate = len(support_users) / assigned if assigned else 0

                summaries.append({
                    "experiment_id": experiment_id,
                    "variant_id": variant_id,
                    "variant_name": variant_name,
                    "assigned": assigned,
                    "purchases": len(purchase_users),
                    "purchase_rate": purchase_rate,
                    "support_contacts": len(support_users),
                    "support_rate": support_rate,
                })

    finally:
        connection.close()

    for row in summaries:
        print(
            "{} | {} | assigned={} | purchases={} | "
            "purchase rate={:.2%} | support rate={:.2%}".format(
                row["experiment_id"],
                row["variant_name"],
                row["assigned"],
                row["purchases"],
                row["purchase_rate"],
                row["support_rate"],
            )
        )

    return summaries


if __name__ == "__main__":
    calculate_metrics()