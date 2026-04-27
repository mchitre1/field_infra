from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import ingest as ingest_routes
from app.core.config import get_settings
from app.core.context import correlation_id_var
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="IIE API", lifespan=lifespan)


@app.middleware("http")
async def limit_request_body_middleware(request: Request, call_next):
    """Reject ``POST``/``PUT``/``PATCH`` when ``Content-Length`` exceeds ``max_upload_bytes``."""
    if request.method in ("POST", "PUT", "PATCH"):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                n = int(cl)
            except ValueError:
                return await call_next(request)
            max_b = get_settings().max_upload_bytes
            if n > max_b:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body exceeds configured limit"},
                )
    return await call_next(request)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    header = request.headers.get("x-request-id") or request.headers.get("x-correlation-id")
    cid = header or str(uuid4())
    token = correlation_id_var.set(cid)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = cid
        return response
    finally:
        correlation_id_var.reset(token)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(ingest_routes.router)
