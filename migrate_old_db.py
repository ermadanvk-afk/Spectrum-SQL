import sqlite3
import os

DB_PATH = "spectrum.db"

def alter_table_add_column(cursor, table, column_def):
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        print(f"Added column: {column_def} to {table}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"Column already exists: {column_def} in {table}")
        else:
            print(f"Error adding {column_def} to {table}: {e}")

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Update system_logs table
    print("--- Updating system_logs ---")
    alter_table_add_column(cursor, "system_logs", "is_useful BOOLEAN")
    alter_table_add_column(cursor, "system_logs", "user_comment VARCHAR(500)")

    # 2. Update users table
    print("--- Updating users ---")
    alter_table_add_column(cursor, "users", "role_id INTEGER")
    alter_table_add_column(cursor, "users", "display_token BOOLEAN DEFAULT 0")
    alter_table_add_column(cursor, "users", "display_sql BOOLEAN DEFAULT 0")
    alter_table_add_column(cursor, "users", "user_type INTEGER DEFAULT 2")
    alter_table_add_column(cursor, "users", "is_active BOOLEAN DEFAULT 1")

    # 3. Create missing tables
    print("--- Creating new tables ---")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR NOT NULL UNIQUE
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_roles_id ON roles(id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_roles_name ON roles(name)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS role_table_access (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role_id INTEGER NOT NULL,
        table_name VARCHAR NOT NULL,
        restricted_columns TEXT,
        FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE CASCADE
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_role_table_access_id ON role_table_access(id)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS refresh_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token VARCHAR NOT NULL UNIQUE,
        expires_at DATETIME NOT NULL,
        revoked BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_id ON refresh_tokens(id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_token ON refresh_tokens(token)")

    # 4. Update sessions table
    print("--- Updating sessions ---")
    alter_table_add_column(cursor, "sessions", "user_id INTEGER")

    # 5. Update messages table
    print("--- Updating messages ---")
    alter_table_add_column(cursor, "messages", "db_id INTEGER")

    # 6. Create new tables for DB master and user roles
    print("--- Creating newer tables ---")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS db_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR NOT NULL UNIQUE,
        connection_string VARCHAR NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_db_master_id ON db_master(id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_db_master_name ON db_master(name)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_database_access (
        user_id INTEGER NOT NULL,
        db_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, db_id),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(db_id) REFERENCES db_master(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_roles (
        user_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, role_id),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE CASCADE
    )
    """)

    print("--- Migrating role_id from users to user_roles ---")
    try:
        cursor.execute("""
        INSERT OR IGNORE INTO user_roles (user_id, role_id)
        SELECT id, role_id FROM users WHERE role_id IS NOT NULL
        """)
        print("Migrated existing user roles from users table.")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    print("--- Migration complete! ---")

if __name__ == "__main__":
    migrate()
