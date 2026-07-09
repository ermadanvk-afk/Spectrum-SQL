from connect import get_engine
from sqlalchemy import text
import contextlib
from logger import log_error_sync, update_log_sync

def execute_query(sql: str, connection_string: str = None, connection=None, timeout_seconds: int = 45, message_id: int = None) -> tuple[list[str], list[dict]]:
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
            column_names = list(result.keys())
            
            # Fetch all rows
            rows = result.fetchmany(3000)
            
            # Convert to list of dictionaries
            rows_as_list_of_dicts = []
            for row in rows:
                if hasattr(row, '_mapping'):
                    rows_as_list_of_dicts.append(dict(row._mapping))
                else:
                    rows_as_list_of_dicts.append(dict(zip(column_names, row)))
            
        update_log_sync(
            message_id=message_id,
            module="execute",
            level="INFO",
            event_type="EXECUTION_SUCCESS",
            message="SQL executed successfully on target DB",
            execution_status="SUCCESS"
        )
        return (column_names, rows_as_list_of_dicts)
    except Exception as e:
        update_log_sync(
            message_id=message_id,
            module="execute",
            level="ERROR",
            event_type="EXECUTION_FAILED",
            message="SQL execution failed on target DB",
            execution_status="FAILED"
        )
        log_error_sync("execute", "DB_EXECUTION_ERROR", e, "Error executing SQL on external DB", message_id=message_id, details={"sql": sql})
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
