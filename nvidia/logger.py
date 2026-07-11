import json
import traceback
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(BASE_DIR, 'spectrum.db').replace('\\', '/')
DATABASE_URL = f"sqlite:///{db_path}"

# Create a synchronous engine and sessionmaker purely for logging
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class SystemLog(Base):
    __tablename__ = "system_logs"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    session_id = Column(String, nullable=True, index=True)
    message_id = Column(Integer, nullable=True, index=True)
    
    # Latest module/event state
    module = Column(String, nullable=True)
    level = Column(String, default="INFO")
    event_type = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    details = Column(Text, nullable=True)  # Stores JSON

    # Dedicated Execution Trace Columns
    user_query = Column(Text, nullable=True)
    tables_retrieved = Column(Text, nullable=True) # JSON list
    tables_after_reranking = Column(Text, nullable=True) # JSON list
    business_rules = Column(Text, nullable=True) # JSON list
    sample_queries = Column(Text, nullable=True) # JSON list
    generated_sql = Column(Text, nullable=True)
    validation_status = Column(String, nullable=True)
    execution_status = Column(String, nullable=True)
    error_details = Column(Text, nullable=True)

# Ensure the table is created immediately
Base.metadata.create_all(bind=engine)

def create_log_sync(session_id: str, message_id: int, user_query: str):
    """
    Synchronously create the initial log entry for a new user message.
    """
    try:
        log_entry = SystemLog(
            session_id=session_id,
            message_id=message_id,
            user_query=user_query,
            module="main",
            level="INFO",
            event_type="QUERY_START",
            message=f"Received query: {user_query}"
        )
        with SessionLocal() as db:
            db.add(log_entry)
            db.commit()
    except Exception as e:
        print(f"Failed to create log in DB: {e}")

def update_log_sync(message_id: int, **kwargs):
    """
    Synchronously update an existing log entry by message_id.
    """
    if not message_id:
        return
        
    try:
        with SessionLocal() as db:
            log_entry = db.query(SystemLog).filter(SystemLog.message_id == message_id).first()
            if not log_entry:
                # If we couldn't find the original row (maybe testing manually), create one on the fly
                log_entry = SystemLog(message_id=message_id)
                db.add(log_entry)
                
            # Automatically serialize any dicts/lists to JSON strings
            for key, value in kwargs.items():
                if hasattr(log_entry, key):
                    if isinstance(value, (dict, list)):
                        setattr(log_entry, key, json.dumps(value, default=str))
                    else:
                        setattr(log_entry, key, value)
            db.commit()
    except Exception as e:
        print(f"Failed to update log in DB: {e}")

def log_error_sync(module: str, event_type: str, error: Exception, message: str = "An error occurred", session_id: str = None, message_id: int = None, details: dict = None):
    """
    Helper to easily append errors with tracebacks to the log.
    """
    error_info = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "traceback": traceback.format_exc()
    }
    if details:
        error_info.update(details)
        
    update_log_sync(
        message_id=message_id,
        module=module,
        level="ERROR",
        event_type=event_type,
        message=message,
        error_details=error_info
    )
