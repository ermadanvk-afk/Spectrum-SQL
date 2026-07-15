# this will act as the auth, like converting the pass
# like pass123 to dsfsp24952 using bcrpyt
# then verifying the password:compare user password against the user
# password against the stored hash. 
# then creating json web tokens, signed tokens containing user's details
# and an expiration time eg. 30 mins
# decoding incoming jwt, for their validity and expiration. 
import os
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__),".env")
load_dotenv(env_path)
secret_key = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINS = 180
REFRESH_TOKEN_EXPIRE_MINS = 360

def get_password_hash(password:str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt() # random string added before hashing
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')
def verify_password(plan_password:str, hashed_password:str) -> bool:
    try:
        return bcrypt.checkpw(plan_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINS)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt
def decode_access_token(token:str)->dict|None:
    try:
        payload = jwt.decode(token,secret_key,algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


