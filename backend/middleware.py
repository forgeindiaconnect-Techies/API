import logging
import time
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from auth.utils import decode_token
from database import get_db

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
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        
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
            response = JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return

        token = auth_header.split(" ")[1]
        try:
            payload = decode_token(token)
            if payload.get("type") != "access":
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid token type"}
                )
                await response(scope, receive, send)
                return
                
            user_id = payload.get("sub")
            if not user_id:
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid token payload"}
                )
                await response(scope, receive, send)
                return

            db = get_db()
            if db is None:
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "Database connection unavailable"}
                )
                await response(scope, receive, send)
                return

            user = await db.users.find_one({"_id": user_id})
            if not user:
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "User not found"}
                )
                await response(scope, receive, send)
                return

            if user.get("disabled"):
                response = JSONResponse(
                    status_code=400,
                    content={"detail": "Account disabled"}
                )
                await response(scope, receive, send)
                return

            # Attach user to request state
            scope["state"] = scope.get("state", {})
            scope["state"]["user"] = user

        except HTTPException as he:
            response = JSONResponse(
                status_code=he.status_code,
                content={"detail": he.detail},
                headers=he.headers
            )
            await response(scope, receive, send)
            return
        except Exception as e:
            logger.error(f"AuthMiddleware error: {e}")
            response = JSONResponse(
                status_code=401,
                content={"detail": f"Authentication failed: {str(e)}"},
                headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
