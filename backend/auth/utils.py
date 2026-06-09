from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import JWTError, jwt, ExpiredSignatureError
import bcrypt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import settings
from database import get_db
from bson import ObjectId
from bson.errors import InvalidId
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()


def hash_password(password: str) -> str:
    pw_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        logger.warning("verify_password called with empty hash")
        return False
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except ValueError as e:
        logger.warning(f"Invalid bcrypt hash format: {e}")
        return False
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False
 

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    to_encode["type"] = "access"
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode["exp"] = expire
    to_encode["type"] = "refresh"
    secret = settings.JWT_REFRESH_SECRET or settings.SECRET_KEY
    return jwt.encode(to_encode, secret, algorithm=settings.ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> Dict[str, Any]:
    try:
        secret = settings.SECRET_KEY if expected_type == "access" else (settings.JWT_REFRESH_SECRET or settings.SECRET_KEY)
        payload = jwt.decode(token, secret, algorithms=[settings.ALGORITHM])
        
        token_type = payload.get("type")
        if token_type != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type: expected {expected_type}, got {token_type}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except ExpiredSignatureError as e:
        logger.warning(f"JWT {expected_type} token expired: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        logger.error(f"JWT {expected_type} token validation failure: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def validate_object_id(id_str: str) -> ObjectId:
    if not id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID string cannot be empty"
        )
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ID format: '{id_str}'. Must be a 24-character hex string."
        )


async def get_current_user(
    request: Request,
):
    # First check if middleware already authenticated and set the user in state
    user = getattr(request.state, "user", None)
    if user:
        logger.info(f"get_current_user: User found in request state: {user.get('email')} (ID: {user.get('_id')})")
        return user

    # Otherwise, extract from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("get_current_user: Missing or invalid Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated: missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ")[1]
    logger.info("get_current_user: Extracting Bearer token from authorization header")
    try:
        payload = decode_token(token, expected_type="access")
        user_id = payload.get("sub")
        logger.info(f"get_current_user: Token decoded successfully. User ID (sub): {user_id}")
        if not user_id:
            logger.warning("get_current_user: Token sub payload missing user_id")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )

        db = get_db()
        if db is None:
            logger.error("get_current_user: Database connection unavailable")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection unavailable"
            )

        # Support both string and ObjectId formats for the user _id lookup
        if len(user_id) == 24:
            try:
                user_oid = ObjectId(user_id)
                user_query = {"_id": {"$in": [user_id, user_oid]}}
            except (InvalidId, TypeError, ValueError) as oid_err:
                logger.warning(f"get_current_user: Invalid user_id format in sub: '{user_id}' | Error: {oid_err}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid User ID format: '{user_id}'. Must be a 24-character hex string."
                )
        else:
            user_query = {"_id": user_id}

        logger.info(f"get_current_user: Querying database for user with query: {user_query}")
        user = await db.users.find_one(user_query)
        if not user:
            logger.warning(f"get_current_user: User not found in database for sub: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if user.get("disabled"):
            logger.warning(f"get_current_user: Account disabled for user: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account disabled"
            )

        # Set user in request state for subsequent lookups in this request
        request.state.user = user
        logger.info(f"get_current_user: Successfully authenticated user: {user.get('email')} (ID: {user_id})")
        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_current_user: Unexpected authentication dependency error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
        {"$set": {"last_used_at": datetime.now(timezone.utc)}, "$inc": {"requests_count": 1}}
    )
    return key_doc
