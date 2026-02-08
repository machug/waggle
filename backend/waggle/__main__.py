"""Entry point: python -m waggle [api|worker|bridge|notify]"""

import asyncio
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
    elif command == "notify":
        run_notify()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python -m waggle [api|worker|bridge|notify]")
        sys.exit(1)


if __name__ == "__main__":
    main()
