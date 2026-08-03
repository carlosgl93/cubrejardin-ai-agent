"""FastAPI entry point."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from api import api_router
from config import settings

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.admin_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Register channel adapters exactly once at import time (before any worker
# begins serving requests). The registry is treated as immutable after this.
from channels.registry import register_adapter
from channels.whatsapp import WhatsAppAdapter
from channels.instagram import InstagramAdapter

register_adapter(WhatsAppAdapter())
register_adapter(InstagramAdapter())


@app.get("/")
def root() -> dict:
    """Return service metadata."""

    return {"name": settings.app_name, "environment": settings.environment}


# One-shot migration endpoint. Disabled by default; enable by setting
# ENABLE_MIGRATION_ENDPOINT=1 in the service env. The endpoint requires the
# MIGRATION_TOKEN env var to authenticate. Returns the SQL it ran plus row counts.
@app.post("/admin/run-migration")
def run_migration(request: Request) -> dict:
    if os.environ.get("ENABLE_MIGRATION_ENDPOINT") != "1":
        raise HTTPException(status_code=404, detail="not found")

    expected = os.environ.get("MIGRATION_TOKEN", "")
    provided = request.headers.get("X-Migration-Token", "")
    if not expected or provided != expected:
        raise HTTPException(status_code=403, detail="forbidden")

    import pathlib
    import psycopg

    sql_path = pathlib.Path(__file__).parent / "sql" / "migrations" / "006_instagram_channel.sql"
    sql_text = sql_path.read_text()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        # Derive direct DB URL from the Supabase project URL. The repo's
        # .env file (db.db.<ref>.supabase.co) is malformed; the correct
        # hostname is db.<ref>.supabase.co on port 5432.
        project_ref = settings.supabase_url.split("//", 1)[-1].split(".", 1)[0]
        db_url = f"postgresql://postgres:{settings.supabase_db_password}@db.{project_ref}.supabase.co:5432/postgres"
    if db_url.startswith("postgresql+psycopg://"):
        db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)

            cur.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='conversations' AND column_name='channel'"
            )
            column_exists = cur.fetchone()[0] > 0

            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='tenant_instagram_credentials'"
            )
            table_exists = cur.fetchone()[0] > 0

    return {
        "migration": "006_instagram_channel.sql",
        "applied": True,
        "conversations_channel_column": column_exists,
        "tenant_instagram_credentials_table": table_exists,
    }
