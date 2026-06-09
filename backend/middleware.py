import logging
import time
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from auth.utils import decode_token
from database import get_db
from bson import ObjectId
from bson.errors import InvalidId


logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Suppress logging for HEAD health checks to keep production logs clean
        if request.method == "HEAD" and request.url.path in ("/", "/api/health"):
            return await call_next(request)

        origin = request.headers.get("origin")
        auth_header = request.headers.get("authorization")
        masked_auth = f"{auth_header[:25]}..." if auth_header and len(auth_header) > 25 else ("Bearer Present" if auth_header else "None")
        logger.info(f"Incoming Request: {request.method} {request.url.path} | Origin: {origin} | Auth: {masked_auth}")

        start = time.time()
        try:
            response = await call_next(request)
            duration = round((time.time() - start) * 1000, 2)

            # Set manual CORS headers on all responses so it's always set (even on errors, preflights, and streaming)
            allowed_origins = [
                "https://d-ai-nu.vercel.app",
                "http://localhost:3000",
                "http://localhost:5173"
            ]
            if origin:
                if origin in allowed_origins or (origin.startswith("https://") and origin.endswith(".vercel.app")):
                    response.headers["Access-Control-Allow-Origin"] = origin
                else:
                    response.headers["Access-Control-Allow-Origin"] = "https://d-ai-nu.vercel.app"
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD"
                response.headers["Access-Control-Allow-Headers"] = "*"
            elif not response.headers.get("access-control-allow-origin"):
                response.headers["Access-Control-Allow-Origin"] = "https://d-ai-nu.vercel.app"

            logger.info(
                f"{request.method} {request.url.path} → {response.status_code} ({duration}ms) | "
                f"CORS Allow-Origin: {response.headers.get('access-control-allow-origin')}"
            )

            response.headers["X-Process-Time"] = str(duration)
            return response
        except Exception as e:
            logger.error(f"Request failed: {request.method} {request.url.path} | Error: {e}")
            raise


class AuthMiddleware:
    """
    Pure ASGI middleware for authenticating requests and setting request.state.user.
    Bypasses preflight OPTIONS and public endpoints.
    Avoids BaseHTTPMiddleware to prevent stream-blocking issues in SSE endpoints.
    """
    ALLOWED_ORIGINS = [
        "https://d-ai-nu.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ]

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
            resolved_origin = "https://d-ai-nu.vercel.app"
        cors_headers["Access-Control-Allow-Origin"] = resolved_origin
        cors_headers["Access-Control-Allow-Credentials"] = "true"
        cors_headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD"
        cors_headers["Access-Control-Allow-Headers"] = "*"
        return JSONResponse(status_code=status_code, content=content, headers=cors_headers)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        origin = request.headers.get("origin")

        # 1. Bypass OPTIONS preflight requests completely
        if request.method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # 2. Bypass public paths
        path = request.url.path
        public_paths = [
            "/",
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
            payload = decode_token(token, expected_type="access")
            user_id = payload.get("sub")
            logger.info(f"AuthMiddleware: Token decoded successfully. User ID (sub): {user_id}")
            if not user_id:
                logger.warning(f"AuthMiddleware: Token sub payload missing user_id for token on path '{path}'")
                response = self._cors_response(origin, 401, {"detail": "Invalid token payload"})
                await response(scope, receive, send)
                return

            db = get_db()
            if db is None:
                logger.error(f"AuthMiddleware: Database connection unavailable when validating token for sub: {user_id}")
                response = self._cors_response(origin, 500, {"detail": "Database connection unavailable"})
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

            # Attach user to request state
            scope["state"] = scope.get("state", {})
            scope["state"]["user"] = user
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
