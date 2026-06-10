from pathlib import Path
import sqlite3


def run_data_profile(db_path):
    db_path = Path(db_path)

    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_records = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT
            SUM(CASE WHEN job_title IS NULL OR job_title = '' THEN 1 ELSE 0 END),
            SUM(CASE WHEN company IS NULL OR company = '' THEN 1 ELSE 0 END),
            SUM(CASE WHEN description IS NULL OR description = '' THEN 1 ELSE 0 END)
        FROM jobs
        """
    )
    missing_job_title, missing_company, missing_description = cursor.fetchone()

    cursor.execute("SELECT AVG(LENGTH(description)) FROM jobs")
    avg_description_length = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT source_id, job_title, LENGTH(description)
        FROM jobs
        ORDER BY LENGTH(description) ASC
        LIMIT 1
        """
    )
    shortest = cursor.fetchone()

    cursor.execute(
        """
        SELECT source_id, job_title, LENGTH(description)
        FROM jobs
        ORDER BY LENGTH(description) DESC
        LIMIT 1
        """
    )
    longest = cursor.fetchone()

    connection.close()

    print("\n--- 🔍 DATA QUALITY REPORT ---")
    print(f"📈 Total Records: {total_records}")
    print(
        f"❓ Missing Values -> "
        f"job_title: {missing_job_title or 0}, "
        f"company: {missing_company or 0}, "
        f"description: {missing_description or 0}"
    )
    print(f"📝 Avg Description Length: {int(avg_description_length)} chars")

    if shortest:
        print(f"⚠️  Shortest Description: {shortest[2]} chars")
        print(f"   ↳ source_id: {shortest[0]} | job_title: {shortest[1]}")

    if longest:
        print(f"🚨 Longest Description: {longest[2]} chars")
        print(f"   ↳ source_id: {longest[0]} | job_title: {longest[1]}")