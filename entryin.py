import sqlite3
import json

# 1. Read the JSON configuration
with open('roles_config.json', 'r') as f:
    config = json.load(f)

conn = sqlite3.connect("spectrum.db")
cursor = conn.cursor()

# 2. Insert the Roles
print("Inserting Roles...")
for role_name in config.get("roles", []):
    # Using INSERT OR IGNORE just in case you run this multiple times
    cursor.execute("INSERT OR IGNORE INTO roles (name) VALUES (?)", (role_name,))

# 3. Insert the Access Mappings
print("Inserting Access Mappings...")
for mapping in config.get("access_mapping", []):
    role_name = mapping["role"]
    table_name = mapping["table_name"]
    restricted_cols = json.dumps(mapping.get("restricted_columns", []))
    
    # Get the role_id for the role name
    cursor.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
    result = cursor.fetchone()
    
    if result:
        role_id = result[0]
        # Insert the access mapping
        cursor.execute(
            """
            INSERT INTO role_table_access (role_id, table_name, restricted_columns) 
            VALUES (?, ?, ?)
            """, 
            (role_id, table_name, restricted_cols)
        )
    else:
        print(f"Warning: Role '{role_name}' not found in the database. Did you create it?")

# 4. Save and close
conn.commit()
conn.close()
print("All roles and access mappings have been successfully entered from the JSON file!")
