"""
Main FastAPI Application Entrypoint for Agentic SRE Platform.
Implements defense-in-depth security headers, CORS isolation, and lifecycle management.
"""

from contextlib import asynccontextmanager
import logging
from sqlalchemy.exc import SQLAlchemyError

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from src.api.ai_router import router as ai_router
from src.api.audit_router import router as audit_router
from src.api.auth_router import router as auth_router
from src.api.chaos_router import router as chaos_router
from src.api.correlation_router import router as correlation_router
from src.api.incident_router import router as incident_router
from src.api.platform_extended_router import router as platform_extended_router
from src.api.remediation_router import router as remediation_router
from src.api.telemetry_router import router as telemetry_router
from src.api.topology_router import router as topology_router
from src.api.ws_router import router as ws_router
from src.config import settings
from src.database import init_db
from src.services.simulation_engine import simulation_engine

from src.services.auth_service import auth_service, get_current_user
from src.services.audit_service import audit_service
from src.services.incident_service import incident_service
from src.services.remediation_engine import remediation_engine
from src.services.platform_service import platform_service
logger = logging.getLogger(__name__)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages background services lifecycle.
    Initializes database schema, starts simulation loop on boot, cleans up gracefully on exit.
    """
    init_db()
    audit_service.initialize()
    auth_service.initialize()
    incident_service.initialize()
    remediation_engine.initialize()
    platform_service.initialize()
    if settings.simulation_enabled:
        simulation_engine.start()
    try:
        yield
    finally:
        await simulation_engine.stop()



app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Incident investigation and human-approved simulation recovery",
    lifespan=lifespan,
)

# 1. CORS Configuration (Restricted to known secure origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


# 2. Enterprise Security Headers Middleware (OWASP Secure Headers)
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


# 3. Include API Routers
app.include_router(auth_router)
app.include_router(telemetry_router, dependencies=[Depends(get_current_user)])
app.include_router(incident_router, dependencies=[Depends(get_current_user)])
app.include_router(chaos_router, dependencies=[Depends(get_current_user)])
app.include_router(topology_router, dependencies=[Depends(get_current_user)])
app.include_router(audit_router, dependencies=[Depends(get_current_user)])
app.include_router(correlation_router, dependencies=[Depends(get_current_user)])
app.include_router(remediation_router, dependencies=[Depends(get_current_user)])
app.include_router(ai_router, dependencies=[Depends(get_current_user)])
app.include_router(platform_extended_router, dependencies=[Depends(get_current_user)])
app.include_router(ws_router)


# 4. API Info Root Endpoint
@app.get("/login", tags=["Frontend"])
@app.get("/signup", tags=["Frontend"])
@app.get("/", tags=["API Root"])
async def root():
    if (FRONTEND_DIR / "index.html").is_file():
        return FileResponse(FRONTEND_DIR / "index.html")
    return {
        "status": "online",
        "service": settings.app_name,
        "version": settings.app_version,
        "mode": "simulation" if settings.simulation_enabled else "telemetry-only",
        "docs": "/docs"
    }


@app.get("/healthz", tags=["System Health"])
async def health_check():
    """Liveness probe for orchestrators/Kubernetes."""
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}



@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    logger.error("Database operation failed", exc_info=True)
    return JSONResponse(status_code=503, content={"detail": "Storage is unavailable. The operation did not complete."})


@app.get("/readyz", tags=["System Health"])
async def readiness_check():
    from sqlalchemy import text
    from src.database import SessionLocal
    with SessionLocal() as session:
        session.execute(text("SELECT 1 FROM users LIMIT 1"))
    if settings.simulation_enabled and not simulation_engine.is_running:
        return JSONResponse(status_code=503, content={"status": "simulation stopped"})
    return {"status": "ready"}

if (FRONTEND_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=settings.debug)
