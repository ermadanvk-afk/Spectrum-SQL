import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'spectrum.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS db_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR NOT NULL UNIQUE,
        connection_string VARCHAR NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    print("Created db_master table")
except Exception as e:
    print(f"Error creating db_master: {e}")

try:
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_database_access (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        db_id INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(db_id) REFERENCES db_master(id)
    )
    ''')
    print("Created user_database_access table")
except Exception as e:
    print(f"Error creating user_database_access: {e}")

conn.commit()
conn.close()
