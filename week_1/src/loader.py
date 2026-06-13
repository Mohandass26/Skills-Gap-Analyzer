from pathlib import Path
import json
import sqlite3
import hashlib


REQUIRED_FIELDS = ["source_id", "job_title", "company", "description"]


def load_sql(filepath):
    """Load a SQL query from a .sql file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def compute_content_hash(job_title, company, description):
    hash_input = f"{job_title}|{company}|{description}"
    return hashlib.sha256(hash_input.encode()).hexdigest()


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

    # Load all SQL from files 
    sql_create = load_sql("queries/create_jobs_table.sql")
    sql_select = load_sql("queries/select_job_by_id.sql")
    sql_insert = load_sql("queries/insert_job.sql")
    sql_update = load_sql("queries/update_job.sql")

    cursor.execute(sql_create)

    json_files = list(input_path.glob("*.json"))

    total = len(json_files)
    inserted = 0
    skipped = 0
    updated = 0

    for file in json_files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)

            
            missing = [field for field in REQUIRED_FIELDS if field not in data]
            if missing:
                raise ValueError(f"Missing fields: {missing}")

            
            new_hash = compute_content_hash(
                data["job_title"],
                data["company"],
                data["description"]
            )

            
            cursor.execute(sql_select, (data["source_id"],))
            existing = cursor.fetchone()

            if existing is None:
                
                cursor.execute(
                    sql_insert,
                    (
                        data["source_id"],
                        data["job_title"],
                        data["company"],
                        data["description"],
                        data.get("tech_stack"),
                        new_hash
                    )
                )
                print(f"✅ Inserted: {file.name}")
                inserted += 1

            elif existing[0] != new_hash:
                
                cursor.execute(
                    sql_update,
                    (
                        data["job_title"],
                        data["company"],
                        data["description"],
                        data.get("tech_stack"),
                        new_hash,
                        data["source_id"]
                    )
                )
                print(f"🔄 Updated (content changed): {file.name}")
                updated += 1

            else:
                
                print(f"⏭️  Skipped (no change): {file.name}")
                skipped += 1

        except Exception as e:
            print(f"❌ Failed: {file.name} - {e}")
            skipped += 1

    connection.commit()
    connection.close()

    print("\n📊 Gold Summary:")
    print(f"Total: {total} | Inserted: {inserted} | Updated: {updated} | Skipped: {skipped}")