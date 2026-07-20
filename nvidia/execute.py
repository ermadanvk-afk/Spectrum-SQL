from connect import get_engine
from sqlalchemy import text
import contextlib
from logger import log_error_sync, update_log_sync_by_id

def execute_query(sql: str, connection_string: str = None, connection=None, timeout_seconds: int = 45, log_id: int = None) -> tuple[list[str], list[dict]]:
    try:
        if connection is None:
            if not connection_string:
                raise ValueError("Either connection_string or connection must be provided")
            engine = get_engine(connection_string)
            conn_context = engine.connect()
        else:
            @contextlib.contextmanager
            def dummy_context(c):
                yield c
            conn_context = dummy_context(connection)
            
        with conn_context as conn:
            try:
                raw_conn = conn.connection.dbapi_connection
                if hasattr(raw_conn, 'timeout'):
                    raw_conn.timeout = timeout_seconds
            except Exception:
                pass
                
            # SQLAlchemy connection execution
            result = conn.execute(text(sql))
            
            # Extract column names
            columns = list(result.keys())
            
            # Extract rows as dictionaries (Limit to 3000 records to prevent memory crash on old DBs)
            rows = [dict(zip(columns, row)) for row in result.fetchmany(3000)]
            
        from logger import update_log_sync_by_id
        update_log_sync_by_id(
            log_id=log_id,
            module="execute",
            level="INFO",
            event_type="EXECUTION_SUCCESS",
            message="SQL executed successfully on target DB",
            execution_status="SUCCESS"
        )
            
        return columns, rows
        
    except Exception as e:
        from logger import update_log_sync_by_id
        update_log_sync_by_id(
            log_id=log_id,
            module="execute",
            level="ERROR",
            event_type="EXECUTION_FAILED",
            message=f"Failed to execute SQL: {str(e)}",
            execution_status="FAILED"
        )
        log_error_sync("execute", "DB_EXECUTION_ERROR", e, "Error executing SQL on external DB", log_id=log_id, details={"sql": sql})
        raise RuntimeError(f"Database execution error: {e}\n\nFAILED SQL:\n{sql}")

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    load_dotenv(env_path)
    
    test_sql = "SELECT * FROM Purchase.vwaiPurchaseOrderMain"  # Example SQL
    conn_str = os.getenv("DB_CONNECTION_STRING")
    
    if conn_str and conn_str != "your_sql_server_connection_string":
        print(f"Testing execution with SQL:\n{test_sql}\n")
        try:
            cols, rows = execute_query(test_sql, conn_str)
            print("Columns:", cols)
            print(f"Row count: {len(rows)}")
            if rows:
                print("First row:", rows[0])
        except Exception as e:
            log_error_sync("execute_test", "TEST_EXECUTION_ERROR", e, "Error during test execution")
            print(f"Error: {e}")
    else:
        print("DB_CONNECTION_STRING is not set properly in .env")
