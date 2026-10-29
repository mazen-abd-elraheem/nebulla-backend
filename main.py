"""
Root entrypoint for Nebula Backend.
Allows running with either:
  uvicorn main:app --reload --port 8000
  uvicorn app.main:app --reload --port 8000
  python main.py
"""

import sys
import os

# Ensure current directory is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
