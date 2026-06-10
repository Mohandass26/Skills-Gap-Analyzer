from pathlib import Path
import json
import sqlite3


REQUIRED_FIELDS = ["source_id", "job_title", "company", "description"]


def load_all_jsons(input_dir, output_dir):
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    print("🥇 Gold:...")

    if not input_path.exists():
        print("⚠️ Silver directory not found.")
        print("\n📊 Gold Summary:")
        print("Total: 0 | Inserted: 0 | Skipped: 0")
        return

    db_path = output_path / "jobs.db"

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            source_id TEXT PRIMARY KEY,
            job_title TEXT,
            company TEXT,
            description TEXT,
            tech_stack TEXT
        )
        """
    )

    json_files = list(input_path.glob("*.json"))

    total = len(json_files)
    inserted = 0
    skipped = 0

    for file in json_files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)

            missing_fields = [
                field for field in REQUIRED_FIELDS
                if field not in data or not data[field]
            ]

            if missing_fields:
                for field in missing_fields:
                    print(f"⚠️ Missing {field} in: {file.name}")

                skipped += 1
                continue

            cursor.execute(
                """
                INSERT OR IGNORE INTO jobs (
                    source_id,
                    job_title,
                    company,
                    description,
                    tech_stack
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    data["source_id"],
                    data["job_title"],
                    data["company"],
                    data["description"],
                    data.get("tech_stack", "")
                )
            )

            if cursor.rowcount == 0:
                print(f"⏭️  Skipped (duplicate): {file.name}")
                skipped += 1
            else:
                print(f"✅ Inserted: {file.name}")
                inserted += 1

        except Exception as e:
            print(f"❌ Failed: {file.name} - {e}")
            skipped += 1

    connection.commit()
    connection.close()

    print("\n📊 Gold Summary:")
    print(f"Total: {total} | Inserted: {inserted} | Skipped: {skipped}")