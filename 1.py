import sqlite3

DB_FILE_PATH = "./jds.db"

def migrate_remove_unique():
    conn = sqlite3.connect(DB_FILE_PATH)
    cursor = conn.cursor()

    # Check if migration is needed
    cursor.execute("PRAGMA table_info(job_descriptions);")
    columns = cursor.fetchall()
    print("Before migration, columns:", columns)

    # 1️⃣ Rename old table
    cursor.execute("ALTER TABLE job_descriptions RENAME TO job_descriptions_old;")

    # 2️⃣ Create new table (no UNIQUE constraint on title)
    cursor.execute("""
        CREATE TABLE job_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    # 3️⃣ Copy data from old → new table
    cursor.execute("""
        INSERT INTO job_descriptions (id, title, company, text, created_at)
        SELECT id, title, company, text, created_at FROM job_descriptions_old;
    """)

    # 4️⃣ Drop old table
    cursor.execute("DROP TABLE job_descriptions_old;")

    conn.commit()
    conn.close()
    print("✅ Migration completed successfully — unique constraint removed.")

if __name__ == "__main__":
    migrate_remove_unique()
