"""Entry point: python -m waggle [api|worker|bridge|notify|sync|ml]"""

import asyncio
import os
import sys

import uvicorn

from waggle.config import Settings


def run_api():
    settings = Settings()
    from waggle.main import create_app

    app = create_app(
        db_url=settings.DB_URL,
        api_key=settings.API_KEY,
        admin_api_key=settings.ADMIN_API_KEY or "",
        settings=settings,
    )
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)


def run_notify():
    settings = Settings()

    from sqlalchemy.ext.asyncio import AsyncSession

    from waggle.database import create_engine_from_url, init_db
    from waggle.services.notify import dispatch_webhooks

    async def _dispatch():
        engine = create_engine_from_url(settings.DB_URL)
        await init_db(engine)
        async with AsyncSession(engine) as session:
            count = await dispatch_webhooks(
                session, settings.WEBHOOK_URLS, settings.WEBHOOK_SECRET
            )
        await engine.dispose()
        return count

    count = asyncio.run(_dispatch())
    print(f"Dispatched webhooks for {count} alert(s).")


def run_ml():
    """Run the ML inference worker."""
    settings = Settings()
    model_path = os.environ.get(
        "ML_MODEL_PATH", "/var/lib/waggle/models/yolov8n.pt"
    )

    from waggle.services.ml_worker import run_worker

    asyncio.run(
        run_worker(
            db_url=settings.DB_URL,
            photo_dir=settings.PHOTO_DIR,
            model_path=model_path,
            expected_hash=settings.EXPECTED_MODEL_HASH,
            confidence_threshold=settings.DETECTION_CONFIDENCE_THRESHOLD,
        )
    )


def run_sync_service():
    settings = Settings()

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set for cloud sync.")
        sys.exit(1)

    from waggle.services.sync import run_sync

    asyncio.run(
        run_sync(
            db_url=settings.DB_URL,
            photo_dir=settings.PHOTO_DIR,
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_SERVICE_KEY,
            interval_sec=settings.SYNC_INTERVAL_SEC,
        )
    )


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "api"

    if command == "api":
        run_api()
    elif command == "worker":
        print("Worker not yet wired (MQTT loop). Use 'api' for now.")
        sys.exit(1)
    elif command == "bridge":
        print("Bridge not yet wired (serial loop). Use 'api' for now.")
        sys.exit(1)
    elif command == "ml":
        run_ml()
    elif command == "notify":
        run_notify()
    elif command == "sync":
        run_sync_service()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python -m waggle [api|worker|bridge|ml|notify|sync]")
        sys.exit(1)


if __name__ == "__main__":
    main()
