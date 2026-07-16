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

from database import init_db, get_db, Session, Message, User, Role, RefreshToken
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
    result = await db.execute(select(User).where(User.username == username))
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
    session_id: str = None

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
    role : str = None
    display_token : bool = False
    display_sql : bool = False
    user_type : int = 2
    is_active : bool = True

class UserUpdate(BaseModel):
    username: str = None
    password: str = None
    role: str = None
    display_token: bool = None
    display_sql: bool = None
    user_type: int = None
    is_active: bool = None

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

async def run_pipeline(query: str, history: list = None, message_id: int = None, allowed_access: list = None) -> dict:
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
        message_id=message_id
    )
    
    usage = response_obj.usage_metadata
    in_tok = getattr(usage, "prompt_token_count", 0)
    out_tok = getattr(usage, "candidates_token_count", 0)
    
    # Step 2: Validate SQL
    is_valid, final_sql, retry_in, retry_out = await validate_and_fix_sql(
        sql_raw, 
        query, 
        chat=chat,
        message_id=message_id,
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
    if not conn_str or conn_str == "your_sql_server_connection_string":
        raise HTTPException(status_code=500, detail="Database connection string not configured.")
        
    columns, rows = execute_query(final_sql, connection_string=conn_str, message_id=message_id)
    
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

from logger import create_log_sync, update_log_sync, log_error_sync, SystemLog

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
        create_log_sync(session_id, user_msg.id, request_model.query)

        # Fetch RoleTableAccess for current_user
        from database import RoleTableAccess
        role_id = current_user.role_id
        allowed_access = []
        if role_id is not None:
            access_result = await db.execute(select(RoleTableAccess).where(RoleTableAccess.role_id == role_id))
            access_records = access_result.scalars().all()
            for acc in access_records:
                allowed_access.append({
                    "table_name": acc.table_name.lower(),
                    "restricted_columns": json.loads(acc.restricted_columns) if acc.restricted_columns else []
                })

        # Wrap the whole pipeline in an asyncio task
        pipeline_task = asyncio.create_task(run_pipeline(request_model.query, history, user_msg.id, allowed_access))
        
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
            cost=json.dumps(result_data.get("cost"), default=json_serial) if result_data.get("cost") is not None else None
        )
        db.add(asst_msg)
        await db.commit()
        await db.refresh(asst_msg)
        
        # Relink the SystemLog to the assistant message so feedback works
        await asyncio.to_thread(update_log_sync, message_id=user_msg.id, new_message_id=asst_msg.id)
        
        result_data["message_id"] = asst_msg.id
        result_data["session_id"] = session_id
        return result_data
        
    except asyncio.CancelledError:
        print(f"\n[NVIDIA PIPELINE] Request aborted by client!")
        raise
    except Exception as e:
        print(f"\n[NVIDIA PIPELINE] UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
    result = await db.execute(
        select(Message, SystemLog.is_useful, SystemLog.user_comment)
        .outerjoin(SystemLog, Message.id == SystemLog.message_id)
        .where(Message.session_id == session_id)
        .order_by(Message.id)
    )
    rows = result.all()
    
    messages = []
    for msg, is_useful, user_comment in rows:
        msg_dict = msg.to_dict()
        msg_dict["is_useful"] = is_useful
        msg_dict["user_comment"] = user_comment
        messages.append(msg_dict)
        
    return messages

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
        
    role_id = None
    if user_data.role:
        role_result = await db.execute(select(Role).where(Role.name == user_data.role))
        db_role = role_result.scalar_one_or_none()
        if not db_role:
            raise HTTPException(status_code=400, detail=f"Role '{user_data.role}' not found")
        role_id = db_role.id

    hashed_pwd = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username, 
        hashed_password=hashed_pwd, 
        role_id=role_id,
        display_token=user_data.display_token,
        display_sql=user_data.display_sql,
        user_type=user_data.user_type,
        is_active=user_data.is_active
    )
    db.add(new_user)
    await db.commit()
    return {"status":"success","message":"User registered successfully"}

from fastapi import Response

@app.post("/api/auth/login")
async def login_user(user_data:UserCreate, response: Response, db:AsyncSession = Depends(get_db)):
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(User).options(selectinload(User.role)).where(User.username == user_data.username))
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
    
    role_name = user.role.name if user.role else None
    
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
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "role": role_name,
        "display_token": user.display_token,
        "display_sql": user.display_sql,
        "user_type": user.user_type
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
    result = await db.execute(select(User).options(selectinload(User.role)))
    users = result.scalars().all()
    return [{
        "id": u.id,
        "username": u.username,
        "role": u.role.name if u.role else None,
        "display_token": u.display_token,
        "display_sql": u.display_sql,
        "user_type": u.user_type,
        "is_active": u.is_active
    } for u in users]

@app.put("/api/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.user_type != 1:
        raise HTTPException(status_code=403, detail="Only Admins can edit users.")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user_data.username is not None:
        user.username = user_data.username
    if user_data.password:
        user.hashed_password = get_password_hash(user_data.password)
    if user_data.role is not None:
        role_result = await db.execute(select(Role).where(Role.name == user_data.role))
        db_role = role_result.scalar_one_or_none()
        if not db_role:
            raise HTTPException(status_code=400, detail=f"Role '{user_data.role}' not found")
        user.role_id = db_role.id
    if user_data.display_token is not None:
        user.display_token = user_data.display_token
    if user_data.display_sql is not None:
        user.display_sql = user_data.display_sql
    if user_data.user_type is not None:
        user.user_type = user_data.user_type
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
        
    await db.commit()
    return {"status": "success", "message": "User updated successfully"}

@app.get("/api/roles")
async def get_roles(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role))
    roles = result.scalars().all()
    return [{"id": r.id, "name": r.name} for r in roles]


@app.get("/api/auth/me")
async def get_current_user_info(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(User).options(selectinload(User.role)).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    role_name = user.role.name if user and user.role else None
    return {
        "username": current_user.username, 
        "role": role_name,
        "display_token": user.display_token,
        "display_sql": user.display_sql,
        "user_type": user.user_type
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
