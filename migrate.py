import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'spectrum.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute('ALTER TABLE system_logs ADD COLUMN is_useful BOOLEAN')
    print("Added is_useful")
except Exception as e:
    print(f"is_useful err: {e}")

try:
    cursor.execute('ALTER TABLE system_logs ADD COLUMN user_comment VARCHAR(500)')
    print("Added user_comment")
except Exception as e:
    print(f"user_comment err: {e}")

conn.commit()
conn.close()
