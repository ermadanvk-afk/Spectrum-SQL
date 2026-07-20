import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from logger import log_error_sync

_engines = {}

def get_engine(connection_string: str) -> Engine:
    global _engines
    if connection_string not in _engines:
        try:
            params = urllib.parse.quote_plus(connection_string)
            # Create a SQLAlchemy engine for SQL Server via pyodbc
            engine_url = f"mssql+pyodbc:///?odbc_connect={params}"
            engine = create_engine(
                engine_url,
                pool_size=5,         # Number of connections to keep open
                max_overflow=10,     # Max extra connections if pool is full
                pool_pre_ping=True,  # Test connection before using it
                pool_recycle=3600    # Recreate connections every hour
            )
            _engines[connection_string] = engine
        except Exception as e:
            log_error_sync("connect", "DB_CONNECTION_ERROR", e, "Failed to create database engine")
            raise RuntimeError(f"Failed to create database engine: {e}")
    return _engines[connection_string]

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    from sqlalchemy import text
    
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(env_path)
    
    conn_str = os.getenv("DB_CONNECTION_STRING")
    if not conn_str:
        print("ERROR: DB_CONNECTION_STRING not found in .env")
    else:
        print(f"Attempting to connect with SQLAlchemy:\n{conn_str}\n")
        try:
            engine = get_engine(conn_str)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                print(f"[+] SUCCESS! Successfully connected to the database! Test query returned: {result.scalar()}")
        except Exception as e:
            log_error_sync("connect_test", "TEST_CONNECTION_ERROR", e, "Failed test database connection")
            print(f"[X] FAILED to connect.\nError Details: {e}")
