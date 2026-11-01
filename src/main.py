from validation import validate_database
from analysis import analyze_experiments


if __name__ == "__main__":
    if validate_database():
        analyze_experiments()
    else:
        raise SystemExit("Fix the database validation failures before analysis.")