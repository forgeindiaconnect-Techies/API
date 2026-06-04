from fastapi import APIRouter, HTTPException, Depends, status
from datetime import datetime
from models import UserCreate, UserLogin, TokenResponse, UserResponse, ProfileUpdate, PasswordChange, RefreshTokenRequest
from auth.utils import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user
)
from database import get_db
import logging

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


def format_user(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        role=user.get("role", "user"),
        created_at=user.get("created_at", datetime.utcnow()),
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
        "created_at": datetime.utcnow(),
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
    user = await db.users.find_one({"email": data.email})

    if not user or not verify_password(data.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.get("disabled"):
        raise HTTPException(status_code=400, detail="Account disabled")

    # Update last login
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.utcnow()}}
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
    payload = decode_token(data.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    user = await db.users.find_one({"_id": user_id})
    if not user:
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
    updates = {k: v for k, v in data.dict().items() if v is not None}
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
