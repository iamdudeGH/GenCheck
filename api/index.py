"""Vercel entry point — the whole portal app as one serverless function.

vercel.json rewrites every path here; FastAPI serves /api/* routes and the
static frontend (mounted at / in portal.app). Submit/poll endpoints keep
every invocation short (~2s / ~0.5s), inside serverless limits.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portal.app import app  # noqa: E402,F401  (Vercel's Python runtime detects the ASGI app)
