import os
import time
import traceback
from fastapi import FastAPI, HTTPException, Request,Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import asyncio
from transformers import pipeline

from sql_gen import generate_sql
from validator import validate_and_fix_sql
from execute import execute_query
from expense import calculate_cost
from embedder import get_m3_model
import pandas as pd
from analytics.analyzer import generate_analytical_summary
from analytics.analyzer_v2 import generate_visual_summary

from dotenv import load_dotenv
from sqlalchemy.future import select
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
import json
import uuid

from typing import Optional
from database import init_db, get_db, Session, Message, User, Role, RefreshToken, DBMaster, UserDatabaseAccess
from auth import get_password_hash, create_access_token, verify_password, decode_access_token, create_refresh_token, REFRESH_TOKEN_EXPIRE_MINS, ACCESS_TOKEN_EXPIRE_MINS
from fastapi.security import OAuth2PasswordBearer

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)
conn_str = os.getenv("DB_CONNECTION_STRING")
cors_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
async def get_current_user(request: Request, token: str = Depends(oauth2_scheme),db:AsyncSession=Depends(get_db)) -> User:
    credentials_exception = HTTPException(status_code=401,detail="could not validate credentials",
    headers ={"WWW-authenticate":"Bearer"},
    )
    
    actual_token = request.cookies.get("access_token") or token
    if not actual_token:
        raise credentials_exception
        
    if actual_token.startswith("Bearer "):
        actual_token = actual_token.split(" ")[1]
        
    payload = decode_access_token(actual_token)
    if payload is None:
        raise credentials_exception
    
    if payload.get("type") != "access":
        raise credentials_exception
        
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(User).options(selectinload(User.roles)).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    return user

async def get_current_user_optional(request: Request, token: str = Depends(oauth2_scheme),db:AsyncSession=Depends(get_db)) -> User:
    try:
        return await get_current_user(request, token, db)
    except HTTPException:
        return None

class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    db_id: Optional[int] = None

class MessageUpdateRequest(BaseModel):
    analysis: dict = None
    visual_spec: dict = None
    cost: dict = None

class AnalyzeDataRequest(BaseModel):
    query: str
    data: list[dict]
    message_id: int = None

class UserCreate(BaseModel):
    username : str
    password : str
    roles : list[str] = []
    display_token : bool = False
    display_sql : bool = False
    user_type : int = 2
    is_active : bool = True
    allowed_databases: list[int] = []

class UserUpdate(BaseModel):
    username: str = None
    password: str = None
    roles: list[str] = None
    display_token: bool = None
    display_sql: bool = None
    user_type: int = None
    is_active: bool = None
    allowed_databases: list[int] = None

class FeedbackRequest(BaseModel):
    is_useful: bool = None
    user_comment: str = None
nli_classifier = None

def get_nli_classifier():
    global nli_classifier
    if nli_classifier is None:
        print("Loading NLI model for intent classification...")
        nli_classifier = pipeline(
            "zero-shot-classification",
            model="cross-encoder/nli-deberta-v3-small",
            local_files_only=True
        )
    return nli_classifier

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing Database...")
    await init_db()
    print("Warming up BGE-M3 model on startup...")
    get_m3_model()
    print("Warming up NLI model on startup...")
    get_nli_classifier()
    yield
    print("Shutting down...")

