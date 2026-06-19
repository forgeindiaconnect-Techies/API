import logging
import time
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from auth.utils import decode_token
from database import get_db
from bson import ObjectId
from bson.errors import InvalidId
from config import settings


logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    """
    Pure ASGI middleware for request logging and injection of CORS headers.
    Avoids BaseHTTPMiddleware to prevent event-loop and stream buffering issues.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "")
        
        # Get headers directly from scope to be fast and safe
        headers_dict = {}
        for k, v in scope.get("headers", []):
            headers_dict[k.decode("latin1").lower()] = v.decode("latin1")

        origin = headers_dict.get("origin")
        auth_header = headers_dict.get("authorization")
        
        is_health = method == "HEAD" and path in ("/", "/api/health")
        
        if not is_health:
            masked_auth = f"{auth_header[:25]}..." if auth_header and len(auth_header) > 25 else ("Bearer Present" if auth_header else "None")
            logger.info(f"Incoming Request: {method} {path} | Origin: {origin} | Auth: {masked_auth}")

        start_time = time.time()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                
                # Check if CORS headers are already set to avoid duplication
                has_cors = any(h[0].lower() == b"access-control-allow-origin" for h in response_headers)
                
                if not has_cors:
                    allowed_origins = settings.allowed_origins_list
                    resolved_origin = allowed_origins[0] if allowed_origins else "*"
                    if origin:
                        if origin in allowed_origins or (origin.startswith("https://") and origin.endswith(".vercel.app")):
                            resolved_origin = origin
                    
                    response_headers.append((b"access-control-allow-origin", resolved_origin.encode("utf-8")))
                    response_headers.append((b"access-control-allow-credentials", b"true"))
                    response_headers.append((b"access-control-allow-methods", b"GET, POST, PUT, DELETE, OPTIONS, HEAD"))
                    response_headers.append((b"access-control-allow-headers", b"Authorization, Content-Type, Accept, X-API-Key"))
                    response_headers.append((b"access-control-expose-headers", b"*"))
                
                # Add process time header
                duration = round((time.time() - start_time) * 1000, 2)
                response_headers.append((b"x-process-time", str(duration).encode("utf-8")))
                
                message["headers"] = response_headers
                
                if not is_health:
                    status_code = message.get("status", 200)
                    logger.info(
                        f"{method} {path} -> {status_code} ({duration}ms) | "
                        f"CORS Allow-Origin: {resolved_origin if not has_cors else 'Already Set'}"
                    )
            
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            if not is_health:
                logger.error(f"Request failed: {method} {path} | Error: {e}", exc_info=True)
            raise


class AuthMiddleware:
    """
    Pure ASGI middleware for authenticating requests and setting request.state.user.
    Bypasses preflight OPTIONS and public endpoints.
    Avoids BaseHTTPMiddleware to prevent stream-blocking issues in SSE endpoints.
    """
    ALLOWED_ORIGINS = settings.allowed_origins_list

    def __init__(self, app):
        self.app = app

    def _cors_response(self, origin: str | None, status_code: int, content: dict, headers: dict | None = None) -> JSONResponse:
        """Build a JSONResponse with CORS headers so the browser doesn't block error responses."""
        cors_headers = dict(headers or {})
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
        origin = request.headers.get("origin")

        # 1. Bypass OPTIONS preflight requests completely
        if request.method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # 1.5 Bypass if already authenticated by APIKeyAuthMiddleware
        state = scope.get("state")
        if isinstance(state, dict) and ("api_key" in state or "api_key_doc" in state):
            await self.app(scope, receive, send)
            return

        # 2. Bypass public paths
        path = request.url.path
        public_paths = [
            "/",
            "/health",
            "/api/health",
            "/favicon.ico",
            "/robots.txt",
            "/api/docs",
            "/api/redoc",
            "/api/openapi.json",
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/refresh",
            "/api/v1/info",
            "/api/v1/test-gemini",
            "/api/v1/test-embedder",
        ]
        
        if path in public_paths or path.startswith("/api/docs") or path.startswith("/api/openapi"):
            await self.app(scope, receive, send)
            return

        # 3. Extract and validate Bearer Token
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning(f"AuthMiddleware: Request to protected path '{path}' missing Bearer Token")
            response = self._cors_response(
                origin, 401,
                {"detail": "Not authenticated"},
                {"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        token = auth_header.split(" ")[1]
        logger.info(f"AuthMiddleware: Extracted Bearer token for protected path '{path}'")
        try:
            db = get_db()
            if db is None:
                logger.error("AuthMiddleware: Database connection unavailable when validating token")
                response = self._cors_response(origin, 500, {"detail": "Database connection unavailable"})
                await response(scope, receive, send)
                return

            if token.startswith("sk-"):
                logger.info("AuthMiddleware: Validating API Key")
                import hashlib
                from datetime import datetime, timezone
                key_hash = hashlib.sha256(token.encode()).hexdigest()
                key_doc = await db.api_keys.find_one({
                    "key_hash": key_hash,
                    "$or": [
                        {"is_active": True},
                        {"is_active": {"$exists": False}, "status": "active"}
                    ]
                })
                if not key_doc:
                    logger.warning("AuthMiddleware: API Key not found or inactive")
                    response = self._cors_response(origin, 401, {"detail": "Invalid or inactive API Key"})
                    await response(scope, receive, send)
                    return
                
                # Check expiration
                expires_at = key_doc.get("expires_at")
                if expires_at:
                    if isinstance(expires_at, str):
                        try:
                            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                        except ValueError:
                            pass
                    if isinstance(expires_at, datetime) and expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                        logger.warning("AuthMiddleware: API Key expired")
                        response = self._cors_response(origin, 401, {"detail": "API Key has expired"})
                        await response(scope, receive, send)
                        return

                # Check rate limit using both count fields
                request_count = key_doc.get("request_count") or key_doc.get("requests_count") or 0
                if request_count >= key_doc.get("rate_limit", 1000):
                    logger.warning("AuthMiddleware: API Key rate limit exceeded")
                    response = self._cors_response(origin, 429, {"detail": "Rate limit exceeded for this API key"})
                    await response(scope, receive, send)
                    return

                user_id = key_doc.get("user_id")
                # Update metrics
                now_utc = datetime.now(timezone.utc)
                await db.api_keys.update_one(
                    {"_id": key_doc["_id"]},
                    {
                        "$set": {
                            "last_used": now_utc,
                            "last_used_at": now_utc
                        },
                        "$inc": {
                            "request_count": 1,
                            "requests_count": 1
                        }
                    }
                )
            else:
                payload = decode_token(token, expected_type="access")
                user_id = payload.get("sub")
                logger.info(f"AuthMiddleware: Token decoded successfully. User ID (sub): {user_id}")
                if not user_id:
                    logger.warning(f"AuthMiddleware: Token sub payload missing user_id for token on path '{path}'")
                    response = self._cors_response(origin, 401, {"detail": "Invalid token payload"})
                    await response(scope, receive, send)
                    return

            # Support both string and ObjectId formats for the user _id lookup
            if len(user_id) == 24:
                try:
                    user_oid = ObjectId(user_id)
                    user_query = {"_id": {"$in": [user_id, user_oid]}}
                except (InvalidId, TypeError, ValueError) as oid_err:
                    logger.warning(f"AuthMiddleware: Invalid user_id format in sub: '{user_id}' | Error: {oid_err}")
                    response = self._cors_response(
                        origin,
                        400,
                        {"detail": f"Invalid User ID format: '{user_id}'. Must be a 24-character hex string."}
                    )
                    await response(scope, receive, send)
                    return
            else:
                user_query = {"_id": user_id}

            logger.info(f"AuthMiddleware: Querying database for user with query: {user_query}")
            user = await db.users.find_one(user_query)
            if not user:
                logger.warning(f"AuthMiddleware: User not found in database for sub: {user_id}")
                response = self._cors_response(origin, 401, {"detail": "User not found"})
                await response(scope, receive, send)
                return

            if user.get("disabled"):
                logger.warning(f"AuthMiddleware: Account disabled for user: {user_id}")
                response = self._cors_response(origin, 400, {"detail": "Account disabled"})
                await response(scope, receive, send)
                return

            # Attach user and api_key to request state
            scope["state"] = scope.get("state", {})
            scope["state"]["user"] = user
            if token.startswith("sk-"):
                scope["state"]["api_key"] = key_doc
            logger.info(f"AuthMiddleware: Successfully authenticated user: {user.get('email')} (ID: {user_id})")

        except HTTPException as he:
            logger.warning(f"AuthMiddleware: HTTPException during token validation for path '{path}': {he.detail}")
            response = self._cors_response(
                origin, he.status_code,
                {"detail": he.detail},
                dict(he.headers) if he.headers else None,
            )
            await response(scope, receive, send)
            return
        except Exception as e:
            logger.error(f"AuthMiddleware: Unexpected authentication error: {e}", exc_info=True)
            response = self._cors_response(
                origin, 401,
                {"detail": f"Authentication failed: {str(e)}"},
                {"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
