import sqlite3


def validate_database(db_path="database/experiments.db"):
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys = ON")

    checks = {}

    try:
        checks["10 experiments"] = (
            connection.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 10
        )
        checks["50,000 audience members"] = (
            connection.execute("SELECT COUNT(*) FROM audience_members").fetchone()[0]
            == 50000
        )
        checks["20 experiment results"] = (
            connection.execute("SELECT COUNT(*) FROM experiment_results").fetchone()[0]
            == 20
        )
        checks["foreign keys valid"] = (
            len(connection.execute("PRAGMA foreign_key_check").fetchall()) == 0
        )
        checks["5 labelled edge cases"] = (
            connection.execute("SELECT COUNT(*) FROM ground_truth").fetchone()[0] == 5
        )
    finally:
        connection.close()

    for name, passed in checks.items():
        print("{}: {}".format("PASS" if passed else "FAIL", name))

    return all(checks.values())


if __name__ == "__main__":
    success = validate_database()
    if not success:
        raise SystemExit("Database validation failed.")
    print("Database validation passed.")