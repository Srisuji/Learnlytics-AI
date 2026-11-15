"""Vercel Serverless Function entry point for Learnlytics AI FastAPI backend."""
import os
import sys

# Ensure repository root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.main import app

# Export app for Vercel Python runtime
__all__ = ["app"]

