from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
import secrets
import hashlib
import logging
from typing import Optional

from models import ApiKeyCreate, ApiKeyResponse, ApiKeyUpdate
from auth.utils import get_current_user
from database import get_db
from bson import ObjectId
from bson.errors import InvalidId

router = APIRouter(prefix="/api-keys", tags=["API Keys"])
logger = logging.getLogger(__name__)


def generate_api_key() -> tuple[str, str, str]:
    """Returns (full_key, prefix, hash)"""
    # Generate key using secrets.token_urlsafe(32) prefixed with sk- for public endpoint routing
    key = f"sk-{secrets.token_urlsafe(32)}"
    prefix = key[:8]
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, prefix, key_hash


def fmt_key(k: dict, show_key: bool = False, raw_key: str = None) -> dict:
    # Handle dates mapping safely
    created_at = k.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            created_at = datetime.utcnow()
    elif not isinstance(created_at, datetime):
        created_at = datetime.utcnow()

    last_used = k.get("last_used") or k.get("last_used_at")
    if isinstance(last_used, str):
        try:
            last_used = datetime.fromisoformat(last_used.replace("Z", "+00:00"))
        except ValueError:
            pass

    expires_at = k.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            pass

    return {
        "id": str(k["_id"]),
        "name": k.get("name"),
        "key": raw_key if show_key else None,
        "key_prefix": k.get("key_prefix"),
        "scopes": k.get("scopes", ["chat"]),
        "rate_limit": k.get("rate_limit", 1000),
        "requests_count": k.get("requests_count", 0),
        "status": "active" if k.get("is_active", True) else "revoked",
        "user_id": k.get("user_id", ""),
        "created_at": created_at,
        "last_used_at": last_used,
        "expires_at": expires_at,
        "is_active": k.get("is_active", True),
        "last_used": last_used,
    }


@router.get("")
async def list_api_keys(current_user=Depends(get_current_user)):
    db = get_db()
    keys = []
    async for k in db.api_keys.find({"user_id": str(current_user["_id"])}):
        keys.append(fmt_key(k))
    return sorted(keys, key=lambda x: x["created_at"], reverse=True)


@router.post("")
async def create_api_key(data: ApiKeyCreate, current_user=Depends(get_current_user)):
    db = get_db()
    full_key, prefix, key_hash = generate_api_key()

    expires_at = None
    if data.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=data.expires_in_days)

    doc = {
        "user_id": str(current_user["_id"]),
        "name": data.name,
        "key_prefix": prefix,
        "key_hash": key_hash,
        "scopes": data.scopes,
        "rate_limit": data.rate_limit,
        "requests_count": 0,
        "status": "active",
        "is_active": True,
        "created_at": datetime.utcnow(),
        "last_used": None,
        "expires_at": expires_at,
    }

    result = await db.api_keys.insert_one(doc)
    doc["_id"] = result.inserted_id

    return fmt_key(doc, show_key=True, raw_key=full_key)


@router.delete("/{key_id}")
async def revoke_api_key(key_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    try:
        oid = ObjectId(key_id)
        query = {"_id": oid, "user_id": str(current_user["_id"])}
    except (InvalidId, TypeError, ValueError):
        query = {"_id": key_id, "user_id": str(current_user["_id"])}

    k = await db.api_keys.find_one(query)
    if not k:
        raise HTTPException(status_code=404, detail="API key not found")

    await db.api_keys.update_one(query, {"$set": {"is_active": False, "status": "revoked"}})
    return {"message": "API key revoked"}


@router.patch("/{key_id}")
async def rename_api_key(key_id: str, data: ApiKeyUpdate, current_user=Depends(get_current_user)):
    db = get_db()
    try:
        oid = ObjectId(key_id)
        query = {"_id": oid, "user_id": str(current_user["_id"])}
    except (InvalidId, TypeError, ValueError):
        query = {"_id": key_id, "user_id": str(current_user["_id"])}

    k = await db.api_keys.find_one(query)
    if not k:
        raise HTTPException(status_code=404, detail="API key not found")

    await db.api_keys.update_one(query, {"$set": {"name": data.name}})
    
    updated_k = await db.api_keys.find_one(query)
    return fmt_key(updated_k)


@router.post("/{key_id}/rotate")
async def rotate_api_key(key_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    try:
        oid = ObjectId(key_id)
        query = {"_id": oid, "user_id": str(current_user["_id"])}
    except (InvalidId, TypeError, ValueError):
        query = {"_id": key_id, "user_id": str(current_user["_id"])}

    k = await db.api_keys.find_one(query)
    if not k:
        raise HTTPException(status_code=404, detail="API key not found")

    full_key, prefix, key_hash = generate_api_key()
    await db.api_keys.update_one(
        query,
        {"$set": {
            "key_hash": key_hash,
            "key_prefix": prefix,
            "requests_count": 0,
            "created_at": datetime.utcnow(),
        }}
    )
    
    updated_k = await db.api_keys.find_one(query)
    return fmt_key(updated_k, show_key=True, raw_key=full_key)


@router.get("/{key_id}/usage")
async def get_key_usage(key_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    try:
        oid = ObjectId(key_id)
        query = {"_id": oid, "user_id": str(current_user["_id"])}
    except (InvalidId, TypeError, ValueError):
        query = {"_id": key_id, "user_id": str(current_user["_id"])}

    k = await db.api_keys.find_one(query)
    if not k:
        raise HTTPException(status_code=404, detail="API key not found")

    reqs = k.get("requests_count", 0)
    now = datetime.utcnow()
    daily_usage = []
    for i in range(7):
        date_str = (now - timedelta(days=6-i)).strftime("%Y-%m-%d")
        daily_usage.append({
            "date": date_str,
            "requests": reqs // 7 if reqs > 0 else 0
        })

    return {
        "key_id": key_id,
        "requests_count": reqs,
        "rate_limit": k.get("rate_limit", 1000),
        "usage_percent": round(reqs / k.get("rate_limit", 1000) * 100, 2),
        "daily_usage": daily_usage,
    }