app = FastAPI(title="Text to SQL API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def run_pipeline(query: str, history: list = None, log_id: int = None, allowed_access: list = None, connection_string: str = None) -> dict:
    # Step 0: Intent Classification (NLI)
    classifier = get_nli_classifier()
    
    import os
    current_dir = os.path.dirname(__file__)
    
    try:
        with open(os.path.join(current_dir, "intent_valid.txt"), "r", encoding="utf-8") as f:
            valid_intent = f.read().strip()
    except FileNotFoundError:
            valid_intent = "A request for Enterprise ERP database data, procurement analysis, OR a direct contextual follow-up or imperative command to modify the previous query (e.g., 'add amount', 'do this for last year', 'do that instead', 'sort it', 'group by month', 'show me X', 'change it to Y')."
        
    try:
        with open(os.path.join(current_dir, "intent_fallback.txt"), "r", encoding="utf-8") as f:
            fallback_intent = f.read().strip()
    except FileNotFoundError:
            fallback_intent = "A general greeting, small talk, or a request completely unrelated to business data or the ongoing conversation (e.g., 'hello', 'weather', 'write a poem')."        
    candidate_labels = [valid_intent, fallback_intent]
    
    # Run the classification
    nli_result = classifier(query, candidate_labels)
    top_intent = nli_result['labels'][0]
    
    valid_index = nli_result['labels'].index(valid_intent)
    valid_score = nli_result['scores'][valid_index]
    
    print(f"\n[NLI INTENT] Query: '{query}'")
    print(f"[NLI INTENT] Predicted Intent: {top_intent} (Scores: {nli_result['scores']})")
    
    if top_intent != valid_intent or valid_score < 0.5:
        # Fallback for small talk or unrelated questions
        return {
            "status": "success",
            "explanation": "I apologize, I am an ERP procurement analytics assistant and am not intended for this task.",
            "sql": None,
            "original_sql": None,
            "data": [],
            "cost": None
        }

    # Step 1: Generate SQL
    sql_raw, response_obj, chat, full_prompt, explanation = await generate_sql(
        query, 
        return_response=True,
        history=history,
        log_id=log_id
    )
    
    usage = response_obj.usage_metadata
    in_tok = getattr(usage, "prompt_token_count", 0)
    out_tok = getattr(usage, "candidates_token_count", 0)
    
    # Step 2: Validate SQL
    is_valid, final_sql, retry_in, retry_out = await validate_and_fix_sql(
        sql_raw, 
        query, 
        chat=chat,
        log_id=log_id,
        allowed_access=allowed_access
    )
    in_tok += retry_in
    out_tok += retry_out
    
    if not is_valid:
        if final_sql.startswith("AUTH_ERROR:"):
            return {
                "status": "error",
                "explanation": final_sql.replace("AUTH_ERROR: ", ""),
                "sql": None,
                "original_sql": sql_raw,
                "data": [],
                "cost": calculate_cost(in_tok, out_tok)
            }
        raise HTTPException(status_code=400, detail="Query validation failed. Unable to safely generate SQL.")
        
    # Step 3: Execute SQL
    target_conn_str = connection_string or conn_str
    if not target_conn_str or target_conn_str == "your_sql_server_connection_string":
        raise HTTPException(status_code=500, detail="Database connection string not configured.")
        
    columns, rows = execute_query(final_sql, connection_string=target_conn_str, log_id=log_id)
    
    # Calculate cost
    cost_info = calculate_cost(in_tok, out_tok)
    
    return {
        "status": "success",
        "explanation": explanation,
        "sql": final_sql,
        "original_sql": sql_raw if sql_raw != final_sql else None,
        "data": rows,
        "cost": cost_info
    }

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from logger import create_log_sync, update_log_sync_by_id, log_error_sync, SystemLog

@app.post("/api/ask")
async def ask_question(request_model: QueryRequest, request: Request,current_user:User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        session_id = request_model.session_id
        if not session_id:
            # Create a new session if none provided
            session_id = str(uuid.uuid4())
            new_session = Session(id=session_id,user_id = current_user.id, title="New Chat")
            db.add(new_session)
            await db.commit()
        else:
            # Fetch the session 
            sess_result = await db.execute(select(Session).where(Session.id == session_id, Session.user_id==current_user.id))
            sess = sess_result.scalar_one_or_none()
            if not sess:
                raise HTTPException(status_code=403, detail="Not Authorized to access this session")
                
        from sqlalchemy.orm import defer
        # Fetch history from DB without loading heavy JSON columns
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.id)
            .options(
                defer(Message.data),
                defer(Message.cost),
                defer(Message.analysis),
                defer(Message.visual_spec)
            )
        )
        messages = result.scalars().all()
        
        user_msg_count = sum(1 for m in messages if m.role == 'user')
        if user_msg_count >= 10:
            raise HTTPException(status_code=400, detail="This session has reached the maximum limit of 10 questions. Please start a new chat.")
        
        # If this is the first message in the session, update the session title
        if not messages and session_id:
            sess_result = await db.execute(select(Session).where(Session.id == session_id))
            sess = sess_result.scalar_one_or_none()
            if sess:
                words = request_model.query.split()
                sess.title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
                await db.commit()
        
        successfulPairs = []
        currentUserMsg = None
        for msg in messages:
            if msg.role == 'user':
                currentUserMsg = msg.content
            elif msg.role == 'assistant' and msg.type == 'success' and currentUserMsg:
                successfulPairs.append({"question": currentUserMsg, "sql": msg.sql})
                currentUserMsg = None
                
        history = successfulPairs[-3:] # Sliding window
        
        # Save user message to DB
        user_msg = Message(session_id=session_id, role="user", content=request_model.query)
        db.add(user_msg)
        await db.commit()
        await db.refresh(user_msg)
        
        # Initiate the single-row log trace for this query
        log_id = create_log_sync(session_id, user_msg.id, request_model.query)

        # Fetch RoleTableAccess for current_user
        from database import RoleTableAccess
        role_ids = [r.id for r in current_user.roles] if current_user.roles else []
        allowed_access = []
        if role_ids:
            access_result = await db.execute(select(RoleTableAccess).where(RoleTableAccess.role_id.in_(role_ids)))
            access_records = access_result.scalars().all()
            
            seen_tables = set()
            for acc in access_records:
                tname = acc.table_name.lower()
                if tname not in seen_tables:
                    seen_tables.add(tname)
                    allowed_access.append({
                        "table_name": tname,
                        "restricted_columns": json.loads(acc.restricted_columns) if acc.restricted_columns else []
                    })

        # Determine connection string
        target_conn_string = None
        actual_db_id = None
        if request_model.db_id:
            # Check if user has access
            db_access_result = await db.execute(select(UserDatabaseAccess).where(UserDatabaseAccess.user_id == current_user.id, UserDatabaseAccess.db_id == request_model.db_id))
            if not db_access_result.scalar_one_or_none() and current_user.user_type != 1:
                return {"status": "error", "explanation": "You don't have access to this database. Please contact the admin."}
            db_result = await db.execute(select(DBMaster).where(DBMaster.id == request_model.db_id))
            db_obj = db_result.scalar_one_or_none()
            if db_obj:
                target_conn_string = db_obj.connection_string
                actual_db_id = db_obj.id
        elif current_user.user_type != 1:
            # If no db_id provided but user is not admin, fallback to their first allowed DB
            db_access_result = await db.execute(select(UserDatabaseAccess).where(UserDatabaseAccess.user_id == current_user.id).limit(1))
            first_access = db_access_result.scalar_one_or_none()
            if first_access:
                db_result = await db.execute(select(DBMaster).where(DBMaster.id == first_access.db_id))
                db_obj = db_result.scalar_one_or_none()
                if db_obj:
                    target_conn_string = db_obj.connection_string
                    actual_db_id = db_obj.id
            else:
                return {"status": "error", "explanation": "You don't have access to any database. Please contact the admin."}

        # Check if we have any valid connection string to use
        if not target_conn_string and (not conn_str or conn_str == "your_sql_server_connection_string"):
            return {"status": "error", "explanation": "Database connection string not configured. Please contact the admin."}

        # Wrap the whole pipeline in an asyncio task
        pipeline_task = asyncio.create_task(run_pipeline(request_model.query, history, log_id, allowed_access, target_conn_string))
        
        # Poll for client disconnect
        while not pipeline_task.done():
            if await request.is_disconnected():
                pipeline_task.cancel()
                print("\n[NVIDIA PIPELINE] Request aborted by client disconnect!")
                return {}
            await asyncio.sleep(0.5)
            
        result_data = await pipeline_task
        
        from decimal import Decimal
        from datetime import datetime, date
        def json_serial(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        # Save assistant message to DB
        asst_msg = Message(
            session_id=session_id,
            role="assistant",
            type=result_data.get("status"),
            query=request_model.query,
            content=result_data.get("explanation") if result_data.get("status") == "error" else None,
            sql=result_data.get("sql"),
            original_sql=result_data.get("original_sql"),
            explanation=result_data.get("explanation") if result_data.get("status") == "success" else None,
            data=json.dumps(result_data.get("data"), default=json_serial) if result_data.get("data") is not None else None,
            cost=json.dumps(result_data.get("cost"), default=json_serial) if result_data.get("cost") is not None else None,
            db_id=actual_db_id
        )
        db.add(asst_msg)
        await db.commit()
        await db.refresh(asst_msg)
        
        # Relink the SystemLog to the assistant message so feedback works
        from logger import update_log_sync_by_id
        await asyncio.to_thread(update_log_sync_by_id, log_id=log_id, new_message_id=asst_msg.id)
        
        result_data["message_id"] = asst_msg.id
        result_data["session_id"] = session_id
        result_data["db_id"] = actual_db_id
        result_data["log_id"] = log_id
        return result_data
        
    except asyncio.CancelledError:
        print(f"\n[NVIDIA PIPELINE] Request aborted by client!")
        raise
    except Exception as e:
        print(f"\n[NVIDIA PIPELINE] UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        
        # Save error message to DB so frontend gets a valid message_id for feedback
        error_str = str(e)
        asst_msg = Message(
            session_id=session_id,
            role="assistant",
            type="error",
            query=request_model.query,
            content=error_str,
            db_id=actual_db_id if 'actual_db_id' in locals() else None
        )
        db.add(asst_msg)
        await db.commit()
        await db.refresh(asst_msg)
        
        # Update system log with the error and link it to the newly created error message
        from logger import update_log_sync_by_id, log_error_sync
        await asyncio.to_thread(update_log_sync_by_id, log_id=log_id, new_message_id=asst_msg.id)
        await asyncio.to_thread(log_error_sync, "main", "PIPELINE_ERROR", e, log_id=log_id)
        
        return {
            "status": "error",
            "explanation": error_str,
            "message_id": asst_msg.id,
            "session_id": session_id,
            "log_id": log_id
        }

@app.post("/api/analyze")
async def analyze_data(request_model: AnalyzeDataRequest, current_user: User = Depends(get_current_user)):
    if not request_model.data:
        return {"status": "error", "type": "error", "content": "No data provided for analysis."}
        
    df = pd.DataFrame(request_model.data)
    result = await generate_analytical_summary(df, request_model.query, message_id=request_model.message_id)
    return result

@app.post("/api/analyze_v2")
async def analyze_data_v2(request_model: AnalyzeDataRequest, current_user: User = Depends(get_current_user)):
    if not request_model.data:
        return {"status": "error", "type": "error", "content": "No data provided for visual analysis."}
        
    df = pd.DataFrame(request_model.data)
    result = await generate_visual_summary(df, request_model.query, message_id=request_model.message_id)
    return result

@app.get("/api/sessions")
async def get_sessions(current_user:User = Depends(get_current_user),db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.user_id==current_user.id).order_by(Session.created_at.desc()).limit(50))
    sessions = result.scalars().all()
    return [{"id": s.id, "title": s.title, "date": s.created_at.isoformat()} for s in sessions]

@app.post("/api/sessions")
async def create_session(current_user:User = Depends(get_current_user),db: AsyncSession = Depends(get_db)):
    session_id = str(uuid.uuid4())
    new_session = Session(id=session_id, user_id=current_user.id, title="New Chat")
    db.add(new_session)
    await db.commit()
    return {"id": session_id, "title": "New Chat"}

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str,current_user:User=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id, Session.user_id == current_user.id))
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404,detail="session not found")
    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.execute(delete(Session).where(Session.id == session_id))
    await db.commit()
    return {"status":"success"}

