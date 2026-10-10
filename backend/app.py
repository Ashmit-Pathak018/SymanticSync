"""
backend/app.py
──────────────
FastAPI main application entry point for SemanticSync.
Mounts all REST endpoints under /api/v1 and configures CORS.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes_databases import router as databases_router
from backend.api.routes_policies import router as policies_router
from backend.api.routes_conflicts import router as conflicts_router
from backend.api.routes_sync import router as sync_router
from backend.api.routes_query import router as query_router
from backend.api.routes_benchmark import router as benchmark_router
from backend.api.routes_seed import router as seed_router
from backend.api.state import DATA_DIR, app_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure data directory exists and load app state
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    app_state.load()

    # Pre-seed default demo workspaces if state is empty
    if not app_state.databases:
        try:
            from backend.api.routes_seed import seed_workload
            from backend.api.models import SeedRequest
            seed_workload(SeedRequest(workload="all"))
        except Exception as e:
            print(f"[Warning] Automatic seeder skipped: {e}")

    yield


app = FastAPI(
    title="SemanticSync API",
    description="Domain-independent semantic merge middleware and developer workspace for local-first SQLite databases.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware (developer environment)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all /api/v1 routers
app.include_router(databases_router, prefix="/api/v1")
app.include_router(policies_router, prefix="/api/v1")
app.include_router(conflicts_router, prefix="/api/v1")
app.include_router(sync_router, prefix="/api/v1")
app.include_router(query_router, prefix="/api/v1")
app.include_router(benchmark_router, prefix="/api/v1")
app.include_router(seed_router, prefix="/api/v1")


@app.get("/api/v1/health")
def health_check():
    return {
        "status": "healthy",
        "service": "SemanticSync Core API",
        "version": "1.0.0",
    }


@app.get("/")
def root():
    return {
        "name": "SemanticSync API",
        "docs_url": "/docs",
        "version": "1.0.0",
        "message": "Keep SQL. Keep SQLite. Add semantic control over conflicts.",
    }
