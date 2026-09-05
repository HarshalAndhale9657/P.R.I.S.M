"""
P.R.I.S.M. — ASGI entry point
=============================
    uvicorn main:app --host 127.0.0.1 --port 8000

All wiring lives in `app.factory.create_app`; this module only exists so the
familiar `main:app` target keeps working for uvicorn, Docker and the tests.
"""
from app import create_app

app = create_app()
