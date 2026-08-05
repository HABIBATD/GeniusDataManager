#!/usr/bin/env python3
"""
Start the GeniusDataManager development server.
Run from the project root: python start.py
"""
import subprocess
import sys
from pathlib import Path

backend = Path(__file__).parent / "backend"

subprocess.run([
    sys.executable, "-m", "uvicorn",
    "main:app",
    "--reload",
    "--host", "0.0.0.0",
    "--port", "8000",
    "--log-level", "info",
], cwd=str(backend))
