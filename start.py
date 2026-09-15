#!/usr/bin/env python3
"""
Start the GeniusDataManager development server.
Run from the project root: python start.py
"""
import sys
from pathlib import Path

backend = Path(__file__).parent / "backend"
if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_includes=["*.py"],
        reload_excludes=["*.db*", "*.sqlite*", "data/*"],
        app_dir=str(backend),
        log_level="info",
    )
