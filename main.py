"""
main.py
───────
Entry point for SemanticSync backend server.
Runs the FastAPI application on http://127.0.0.1:8000.
"""

import sys
import uvicorn

if __name__ == "__main__":
    print("==================================================")
    print("  SemanticSync — Local-First Semantic Middleware  ")
    print("  API Server: http://127.0.0.1:8000               ")
    print("  Swagger UI: http://127.0.0.1:8000/docs          ")
    print("==================================================")
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