@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str,current_user:User=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id,Session.user_id == current_user.id))
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404,detail="session not found") 
    from sqlalchemy import and_
    result = await db.execute(
        select(Message, SystemLog.is_useful, SystemLog.user_comment, SystemLog.id.label("log_id"))
        .outerjoin(SystemLog, and_(Message.id == SystemLog.message_id, Message.session_id == SystemLog.session_id))
        .where(Message.session_id == session_id)
        .order_by(Message.id)
    )
    rows = result.all()
    
    messages = []
    for msg, is_useful, user_comment, log_id in rows:
        msg_dict = msg.to_dict()
        msg_dict["is_useful"] = is_useful
        msg_dict["user_comment"] = user_comment
        msg_dict["log_id"] = log_id
        messages.append(msg_dict)
        
    return messages

@app.get("/api/logs")
async def get_system_logs(
    start_date: str = None, 
    end_date: str = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.user_type != 1:
        raise HTTPException(status_code=403, detail="Only Admins can view system logs.")
    
    from logger import SystemLog
    from sqlalchemy import select, func
    from database import Session as DBSession, User as DBUser
    
    try:
        # Build the base query for counting
        count_query = select(func.count()).select_from(SystemLog)
        
        # Build the base query for data
        data_query = select(SystemLog, DBUser.username)\
            .outerjoin(DBSession, SystemLog.session_id == DBSession.id)\
            .outerjoin(DBUser, DBSession.user_id == DBUser.id)
            
        if start_date:
            from datetime import datetime
            try:
                dt_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                count_query = count_query.where(SystemLog.timestamp >= dt_start)
                data_query = data_query.where(SystemLog.timestamp >= dt_start)
            except ValueError:
                pass
                
        if end_date:
            from datetime import datetime
            try:
                dt_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                count_query = count_query.where(SystemLog.timestamp <= dt_end)
                data_query = data_query.where(SystemLog.timestamp <= dt_end)
            except ValueError:
                pass
        
        total_count = await db.scalar(count_query)
        
        # Pagination
        offset = (page - 1) * page_size
        data_query = data_query.order_by(SystemLog.timestamp.desc()).offset(offset).limit(page_size)
        
        result_rows = await db.execute(data_query)
        rows = result_rows.all()
        
        # Format output
        result = []
        from datetime import timedelta
        for log, username in rows:
            result.append({
                "id": log.id,
                "date": (log.timestamp + timedelta(hours=5, minutes=30)).isoformat() if log.timestamp else None,
                "user": username or "Unknown",
                "question": log.user_query,
                "rating": log.is_useful,
                "comment": log.user_comment
            })
            
        return {
            "data": result,
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to fetch logs")

@app.put("/api/messages/{message_id}")
async def update_message(message_id: int, request_model: MessageUpdateRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Message).where(Message.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
        
    if request_model.analysis is not None:
        msg.analysis = json.dumps(request_model.analysis)
    if request_model.visual_spec is not None:
        msg.visual_spec = json.dumps(request_model.visual_spec)
    if request_model.cost is not None:
        if msg.cost:
            current_cost = json.loads(msg.cost)
            current_cost["input_tokens"] = current_cost.get("input_tokens", 0) + request_model.cost.get("input_tokens", 0)
            current_cost["output_tokens"] = current_cost.get("output_tokens", 0) + request_model.cost.get("output_tokens", 0)
            current_cost["cost_inr"] = current_cost.get("cost_inr", 0.0) + request_model.cost.get("cost_inr", 0.0)
            msg.cost = json.dumps(current_cost)
        else:
            msg.cost = json.dumps(request_model.cost)
        
    await db.commit()
    return {"status": "success"}

@app.post("/api/messages/{message_id}/feedback")
async def submit_feedback(message_id: int, request_model: FeedbackRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    kwargs = {}
    if request_model.is_useful is not None:
        kwargs["is_useful"] = request_model.is_useful
    if request_model.user_comment is not None:
        kwargs["user_comment"] = request_model.user_comment
        
    if kwargs:
        import asyncio
        # message_id here is the messages table PK, not system_logs.id
        # Use update_log_sync which looks up by SystemLog.message_id column
        from logger import update_log_sync
        await asyncio.to_thread(update_log_sync, message_id=message_id, **kwargs)
        
    return {"status": "success"}
@app.post("/api/auth/register")
async def register_user(user_data:UserCreate, current_user: User = Depends(get_current_user_optional), db:AsyncSession=Depends(get_db)):
    from sqlalchemy import func
    total_users = await db.scalar(select(func.count()).select_from(User))
    
    if total_users > 0:
        if not current_user or current_user.user_type != 1:
            raise HTTPException(status_code=403, detail="Only Admins can register new users.")
            
    result = await db.execute(select(User).where(User.username==user_data.username))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=400,detail="Username already registered")
        
    roles_list = []
    if user_data.roles:
        for role_name in user_data.roles:
            role_result = await db.execute(select(Role).where(Role.name == role_name))
            db_role = role_result.scalar_one_or_none()
            if not db_role:
                raise HTTPException(status_code=400, detail=f"Role '{role_name}' not found")
            roles_list.append(db_role)

    hashed_pwd = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username, 
        hashed_password=hashed_pwd, 
        roles=roles_list,
        display_token=user_data.display_token,
        display_sql=user_data.display_sql,
        user_type=user_data.user_type,
        is_active=user_data.is_active
    )
    db.add(new_user)
    await db.flush()
    if user_data.allowed_databases:
        for db_id in user_data.allowed_databases:
            db.add(UserDatabaseAccess(user_id=new_user.id, db_id=db_id))
    await db.commit()
    return {"status":"success","message":"User registered successfully"}

from fastapi import Response

@app.post("/api/auth/login")
async def login_user(user_data:UserCreate, response: Response, db:AsyncSession = Depends(get_db)):
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(User).options(selectinload(User.roles), selectinload(User.database_access).selectinload(UserDatabaseAccess.db)).where(User.username == user_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_data.password,user.hashed_password):
        raise HTTPException(status_code = 401,detail="Incorrect username or password")
        
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    access_token = create_access_token(data={"sub":user.username})
    refresh_token = create_refresh_token(data={"sub":user.username})
    
    from datetime import datetime, timedelta, timezone
    expire_date = datetime.now(timezone.utc) + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINS)
    db_refresh_token = RefreshToken(user_id=user.id, token=refresh_token, expires_at=expire_date)
    db.add(db_refresh_token)
    await db.commit()
    
    role_names = [r.name for r in user.roles] if user.roles else []
    
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINS*60,
        expires=ACCESS_TOKEN_EXPIRE_MINS*60,
        samesite="lax",
        secure=False,
    )
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=REFRESH_TOKEN_EXPIRE_MINS*60,
        expires=REFRESH_TOKEN_EXPIRE_MINS*60,
        samesite="lax",
        secure=False,
    )
    
    allowed_dbs = []
    for acc in user.database_access:
        if acc.db:
            allowed_dbs.append({"id": acc.db.id, "name": acc.db.name})
            
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "roles": role_names,
        "display_token": user.display_token,
        "display_sql": user.display_sql,
        "user_type": user.user_type,
        "allowed_databases": allowed_dbs
    }

