"""Weather endpoint with provider-based fetching and caching."""

import time

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from waggle.schemas import WeatherOut

# Simple in-memory cache
_weather_cache: dict = {"data": None, "fetched_at": 0}
_CACHE_TTL = 900  # 15 minutes


async def _fetch_openweathermap(api_key: str, lat: str, lon: str) -> WeatherOut:
    """Fetch weather from OpenWeatherMap API."""
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    return WeatherOut(
        provider="openweathermap",
        temp_c=data.get("main", {}).get("temp"),
        humidity_pct=data.get("main", {}).get("humidity"),
        description=(
            data.get("weather", [{}])[0].get("description")
            if data.get("weather")
            else None
        ),
        icon=(
            data.get("weather", [{}])[0].get("icon")
            if data.get("weather")
            else None
        ),
        wind_speed_ms=data.get("wind", {}).get("speed"),
        fetched_at=None,  # Will be set below
    )


async def _fetch_bom(lat: str, lon: str) -> WeatherOut:
    """Fetch weather from BOM (Australian Bureau of Meteorology).

    BOM doesn't have a simple REST API, so this is a placeholder
    that returns a stub response.
    """
    return WeatherOut(
        provider="bom",
        temp_c=None,
        humidity_pct=None,
        description="BOM provider not yet implemented",
        icon=None,
        wind_speed_ms=None,
        fetched_at=None,
    )


def create_router(verify_key) -> APIRouter:
    router = APIRouter(dependencies=[verify_key])

    @router.get("/weather/current")
    async def get_weather(request: Request):
        settings = (
            request.app.state.settings
            if hasattr(request.app.state, "settings")
            else None
        )
        provider = getattr(settings, "WEATHER_PROVIDER", None) or "none"

        if provider == "none":
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "Weather provider not configured",
                    }
                },
            )

        # Check cache
        now = time.time()
        if _weather_cache["data"] and (now - _weather_cache["fetched_at"]) < _CACHE_TTL:
            return _weather_cache["data"]

        try:
            if provider == "openweathermap":
                api_key = getattr(settings, "OPENWEATHERMAP_API_KEY", "")
                lat = getattr(settings, "WEATHER_LATITUDE", "")
                lon = getattr(settings, "WEATHER_LONGITUDE", "")
                if not api_key or not lat or not lon:
                    raise HTTPException(
                        status_code=503,
                        detail="Weather provider not fully configured",
                    )
                weather = await _fetch_openweathermap(api_key, lat, lon)
            elif provider == "bom":
                lat = getattr(settings, "WEATHER_LATITUDE", "")
                lon = getattr(settings, "WEATHER_LONGITUDE", "")
                weather = await _fetch_bom(lat, lon)
            else:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": {
                            "code": "SERVICE_UNAVAILABLE",
                            "message": f"Unknown weather provider: {provider}",
                        }
                    },
                )

            from waggle.utils.timestamps import utc_now

            weather.fetched_at = utc_now()

            # Update cache
            _weather_cache["data"] = weather
            _weather_cache["fetched_at"] = now

            return weather
        except httpx.HTTPError:
            raise HTTPException(
                status_code=502, detail="Weather provider request failed"
            )

    return router
