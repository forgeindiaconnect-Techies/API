from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime
from pymongo import ReturnDocument
import logging
from config import settings

logger = logging.getLogger(__name__)


class APIKeyAuthMiddleware:
    """
    ASGI middleware for validating sk-ai_ API keys on public endpoints.
    """
    ALLOWED_ORIGINS = settings.allowed_origins_list

    def __init__(self, app):
        self.app = app

    def _cors_response(self, origin: str | None, status_code: int, content: dict) -> JSONResponse:
        cors_headers = {}
        resolved_origin = None
        if origin:
            if origin in self.ALLOWED_ORIGINS or (origin.startswith("https://") and origin.endswith(".vercel.app")):
                resolved_origin = origin
        if not resolved_origin:
            resolved_origin = self.ALLOWED_ORIGINS[0] if self.ALLOWED_ORIGINS else "*"
        cors_headers["Access-Control-Allow-Origin"] = resolved_origin
        cors_headers["Access-Control-Allow-Credentials"] = "true"
        cors_headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD"
        cors_headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept, X-API-Key"
        return JSONResponse(status_code=status_code, content=content, headers=cors_headers)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if "state" not in scope:
            scope["state"] = {}

        request = Request(scope, receive=receive)
        path = request.url.path
        origin = request.headers.get("origin")

        # Bypass OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Check if route is protected
        protected_prefixes = [
            "/api/chat", "/api/v1/chat",
            "/api/predict", "/api/v1/predict",
            "/api/embed", "/api/v1/embed",
            "/api/transcribe", "/api/v1/transcribe",
            "/api/generate-image", "/api/v1/generate-image",
            "/api/image-generate", "/api/v1/image-generate",
            "/api/rag", "/api/v1/rag",
            "/api/ai", "/api/v1/ai"
        ]

        is_protected = any(path == p or path.startswith(p + "/") for p in protected_prefixes)

        if not is_protected:
            await self.app(scope, receive, send)
            return

        # 1. Read API Key from headers (X-API-Key or Authorization Bearer)
        api_key = request.headers.get("x-api-key")
        is_bearer = False
        if not api_key:
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                api_key = auth_header.split(" ")[1]
                is_bearer = True

        # If it's a Bearer token but doesn't start with 'sk-', it's a standard user JWT session.
        # Bypass API key validation and let AuthMiddleware validate the JWT token.
        if is_bearer and api_key and not api_key.startswith("sk-"):
            await self.app(scope, receive, send)
            return

        if not api_key:
            response = self._cors_response(origin, 401, {"detail": "Invalid or inactive API key"})
            await response(scope, receive, send)
            return

        # Import get_db lazily to avoid circular imports during startup
        from database import get_db
        db = get_db()
        if db is None:
            response = self._cors_response(origin, 500, {"detail": "Database connection unavailable"})
            await response(scope, receive, send)
            return

        # 2. Query MongoDB api_keys by key_hash
        import hashlib
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_doc = await db.api_keys.find_one({
            "key_hash": key_hash,
            "$or": [
                {"is_active": True},
                {"is_active": {"$exists": False}, "status": "active"}
            ]
        })
        if not key_doc:
            response = self._cors_response(origin, 401, {"detail": "Invalid or inactive API key"})
            await response(scope, receive, send)
            return

        # 3. Check rate limit
        request_count = key_doc.get("request_count") or key_doc.get("requests_count") or 0
        rate_limit = key_doc.get("rate_limit", 10000)
        if request_count >= rate_limit:
            response = self._cors_response(origin, 429, {"detail": "Rate limit exceeded"})
            await response(scope, receive, send)
            return

        # 4. Check scopes
        scope_name = None
        if "chat" in path:
            scope_name = "chat"
        elif "predict" in path:
            scope_name = "predict"
        elif "embed" in path:
            scope_name = "embed"
        elif "transcribe" in path:
            scope_name = "transcribe"
        elif "generate-image" in path or "image-generate" in path:
            scope_name = "generate-image"
        elif "rag" in path:
            scope_name = "rag"

        scopes_list = key_doc.get("scopes", [])
        if scope_name and scope_name not in scopes_list:
            response = self._cors_response(origin, 403, {"detail": "Scope not allowed"})
            await response(scope, receive, send)
            return

        # 5. Check allowed_datasets
        allowed_datasets = key_doc.get("allowed_datasets") or key_doc.get("dataset_ids")
        scope["state"] = scope.get("state", {})
        if allowed_datasets and len(allowed_datasets) > 0:
            scope["state"]["allowed_datasets"] = allowed_datasets
        else:
            scope["state"]["allowed_datasets"] = None

        # 6. On success: increment count and update last_used (both request_count and requests_count)
        updated_doc = await db.api_keys.find_one_and_update(
            {"_id": key_doc["_id"]},
            {
                "$inc": {"request_count": 1, "requests_count": 1},
                "$set": {
                    "last_used": datetime.utcnow(),
                    "last_used_at": datetime.utcnow()
                }
            },
            return_document=ReturnDocument.AFTER
        )
        scope["state"]["api_key"] = updated_doc
        scope["state"]["api_key_doc"] = updated_doc

        # Also authenticate/attach user context to request.state.user for compatibility
        # with downstream routers/functions that depend on current_user or state.user
        user_id = key_doc.get("user_id")
        if user_id:
            from bson import ObjectId
            from bson.errors import InvalidId
            try:
                user_query = {"_id": ObjectId(user_id)} if len(user_id) == 24 else {"_id": user_id}
            except (InvalidId, TypeError, ValueError):
                user_query = {"_id": user_id}
            
            user_doc = await db.users.find_one(user_query)
            if user_doc:
                scope["state"]["user"] = user_doc

        client_host = request.client.host if request.client else "unknown"
        logger.info(
            f"API Key Authenticated: name='{updated_doc.get('name')}', "
            f"prefix='{updated_doc.get('key_prefix') or api_key[:12]}', "
            f"path='{path}', client='{client_host}'"
        )

        await self.app(scope, receive, send)