@app.post("/api/auth/refresh")
async def refresh_access_token(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
        
    payload = decode_access_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
        
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")
        
    result = await db.execute(select(RefreshToken).where(RefreshToken.token == refresh_token))
    db_token = result.scalar_one_or_none()
    
    if not db_token or db_token.revoked:
        raise HTTPException(status_code=401, detail="Refresh token revoked or invalid")
        
    new_access_token = create_access_token(data={"sub": username})
    new_refresh_token = create_refresh_token(data={"sub": username})
    from datetime import datetime, timedelta, timezone
    expire_date = datetime.now(timezone.utc) + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINS)
    
    db_token.revoked = True
    new_db_token = RefreshToken(user_id=db_token.user_id, token=new_refresh_token, expires_at=expire_date)
    db.add(new_db_token)
    await db.commit()
    
    response.set_cookie(
        key="access_token",
        value=f"Bearer {new_access_token}",
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINS*60,
        expires=ACCESS_TOKEN_EXPIRE_MINS*60,
        samesite="lax",
        secure=False,
    )
    
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        max_age=REFRESH_TOKEN_EXPIRE_MINS*60,
        expires=REFRESH_TOKEN_EXPIRE_MINS*60,
        samesite="lax",
        secure=False,
    )
    
    return {"status": "success", "message": "Tokens refreshed"}

