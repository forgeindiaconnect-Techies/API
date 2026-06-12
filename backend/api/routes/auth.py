from fastapi import APIRouter, HTTPException, Depends, status
from datetime import datetime, timedelta, timezone
from models import (
    UserCreate, UserLogin, TokenResponse, UserResponse, 
    ProfileUpdate, PasswordChange, RefreshTokenRequest,
    ApiKeyCreate, ApiKeyResponse
)
from auth.utils import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user
)
from database import get_db
import logging
import secrets
import hashlib

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


def format_user(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        role=user.get("role", "user"),
        created_at=user.get("created_at", datetime.now(timezone.utc)),
        avatar_url=user.get("avatar_url"),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate):
    db = get_db()

    # Check existing
    existing = await db.users.find_one({"email": data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_doc = {
        "name": data.name,
        "email": data.email,
        "password_hash": hash_password(data.password),
        "role": "admin",  # First user is admin
        "created_at": datetime.now(timezone.utc),
        "disabled": False,
    }

    result = await db.users.insert_one(user_doc)
    user_doc["_id"] = str(result.inserted_id)

    token_data = {"sub": str(result.inserted_id), "email": data.email}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=format_user(user_doc),
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin):
    db = get_db()
    email = data.email.lower().strip()
    logger.info(f"Attempting login for email: '{email}'")
    
    if email == "demo@aistudio.com":
        user = await db.users.find_one({"email": email})
        if not user:
            logger.info("Demo user 'demo@aistudio.com' not found. Creating dynamically.")
            demo_user = {
                "name": "Demo User",
                "email": "demo@aistudio.com",
                "password_hash": hash_password("demo1234"),
                "role": "admin",
                "created_at": datetime.now(timezone.utc),
                "disabled": False,
            }
            result = await db.users.insert_one(demo_user)
            demo_user["_id"] = result.inserted_id
            user = demo_user
    else:
        user = await db.users.find_one({"email": email})
        
    if not user:
        logger.warning(f"Login failed: User with email '{email}' not found in database.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    password_hash = user.get("password_hash", "")
    if not password_hash:
        logger.warning(f"Login failed: User '{email}' has no password hash stored.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    is_valid = verify_password(data.password, password_hash)
    if not is_valid:
        logger.warning(f"Login failed: Password verification failed for user '{email}'.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.get("disabled"):
        logger.warning(f"Login failed: User '{email}' is disabled.")
        raise HTTPException(status_code=400, detail="Account disabled")

    logger.info(f"Login successful for user '{email}'. Updating last login time.")
    # Update last login
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.now(timezone.utc)}}
    )

    token_data = {"sub": str(user["_id"]), "email": user["email"]}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=format_user(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshTokenRequest):
    db = get_db()
    payload = decode_token(data.refresh_token, expected_type="refresh")

    user_id = payload.get("sub")
    logger.info(f"Token refresh requested for user_id (sub): {user_id}")

    # Support both string and ObjectId _id formats (MongoDB stores _id as ObjectId)
    from bson import ObjectId
    from bson.errors import InvalidId
    if user_id and len(user_id) == 24:
        try:
            user_oid = ObjectId(user_id)
            user_query = {"_id": {"$in": [user_id, user_oid]}}
        except (InvalidId, TypeError, ValueError):
            user_query = {"_id": user_id}
    else:
        user_query = {"_id": user_id}

    user = await db.users.find_one(user_query)
    if not user:
        logger.warning(f"Token refresh failed: user not found for sub: {user_id} (query: {user_query})")
        raise HTTPException(status_code=401, detail="User not found")

    token_data = {"sub": str(user["_id"]), "email": user["email"]}
    access_token = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        user=format_user(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user=Depends(get_current_user)):
    return format_user(current_user)


@router.put("/profile", response_model=UserResponse)
async def update_profile(data: ProfileUpdate, current_user=Depends(get_current_user)):
    db = get_db()
    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if updates:
        await db.users.update_one({"_id": current_user["_id"]}, {"$set": updates})
    updated = await db.users.find_one({"_id": current_user["_id"]})
    return format_user(updated)


@router.put("/password")
async def change_password(data: PasswordChange, current_user=Depends(get_current_user)):
    db = get_db()
    if not verify_password(data.current_password, current_user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"password_hash": hash_password(data.new_password)}}
    )
    return {"message": "Password updated successfully"}


@router.post("/apikey", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def generate_api_key(data: ApiKeyCreate, current_user=Depends(get_current_user)):
    db = get_db()
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    key_doc = {
        "name": data.name,
        "key_hash": key_hash,
        "key_prefix": raw_key[:4] + "..." + raw_key[-4:],
        "scopes": data.scopes,
        "rate_limit": data.rate_limit,
        "requests_count": 0,
        "status": "active",
        "user_id": str(current_user["_id"]),
        "created_at": datetime.now(timezone.utc),
    }
    
    if data.expires_in_days:
        key_doc["expires_at"] = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)
        
    result = await db.api_keys.insert_one(key_doc)
    
    # We must return an ApiKeyResponse model. We set the unhashed key only for this one-time display.
    return ApiKeyResponse(
        id=str(result.inserted_id),
        name=key_doc["name"],
        key=raw_key,
        key_prefix=key_doc["key_prefix"],
        scopes=key_doc["scopes"],
        rate_limit=key_doc["rate_limit"],
        requests_count=key_doc["requests_count"],
        status=key_doc["status"],
        user_id=key_doc["user_id"],
        created_at=key_doc["created_at"],
        expires_at=key_doc.get("expires_at"),
        allowed_datasets=key_doc.get("allowed_datasets") or [],
        allowed_models=key_doc.get("allowed_models") or [],
    )

