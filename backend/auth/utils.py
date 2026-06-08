from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import settings
from database import get_db
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()


def hash_password(password: str) -> str:
    pw_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False
 

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    to_encode["type"] = "access"
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode["exp"] = expire
    to_encode["type"] = "refresh"
    secret = settings.JWT_REFRESH_SECRET or settings.SECRET_KEY
    return jwt.encode(to_encode, secret, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    try:
        # Try primary secret key first (access tokens)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"JWT access token decode failed: {e}")
        try:
            # Fallback to refresh token secret key (refresh tokens)
            secret = settings.JWT_REFRESH_SECRET or settings.SECRET_KEY
            payload = jwt.decode(token, secret, algorithms=[settings.ALGORITHM])
            return payload
        except JWTError as re:
            logger.error(f"JWT validation failure: Both access and refresh tokens failed decoding. Details: {re}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired token: {str(re)}",
                headers={"WWW-Authenticate": "Bearer"},
            )


async def get_current_user(
    request: Request,
):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(current_user=Depends(get_current_user)):
    if current_user.get("disabled"):
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def require_admin(current_user=Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


async def verify_api_key(api_key: str) -> Optional[Dict]:
    """Verify an API key from request header"""
    import hashlib
    db = get_db()
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    key_doc = await db.api_keys.find_one({"key_hash": key_hash, "status": "active"})
    if not key_doc:
        return None

    # Update last_used
    await db.api_keys.update_one(
        {"_id": key_doc["_id"]},
        {"$set": {"last_used_at": datetime.utcnow()}, "$inc": {"requests_count": 1}}
    )
    return key_doc