@app.post("/api/auth/logout")
async def logout_user(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        result = await db.execute(select(RefreshToken).where(RefreshToken.token == refresh_token))
        db_token = result.scalar_one_or_none()
        if db_token:
            db_token.revoked = True
            await db.commit()

    response.delete_cookie("access_token", httponly=True, samesite="lax")
    response.delete_cookie("refresh_token", httponly=True, samesite="lax")
    return {"status": "success", "message": "Logged out successfully"}

@app.get("/api/users")
async def get_users(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.user_type != 1:
        raise HTTPException(status_code=403, detail="Only Admins can view users.")
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(User).options(selectinload(User.roles), selectinload(User.database_access).selectinload(UserDatabaseAccess.db)))
    users = result.scalars().all()
    return [{
        "id": u.id,
        "username": u.username,
        "roles": [r.name for r in u.roles] if u.roles else [],
        "display_token": u.display_token,
        "display_sql": u.display_sql,
        "user_type": u.user_type,
        "is_active": u.is_active,
        "allowed_databases": [acc.db_id for acc in u.database_access]
    } for u in users]

@app.put("/api/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.user_type != 1:
        raise HTTPException(status_code=403, detail="Only Admins can edit users.")
    
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(User).options(selectinload(User.roles)).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user_data.username is not None:
        user.username = user_data.username
    if user_data.password:
        user.hashed_password = get_password_hash(user_data.password)
    if user_data.roles is not None:
        roles_list = []
        for role_name in user_data.roles:
            role_result = await db.execute(select(Role).where(Role.name == role_name))
            db_role = role_result.scalar_one_or_none()
            if not db_role:
                raise HTTPException(status_code=400, detail=f"Role '{role_name}' not found")
            roles_list.append(db_role)
        user.roles = roles_list
    if user_data.display_token is not None:
        user.display_token = user_data.display_token
    if user_data.display_sql is not None:
        user.display_sql = user_data.display_sql
    if user_data.user_type is not None:
        user.user_type = user_data.user_type
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
        
    if user_data.allowed_databases is not None:
        await db.execute(delete(UserDatabaseAccess).where(UserDatabaseAccess.user_id == user_id))
        for db_id in user_data.allowed_databases:
            db.add(UserDatabaseAccess(user_id=user_id, db_id=db_id))
            
    await db.commit()
    return {"status": "success", "message": "User updated successfully"}

@app.get("/api/roles")
async def get_roles(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role))
    roles = result.scalars().all()
    return [{"id": r.id, "name": r.name} for r in roles]

class DBMasterCreate(BaseModel):
    name: str
    connection_string: str

class DBMasterUpdate(BaseModel):
    name: str = None
    connection_string: str = None

@app.get("/api/databases")
async def get_databases(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.user_type != 1:
        raise HTTPException(status_code=403, detail="Only Admins can view databases.")
    result = await db.execute(select(DBMaster))
    dbs = result.scalars().all()
    return [{"id": d.id, "name": d.name, "connection_string": d.connection_string} for d in dbs]

@app.post("/api/databases")
async def create_database(db_data: DBMasterCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.user_type != 1:
        raise HTTPException(status_code=403, detail="Only Admins can create databases.")
    result = await db.execute(select(DBMaster).where(DBMaster.name == db_data.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Database name already exists")
    new_db = DBMaster(name=db_data.name, connection_string=db_data.connection_string)
    db.add(new_db)
    await db.commit()
    return {"status": "success", "message": "Database added"}

@app.put("/api/databases/{db_id}")
async def update_database(db_id: int, db_data: DBMasterUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.user_type != 1:
        raise HTTPException(status_code=403, detail="Only Admins can edit databases.")
    result = await db.execute(select(DBMaster).where(DBMaster.id == db_id))
    db_obj = result.scalar_one_or_none()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Database not found")
    if db_data.name is not None:
        db_obj.name = db_data.name
    if db_data.connection_string is not None:
        db_obj.connection_string = db_data.connection_string
    await db.commit()
    return {"status": "success", "message": "Database updated"}

@app.delete("/api/databases/{db_id}")
async def delete_database(db_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.user_type != 1:
        raise HTTPException(status_code=403, detail="Only Admins can delete databases.")
    result = await db.execute(select(DBMaster).where(DBMaster.id == db_id))
    db_obj = result.scalar_one_or_none()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Database not found")
    await db.execute(delete(DBMaster).where(DBMaster.id == db_id))
    await db.commit()
    return {"status": "success", "message": "Database deleted"}


@app.get("/api/auth/me")
async def get_current_user_info(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(User).options(selectinload(User.roles), selectinload(User.database_access).selectinload(UserDatabaseAccess.db)).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    role_names = [r.name for r in user.roles] if user and user.roles else []
    
    allowed_dbs = []
    if user:
        for acc in user.database_access:
            if acc.db:
                allowed_dbs.append({"id": acc.db.id, "name": acc.db.name})
                
    return {
        "username": current_user.username, 
        "roles": role_names,
        "display_token": user.display_token,
        "display_sql": user.display_sql,
        "user_type": user.user_type,
        "allowed_databases": allowed_dbs
    }
if __name__ == "__main__":
    import uvicorn
    import json
    import os

    config_path = os.path.join(os.path.dirname(__file__), "server_config.json")
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {"host": "0.0.0.0", "port": 8000, "reload": True, "workers": 1}

    uvicorn.run(
        "main:app",
        host=config.get("host", "0.0.0.0"),
        port=config.get("port", 8000),
        reload=config.get("reload", True),
        workers=config.get("workers", 1)
    )
