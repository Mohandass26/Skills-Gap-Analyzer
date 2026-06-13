from pathlib import Path
import sqlite3


def load_sql(filepath):
    """Load a SQL query from a .sql file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def run_data_profile(db_path):
    db_path = Path(db_path)

    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    # Load all SQL from files 
    sql_count_all       = load_sql("queries/count_all_jobs.sql")
    sql_missing_fields  = load_sql("queries/count_missing_fields.sql")
    sql_avg_desc        = load_sql("queries/avg_description_length.sql")
    sql_shortest        = load_sql("queries/shortest_description.sql")
    sql_longest         = load_sql("queries/longest_description.sql")

    cursor.execute(sql_count_all)
    total_records = cursor.fetchone()[0]

    cursor.execute(sql_missing_fields)
    missing_job_title, missing_company, missing_description = cursor.fetchone()

    cursor.execute(sql_avg_desc)
    avg_description_length = cursor.fetchone()[0] or 0

    cursor.execute(sql_shortest)
    shortest = cursor.fetchone()

    cursor.execute(sql_longest)
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