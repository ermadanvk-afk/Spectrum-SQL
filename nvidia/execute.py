from connect import get_connection, close_connection

def execute_query(sql: str, connection_string: str = None, connection=None, timeout_seconds: int = 5) -> tuple[list[str], list[dict]]:
    own_connection = False
    try:
        if connection is None:
            if not connection_string:
                raise ValueError("Either connection_string or connection must be provided")
            connection = get_connection(connection_string)
            own_connection = True
            
        connection.timeout = timeout_seconds
        cursor = connection.cursor()
        
        cursor.execute(sql)
        column_names = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
        
        rows_as_list_of_dicts = []
        for row in rows:
            rows_as_list_of_dicts.append(dict(zip(column_names, row)))
            
        return (column_names, rows_as_list_of_dicts)
    except Exception as e:
        raise RuntimeError(f"Database execution error: {e}\n\nFAILED SQL:\n{sql}")
    finally:
        if own_connection and connection is not None:
            close_connection(connection)

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
            print(f"Error: {e}")
    else:
        print("DB_CONNECTION_STRING is not set properly in .env")
