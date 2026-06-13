from pathlib import Path
import json
import sqlite3
import hashlib


REQUIRED_FIELDS = ["source_id", "job_title", "company", "description"]


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

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            source_id TEXT PRIMARY KEY,
            job_title TEXT,
            company TEXT,
            description TEXT,
            tech_stack TEXT,
            content_hash TEXT
        )
        """
    )

    json_files = list(input_path.glob("*.json"))

    total = len(json_files)
    inserted = 0
    skipped = 0
    updated = 0

    for file in json_files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)

            new_hash = compute_content_hash(
                data["job_title"],
                data["company"],
                data["description"]
            )

            # Check if source_id already exists
            cursor.execute(
                "SELECT content_hash FROM jobs WHERE source_id = ?",
                (data["source_id"],)
            )
            existing = cursor.fetchone()

            if existing is None:
                # Brand new record — insert it
                cursor.execute(
                    """
                    INSERT INTO jobs (
                        source_id,
                        job_title,
                        company,
                        description,
                        tech_stack,
                        content_hash
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["source_id"],
                        data["job_title"],
                        data["company"],
                        data["description"],
                        data.get("tech_stack", None),
                        new_hash
                    )
                )
                print(f"✅ Inserted: {file.name}")
                inserted += 1

            elif existing[0] != new_hash:
                # Same source_id but content has changed — update it
                cursor.execute(
                    """
                    UPDATE jobs
                    SET job_title = ?,
                        company = ?,
                        description = ?,
                        tech_stack = ?,
                        content_hash = ?
                    WHERE source_id = ?
                    """,
                    (
                        data["job_title"],
                        data["company"],
                        data["description"],
                        data.get("tech_stack", None),
                        new_hash,
                        data["source_id"]
                    )
                )
                print(f"🔄 Updated (content changed): {file.name}")
                updated += 1

            else:
                # Same source_id, same content — skip
                print(f"⏭️  Skipped (no change): {file.name}")
                skipped += 1

        except Exception as e:
            print(f"❌ Failed: {file.name} - {e}")
            skipped += 1

    connection.commit()
    connection.close()

    print("\n📊 Gold Summary:")
    print(f"Total: {total} | Inserted: {inserted} | Updated: {updated} | Skipped: {skipped}")