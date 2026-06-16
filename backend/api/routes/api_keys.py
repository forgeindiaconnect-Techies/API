from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
import secrets
import hashlib
import logging
from typing import Optional, List

from models import ApiKeyCreate, ApiKeyResponse, ApiKeyUpdate
from auth.utils import get_current_user
from database import get_db
from bson import ObjectId
from bson.errors import InvalidId

router = APIRouter(tags=["API Keys"])
logger = logging.getLogger(__name__)


def generate_api_key():
    import secrets
    import hashlib
    raw_key = "sk-ai_" + secrets.token_urlsafe(24)
    prefix = raw_key[:12]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, prefix, key_hash


def fmt_key(k: dict, mask: bool = True, raw_key: str = None) -> dict:
    created_at = k.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            created_at = datetime.utcnow()
    elif not isinstance(created_at, datetime):
        created_at = datetime.utcnow()

    last_used = k.get("last_used")
    if isinstance(last_used, str):
        try:
            last_used = datetime.fromisoformat(last_used.replace("Z", "+00:00"))
        except ValueError:
            pass

    key_value = None
    if not mask:
        key_value = raw_key or k.get("key")
    else:
        full_key = raw_key or k.get("key") or ""
        if full_key:
            key_value = full_key[:12] + "••••••••"
        else:
            prefix = k.get("key_prefix")
            if prefix:
                key_value = prefix + "••••••••"
            else:
                key_value = "••••••••••••"

    return {
        "id": str(k["_id"]),
        "name": k.get("name"),
        "key": key_value,
        "key_prefix": k.get("key_prefix") or (raw_key[:12] if raw_key else (k.get("key")[:12] if k.get("key") else None)),
        "scopes": k.get("scopes", ["chat"]),
        "rate_limit": k.get("rate_limit", 10000),
        "request_count": k.get("request_count") or k.get("requests_count") or 0,
        "is_active": k.get("is_active", True) or (k.get("status") == "active"),
        "user_id": k.get("user_id", ""),
        "created_at": created_at,
        "last_used": last_used,
        "allowed_datasets": [str(x) for x in (k.get("allowed_datasets") or k.get("dataset_ids") or [])],
        "allowed_models": [str(x) for x in (k.get("allowed_models") or k.get("model_ids") or [])],
    }


@router.get("", response_model=List[ApiKeyResponse])
async def list_api_keys(current_user=Depends(get_current_user)):
    db = get_db()
    keys = []
    async for k in db.api_keys.find({"user_id": str(current_user["_id"])}):
        keys.append(fmt_key(k, mask=True))
    return sorted(keys, key=lambda x: x["created_at"], reverse=True)


@router.post("", response_model=ApiKeyResponse)
async def create_api_key(data: ApiKeyCreate, current_user=Depends(get_current_user)):
    db = get_db()
    logger.info(f"API Key creation request for user '{current_user.get('email')}' with name: '{data.name}' and rate limit: {data.rate_limit}")
    
    raw_key = "sk-ai_" + secrets.token_urlsafe(24)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    doc = {
        "name": data.name,
        "key": raw_key,
        "key_hash": key_hash,
        "scopes": data.scopes,
        "rate_limit": data.rate_limit if data.rate_limit is not None else 10000,
        "request_count": 0,
        "allowed_datasets": data.allowed_datasets or [],
        "allowed_models": data.allowed_models or [],
        "is_active": True,
        "created_at": datetime.utcnow(),
        "last_used": None,
        "user_id": str(current_user["_id"]),
    }

    result = await db.api_keys.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(f"Successfully generated API Key '{data.name}' (ID: {doc['_id']}) for user '{current_user.get('email')}'")

    return fmt_key(doc, mask=False, raw_key=raw_key)


@router.delete("/{key_id}")
async def revoke_api_key(key_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    logger.info(f"API Key revocation request for key ID: '{key_id}' by user '{current_user.get('email')}'")
    try:
        oid = ObjectId(key_id)
        query = {"_id": oid, "user_id": str(current_user["_id"])}
    except (InvalidId, TypeError, ValueError):
        query = {"_id": key_id, "user_id": str(current_user["_id"])}

    k = await db.api_keys.find_one(query)
    if not k:
        logger.warning(f"API Key revocation failed: key ID '{key_id}' not found for user '{current_user.get('email')}'")
        raise HTTPException(status_code=404, detail="API key not found")

    await db.api_keys.update_one(query, {"$set": {"is_active": False}})
    logger.info(f"Successfully soft-deleted API Key ID '{key_id}' for user '{current_user.get('email')}'")
    return {"message": "API key revoked"}


@router.patch("/{key_id}", response_model=ApiKeyResponse)
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
    return fmt_key(updated_k, mask=True)


@router.post("/{key_id}/rotate", response_model=ApiKeyResponse)
async def rotate_api_key(key_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    logger.info(f"API Key rotation request for key ID: '{key_id}' by user '{current_user.get('email')}'")
    try:
        oid = ObjectId(key_id)
        query = {"_id": oid, "user_id": str(current_user["_id"])}
    except (InvalidId, TypeError, ValueError):
        query = {"_id": key_id, "user_id": str(current_user["_id"])}

    k = await db.api_keys.find_one(query)
    if not k:
        logger.warning(f"API Key rotation failed: key ID '{key_id}' not found for user '{current_user.get('email')}'")
        raise HTTPException(status_code=404, detail="API key not found")

    raw_key = "sk-ai_" + secrets.token_urlsafe(24)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    await db.api_keys.update_one(
        query,
        {"$set": {
            "key": raw_key,
            "key_hash": key_hash,
            "request_count": 0,
            "created_at": datetime.utcnow(),
        }}
    )
    
    updated_k = await db.api_keys.find_one(query)
    logger.info(f"Successfully rotated API Key ID '{key_id}' for user '{current_user.get('email')}'")
    return fmt_key(updated_k, mask=False, raw_key=raw_key)


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

    reqs = k.get("request_count") or k.get("requests_count") or 0
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
        "rate_limit": k.get("rate_limit", 10000),
        "usage_percent": round(reqs / k.get("rate_limit", 10000) * 100, 2),
        "daily_usage": daily_usage,
    }
