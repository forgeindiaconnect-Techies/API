from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
import secrets
import hashlib
import logging

from models import ApiKeyCreate, ApiKeyResponse
from auth.utils import get_current_user
from database import get_db

router = APIRouter(prefix="/api-keys", tags=["API Keys"])
logger = logging.getLogger(__name__)


def generate_api_key() -> tuple[str, str, str]:
    """Returns (full_key, prefix, hash)"""
    key = f"sk-{secrets.token_urlsafe(32)}"
    prefix = key[:12]
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, prefix, key_hash


def fmt_key(k: dict, show_key: bool = False) -> dict:
    return {
        "id": str(k["_id"]),
        "name": k["name"],
        "key": k.get("_full_key") if show_key else None,
        "key_prefix": k.get("key_prefix", "sk-..."),
        "scopes": k.get("scopes", ["chat"]),
        "rate_limit": k.get("rate_limit", 1000),
        "requests_count": k.get("requests_count", 0),
        "status": k.get("status", "active"),
        "user_id": k.get("user_id", ""),
        "created_at": k.get("created_at", datetime.utcnow()),
        "last_used_at": k.get("last_used_at"),
        "expires_at": k.get("expires_at"),
    }


@router.get("/")
async def list_api_keys(current_user=Depends(get_current_user)):
    db = get_db()
    keys = []
    async for k in db.api_keys.find({"user_id": str(current_user["_id"])}):
        keys.append(fmt_key(k))
    return sorted(keys, key=lambda x: x["created_at"], reverse=True)


@router.post("/")
async def create_api_key(data: ApiKeyCreate, current_user=Depends(get_current_user)):
    db = get_db()
    full_key, prefix, key_hash = generate_api_key()

    expires_at = None
    if data.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=data.expires_in_days)

    doc = {
        "name": data.name,
        "key_hash": key_hash,
        "key_prefix": prefix,
        "scopes": data.scopes,
        "rate_limit": data.rate_limit,
        "requests_count": 0,
        "status": "active",
        "user_id": str(current_user["_id"]),
        "created_at": datetime.utcnow(),
        "expires_at": expires_at,
    }

    result = await db.api_keys.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    doc["_full_key"] = full_key  # Only sent once

    return fmt_key(doc, show_key=True)


@router.delete("/{key_id}")
async def revoke_api_key(key_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    k = await db.api_keys.find_one({"_id": key_id, "user_id": str(current_user["_id"])})
    if not k:
        raise HTTPException(status_code=404, detail="API key not found")
    await db.api_keys.update_one({"_id": key_id}, {"$set": {"status": "revoked"}})
    return {"message": "API key revoked"}


@router.post("/{key_id}/rotate")
async def rotate_api_key(key_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    k = await db.api_keys.find_one({"_id": key_id, "user_id": str(current_user["_id"])})
    if not k:
        raise HTTPException(status_code=404, detail="API key not found")

    full_key, prefix, key_hash = generate_api_key()
    await db.api_keys.update_one(
        {"_id": key_id},
        {"$set": {
            "key_hash": key_hash,
            "key_prefix": prefix,
            "requests_count": 0,
            "created_at": datetime.utcnow(),
        }}
    )
    k["_id"] = key_id
    k["key_prefix"] = prefix
    k["_full_key"] = full_key
    return fmt_key(k, show_key=True)


@router.get("/{key_id}/usage")
async def get_key_usage(key_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    k = await db.api_keys.find_one({"_id": key_id, "user_id": str(current_user["_id"])})
    if not k:
        raise HTTPException(status_code=404, detail="API key not found")

    return {
        "key_id": key_id,
        "requests_count": k.get("requests_count", 0),
        "rate_limit": k.get("rate_limit", 1000),
        "usage_percent": round(k.get("requests_count", 0) / k.get("rate_limit", 1000) * 100, 2),
        "daily_usage": [
            {"date": f"2024-01-{14 - i}", "requests": max(0, 100 - i * 8 + (i % 3) * 20)}
            for i in range(7)
        ],
    }
