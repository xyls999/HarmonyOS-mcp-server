"""
Weather tools.
"""

import asyncio
import json
import os
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


def _fetch_weather(location: str) -> dict[str, Any]:
    place = quote(location.strip())
    path = f"/{place}" if place else ""
    url = f"https://wttr.in{path}?format=j1"
    request = Request(url, headers={"User-Agent": "HarmonyOS-MCP/0.1"})

    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


async def get_local_weather(location: str = "") -> dict[str, Any]:
    """
    Get current weather.

    Args:
        location: Optional city name. If empty, wttr.in uses the caller IP location.

    Returns:
        A compact weather report with current condition and nearest area.
    """
    location = location or os.getenv("LOCAL_WEATHER_LOCATION", "")
    data = await asyncio.to_thread(_fetch_weather, location)
    current = data.get("current_condition", [{}])[0]
    nearest = data.get("nearest_area", [{}])[0]

    area = nearest.get("areaName", [{}])[0].get("value", "")
    country = nearest.get("country", [{}])[0].get("value", "")
    weather_desc = current.get("weatherDesc", [{}])[0].get("value", "")

    return {
        "location": location or f"{area}, {country}".strip(", "),
        "temperature_c": current.get("temp_C"),
        "feels_like_c": current.get("FeelsLikeC"),
        "humidity": current.get("humidity"),
        "wind_kmph": current.get("windspeedKmph"),
        "condition": weather_desc,
        "observation_time": current.get("observation_time"),
    }
