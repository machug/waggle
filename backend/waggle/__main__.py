"""Entry point: python -m waggle [api|worker|bridge]"""

import sys

import uvicorn

from waggle.config import Settings


def run_api():
    settings = Settings()
    from waggle.main import create_app

    app = create_app(db_url=settings.DB_URL, api_key=settings.API_KEY)
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)


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
    else:
        print(f"Unknown command: {command}")
        print("Usage: python -m waggle [api|worker|bridge]")
        sys.exit(1)


if __name__ == "__main__":
    main()
