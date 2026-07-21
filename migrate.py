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

# --- Multi-Role Migration ---
try:
    print("Starting multi-role migration...")
    cursor.execute("PRAGMA foreign_keys=OFF")
    
    # Check if users table still has role_id column
    cursor.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in cursor.fetchall()]
    
    if 'role_id' in columns:
        print("Creating user_roles table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER, 
                role_id INTEGER, 
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(role_id) REFERENCES roles(id)
            )
        ''')
        
        print("Migrating existing role_id data...")
        cursor.execute('''
            INSERT OR IGNORE INTO user_roles (user_id, role_id) 
            SELECT id, role_id FROM users WHERE role_id IS NOT NULL
        ''')
        
        print("Rebuilding users table without role_id...")
        cursor.execute('''
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                display_token BOOLEAN DEFAULT 0,
                display_sql BOOLEAN DEFAULT 0,
                user_type INTEGER DEFAULT 2,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        cursor.execute('''
            INSERT INTO users_new (id, username, hashed_password, display_token, display_sql, user_type, is_active)
            SELECT id, username, hashed_password, display_token, display_sql, user_type, is_active FROM users
        ''')
        
        cursor.execute("DROP TABLE users")
        cursor.execute("ALTER TABLE users_new RENAME TO users")
        
        # Recreate the index on username
        cursor.execute("CREATE UNIQUE INDEX ix_users_username ON users (username)")
        
        print("User roles migration complete!")
    else:
        print("User roles migration already performed (role_id not found in users table).")
        
    conn.commit()
except Exception as e:
    print(f"Error during user roles migration: {e}")
    conn.rollback()
finally:
    cursor.execute("PRAGMA foreign_keys=ON")

# --- Role Transfer Migration ---
# Use this block to move users from old roles to the new roles created by entryin.py.
try:
    print("\nStarting role transfer...")
    cursor = conn.cursor()
    
    # Mapping from old role names to new role names
    role_transfer_mapping = {
        "Purchase Manager": "purchase",
        "Warehouse Manager": "store",
        "Purchase Executive": "finance"
    }
    
    for old_name, new_name in role_transfer_mapping.items():
        # Get old role ID
        cursor.execute("SELECT id FROM roles WHERE name = ?", (old_name,))
        old_role = cursor.fetchone()
        
        # Get new role ID
        cursor.execute("SELECT id FROM roles WHERE name = ?", (new_name,))
        new_role = cursor.fetchone()
        
        if old_role and new_role:
            old_id = old_role[0]
            new_id = new_role[0]
            
            # Move users to the new role in user_roles table
            cursor.execute("UPDATE OR IGNORE user_roles SET role_id = ? WHERE role_id = ?", (new_id, old_id))
            # Delete old mappings if any remain (due to IGNORE clause above)
            cursor.execute("DELETE FROM user_roles WHERE role_id = ?", (old_id,))
            
            # Finally, delete the old role from the roles table
            cursor.execute("DELETE FROM roles WHERE id = ?", (old_id,))
            print(f"Transferred users from '{old_name}' to '{new_name}' and removed old role.")
            
    conn.commit()
    print("Role transfer complete!")
except Exception as e:
    print(f"Error during role transfer: {e}")
    conn.rollback()

conn.close()
