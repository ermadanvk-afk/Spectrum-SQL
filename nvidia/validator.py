import sys
import os

import sqlfluff
from sql_gen import generate_sql
from logger import update_log_sync, log_error_sync

import re

def sanitize_sql(sql: str) -> str:
    sql = sql.replace("≥", ">=").replace("≤", "<=")
    return sql

async def validate_and_fix_sql(sql: str, user_query: str, chat=None, max_retries: int = 2, message_id: int = None, allowed_access: list = None) -> tuple[bool, str, int, int]:
    retry_in_tokens = 0
    retry_out_tokens = 0
    
    if sql in ("UNSAFE_QUERY_DETECTED", "INSUFFICIENT_CONTEXT"):
        return (False, sql, retry_in_tokens, retry_out_tokens)
        
    keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"]
    if any(keyword in sql.upper() for keyword in keywords):
        return (False, "UNSAFE_QUERY_DETECTED", retry_in_tokens, retry_out_tokens)
        
    current_sql = sanitize_sql(sql)
    
    # Load environment variables for DB connection
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(env_path)
    conn_str = os.getenv("DB_CONNECTION_STRING")
    
    from connect import get_engine
    
    for attempt in range(max_retries + 1):
        try:
            # 1. Syntax check using SQLFluff
            parsed = sqlfluff.parse(current_sql, dialect="tsql")
            
            # 1.5. SQLGlot RBAC and Star Ban
            import sqlglot
            from sqlglot.expressions import Star, Table, Column
            
            try:
                ast = sqlglot.parse_one(current_sql, dialect="tsql")
            except Exception as parse_err:
                raise Exception(f"SQL parsing error: {parse_err}")
                
            if list(ast.find_all(Star)):
                raise Exception("Do not use SELECT *. Please explicitly list the specific columns you need from the tables.")

            if allowed_access is not None:
                extracted_tables = {t.name.lower() for t in ast.find_all(Table)}
                allowed_table_names = [a['table_name'].lower() for a in allowed_access]
                
                # Check tables
                for t in extracted_tables:
                    if t not in allowed_table_names:
                        return (False, f"AUTH_ERROR: You are not authorized to access the table '{t}'.", retry_in_tokens, retry_out_tokens)
                        
                # Check columns
                extracted_columns = {c.name.lower() for c in ast.find_all(Column)}
                for t in extracted_tables:
                    table_rules = next((a for a in allowed_access if a['table_name'].lower() == t), None)
                    if table_rules:
                        restricted_cols = [c.lower() for c in table_rules['restricted_columns']]
                        for col in extracted_columns:
                            if col in restricted_cols:
                                return (False, f"AUTH_ERROR: You are not authorized to view the column '{col}'.", retry_in_tokens, retry_out_tokens)

            # 2. Database Dry-Run (Schema & Column validation)
            if conn_str and conn_str != "your_sql_server_connection_string":
                engine = get_engine(conn_str)
                raw_conn = engine.raw_connection()
                try:
                    cursor = raw_conn.cursor()
                    # SET FMTONLY ON compiles the query and verifies columns/tables without returning rows
                    cursor.execute("SET FMTONLY ON")
                    cursor.execute(current_sql)
                except Exception as db_err:
                    raise Exception(f"Database schema error: {db_err}")
                finally:
                    # Always ensure FMTONLY is turned off before returning the connection to the pool
                    cursor.execute("SET FMTONLY OFF")
                    cursor.close()
                    raw_conn.close() # Returns the connection to the pool
                    
            # Log SUCCESS
            update_log_sync(
                message_id=message_id,
                module="validator",
                level="INFO",
                event_type="VALIDATION_SUCCESS",
                message="SQL passed validation.",
                generated_sql=current_sql,
                validation_status="SUCCESS"
            )
            return (True, current_sql, retry_in_tokens, retry_out_tokens)
        except Exception as e:
            if attempt < max_retries:
                error_message = str(e)
                retry_prompt = f"{user_query}\nThe following SQL has an error: {error_message}\nFix it and return only the corrected SQL."
                
                log_error_sync(
                    message_id=message_id,
                    module="validator",
                    event_type="VALIDATION_RETRY",
                    error=e,
                    message=f"SQL Validation Error on attempt {attempt+1}"
                )
                    

                if chat is not None:
                    response = await chat.send_message(retry_prompt)
                    usage = response.usage_metadata
                    if hasattr(usage, 'prompt_token_count'):
                        retry_in_tokens += usage.prompt_token_count
                    if hasattr(usage, 'candidates_token_count'):
                        retry_out_tokens += usage.candidates_token_count
                        
                    content = response.text.strip()
                    sql_match = re.search(r"```sql\n?(.*?)\n?```", content, re.DOTALL)
                    if sql_match:
                        current_sql = sql_match.group(1).strip()
                    else:
                        current_sql = content.replace('```', '').strip()
                else:
                    current_sql = await generate_sql(retry_prompt)
                current_sql = sanitize_sql(current_sql)
            else:
                pass
                
    # Log Failure
    update_log_sync(
        message_id=message_id,
        module="validator",
        level="ERROR",
        event_type="VALIDATION_FAILED",
        message="Sorry ! Please Reframe Your Question by giving more specific details",
        generated_sql=current_sql,
        validation_status="FAILED"
    )
                
    return (False, "UNABLE_TO_GENERATE: Sorry, unable to get the required results.", retry_in_tokens, retry_out_tokens)
