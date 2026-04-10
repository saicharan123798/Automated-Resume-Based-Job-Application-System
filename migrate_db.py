import sqlite3
import os

db_path = "autojob.db"

if not os.path.exists(db_path):
    print("Database file not found. Nothing to migration.")
    exit(0)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

new_columns = [
    ("parsed_phone", "VARCHAR(50)"),
    ("parsed_location", "VARCHAR(200)"),
    ("parsed_education_list", "TEXT"),
    ("parsed_experience_list", "TEXT"),
    ("parsed_projects_list", "TEXT"),
    ("parsed_certifications_list", "TEXT"),
    ("parsed_links", "TEXT"),
    ("parsed_summary", "TEXT")
]

added_count = 0
for col_name, col_type in new_columns:
    try:
        cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        print(f"Added column: {col_name}")
        added_count += 1
    except sqlite3.OperationalError:
        print(f"Column {col_name} already exists.")

conn.commit()
conn.close()

print(f"\nMigration finished. Added {added_count} new columns.")
