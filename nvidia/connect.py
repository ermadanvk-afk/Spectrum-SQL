import pyodbc

def get_connection(connection_string: str) -> pyodbc.Connection:
    try:
        connection = pyodbc.connect(connection_string, autocommit=False)
        return connection
    except Exception as e:
        raise RuntimeError(f"Failed to connect to database: {e}")

def close_connection(connection: pyodbc.Connection) -> None:
    try:
        connection.close()
    except Exception:
        pass

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(env_path)
    
    conn_str = os.getenv("DB_CONNECTION_STRING")
    if not conn_str:
        print("ERROR: DB_CONNECTION_STRING not found in .env")
    else:
        print(f"Attempting to connect with:\n{conn_str}\n")
        try:
            conn = get_connection(conn_str)
            print("[+] SUCCESS! Successfully connected to the database!")
            close_connection(conn)
        except Exception as e:
            print(f"[X] FAILED to connect.\nError Details: {e}")
