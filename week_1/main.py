import sys
from pathlib import Path

from src.ingestor import ingest_all_mhtml
from src.processor import process_all_html
#from src.loader import load_all_jsons
#from src.profiler import run_data_profile


SOURCE_DIR = Path("data/0_source")
BRONZE_DIR = Path("data/1_bronze")
SILVER_DIR = Path("data/2_silver")
GOLD_DIR = Path("data/3_gold")
DB_NAME = "jobs.db"


def run_profiler():
    db_path = GOLD_DIR / DB_NAME
    #run_data_profile(db_path)


def run_gold():
    input_dir = SILVER_DIR
    output_dir = GOLD_DIR
    #load_all_jsons(input_dir, output_dir)


def run_silver():
    input_dir = BRONZE_DIR
    output_dir = SILVER_DIR
    process_all_html(input_dir, output_dir)


def run_bronze():
    input_dir = SOURCE_DIR
    output_dir = BRONZE_DIR
    ingest_all_mhtml(input_dir, output_dir)


def main():
    commands = {
        "ingest": run_bronze,
        "bronze": run_bronze,
        "process": run_silver,
        "silver": run_silver,
        "gold": run_gold,
        "profile": run_profiler,
    }

    if len(sys.argv) < 2:
        print("Please provide a command.")
        print("Example: python main.py ingest")
        print("\nAvailable commands:")
        for command in commands:
            print(f"  - {command}")
        return

    command = sys.argv[1].lower()

    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        print("\nAvailable commands:")
        for command in commands:
            print(f"  - {command}")


if __name__ == "__main__":
    main()