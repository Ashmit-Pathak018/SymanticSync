"""
main.py
───────
Entry point for SemanticSync server.
Runs the FastAPI application on http://127.0.0.1:8000.
Optionally starts the frontend dev server when --with-frontend is passed.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn


def run_frontend():
    frontend_dir = Path(__file__).resolve().parent / "frontend"
    if (frontend_dir / "node_modules").exists():
        print("\n[Frontend] Starting Studio Dev Server on http://localhost:5173 ...\n")
        subprocess.run(["npm", "run", "dev"], cwd=str(frontend_dir), shell=True)
    else:
        print("\n[Warning] frontend/node_modules not found. Run 'cd frontend && npm install' first.\n")


def main():
    parser = argparse.ArgumentParser(description="SemanticSync Runner")
    parser.add_argument(
        "--with-frontend",
        action="store_true",
        help="Start Vite frontend dev server (http://localhost:5173) alongside backend API",
    )
    parser.add_argument("--host", default="127.0.0.1", help="API host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="API port (default: 8000)")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    args = parser.parse_args()

    print("==================================================")
    print("  SemanticSync — Local-First Semantic Middleware  ")
    print(f"  API Server: http://{args.host}:{args.port}         ")
    print(f"  Swagger UI: http://{args.host}:{args.port}/docs    ")
    if args.with_frontend:
        print("  Studio UI:  http://localhost:5173              ")
    print("==================================================")

    if args.with_frontend:
        t = threading.Thread(target=run_frontend, daemon=True)
        t.start()
        time.sleep(1)

    uvicorn.run("backend.app:app", host=args.host, port=args.port, reload=not args.no_reload)


if __name__ == "__main__":
    main()
