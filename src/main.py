"""
Main FastAPI Application Entrypoint for Agentic SRE Platform.
Implements defense-in-depth security headers, CORS isolation, and lifecycle management.
"""

from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from src.api.ai_router import router as ai_router
from src.api.audit_router import router as audit_router
from src.api.auth_router import router as auth_router
from src.api.chaos_router import router as chaos_router
from src.api.correlation_router import router as correlation_router
from src.api.incident_router import router as incident_router
from src.api.remediation_router import router as remediation_router
from src.api.telemetry_router import router as telemetry_router
from src.api.topology_router import router as topology_router
from src.api.ws_router import router as ws_router
from src.config import settings
from src.database import init_db
from src.services.simulation_engine import simulation_engine

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "ui" / "static"
TEMPLATES_DIR = BASE_DIR / "ui" / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages background services lifecycle.
    Initializes database schema, starts simulation loop on boot, cleans up gracefully on exit.
    """
    # 0. Initialize persistent SQLite database
    init_db()
    print("[Agentic SRE] Persistent SQLite database connected & verified.")

    # 1. Start cluster simulation
    simulation_engine.start()
    print("[Agentic SRE] Cluster microservice simulator started.")
    yield
    # 2. Stop simulation on shutdown
    simulation_engine.stop()
    print("[Agentic SRE] Cluster microservice simulator stopped gracefully.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Intelligent Incident Management and Automated Remediation Platform",
    lifespan=lifespan,
)

# 1. CORS Configuration (Restricted to known secure origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT"],
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


# 3. Mount Static UI Assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 4. Include API Routers
app.include_router(auth_router)
app.include_router(telemetry_router)
app.include_router(incident_router)
app.include_router(chaos_router)
app.include_router(topology_router)
app.include_router(audit_router)
app.include_router(correlation_router)
app.include_router(remediation_router)
app.include_router(ai_router)
app.include_router(ws_router)


# 5. UI Root Endpoint
@app.get("/", response_class=HTMLResponse, tags=["Dashboard UI"])
async def serve_dashboard():
    index_file = TEMPLATES_DIR / "index.html"
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/healthz", tags=["System Health"])
async def health_check():
    """Liveness probe for orchestrators/Kubernetes."""
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=True)
