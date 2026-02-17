"""
OpenWeather Adapter - Real weather data from OpenWeatherMap API.

API docs: https://openweathermap.org/current
Free tier: 60 calls/min, 1M calls/month
Auth: API key as query parameter (?appid=KEY)
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import aiohttp

from shared.adapters.base import BaseAdapter, AdapterConfig
from shared.adapters.registry import register_adapter
from shared.schemas.canonical import (
    GeoPoint,
    WeatherCondition,
    WeatherData,
    WeatherForecast,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openweathermap.org/data/2.5"

# OpenWeather condition ID → canonical WeatherCondition
_CONDITION_MAP = {
    range(200, 300): WeatherCondition.THUNDERSTORM,
    range(300, 400): WeatherCondition.DRIZZLE,
    range(500, 600): WeatherCondition.RAIN,
    range(600, 700): WeatherCondition.SNOW,
    range(700, 712): WeatherCondition.MIST,
    range(712, 742): WeatherCondition.HAZE,
    range(742, 770): WeatherCondition.FOG,
    range(770, 800): WeatherCondition.EXTREME,
}


def _map_condition(weather_id: int) -> WeatherCondition:
    """Map OpenWeather condition ID to canonical enum."""
    if weather_id == 800:
        return WeatherCondition.CLEAR
    if weather_id > 800:
        return WeatherCondition.CLOUDS
    for id_range, condition in _CONDITION_MAP.items():
        if weather_id in id_range:
            return condition
    return WeatherCondition.CLEAR


@register_adapter(
    category="weather",
    platform="openweather",
    display_name="OpenWeather",
    description="Current weather and 5-day forecast from OpenWeatherMap",
    icon="\U0001f324\ufe0f",
    requires_auth=True,
    auth_type="api_key",
)
class OpenWeatherAdapter(BaseAdapter[WeatherData]):
    """Adapter for OpenWeatherMap API (free tier)."""

    category = "weather"
    platform = "openweather"

    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        api_key = config.credentials.get("api_key", "")
        if not api_key:
            raise ValueError("OpenWeather API key not configured (credentials.api_key)")

        city = config.settings.get("city", "Toronto,CA")
        units = config.settings.get("units", "metric")
        include_forecast = config.settings.get("include_forecast", True)

        result: Dict[str, Any] = {}

        async with aiohttp.ClientSession() as session:
            # Current weather
            params = {"q": city, "appid": api_key, "units": units}
            async with session.get(
                f"{BASE_URL}/weather",
                params=params,
                timeout=aiohttp.ClientTimeout(total=config.timeout_seconds),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise ValueError(f"OpenWeather API error {resp.status}: {body}")
                result["current"] = await resp.json()

            # 5-day / 3-hour forecast
            if include_forecast:
                params["cnt"] = config.settings.get("forecast_count", 8)
                async with session.get(
                    f"{BASE_URL}/forecast",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=config.timeout_seconds),
                ) as resp:
                    if resp.status == 200:
                        result["forecast"] = await resp.json()

        return result

    def transform(self, raw_data: Dict[str, Any]) -> List[WeatherData]:
        items: List = []

        # Transform current weather
        current = raw_data.get("current")
        if current:
            items.append(self._transform_current(current))

        # Transform forecast entries as WeatherForecast objects stored in metadata
        forecast_data = raw_data.get("forecast", {})
        forecast_list = forecast_data.get("list", [])
        forecasts = [self._transform_forecast_entry(f) for f in forecast_list]

        if items and forecasts:
            items[0].metadata["forecasts"] = [f.to_dict() for f in forecasts]

        return items

    def _transform_current(self, data: Dict[str, Any]) -> WeatherData:
        weather = data.get("weather", [{}])[0]
        main = data.get("main", {})
        wind = data.get("wind", {})
        coord = data.get("coord", {})

        ts = datetime.fromtimestamp(data.get("dt", 0), tz=timezone.utc)
        loc_str = f"{coord.get('lat', 0)}:{coord.get('lon', 0)}:{data.get('dt', 0)}"
        stable_id = f"ow:{hashlib.md5(loc_str.encode()).hexdigest()[:12]}"

        return WeatherData(
            id=stable_id,
            timestamp=ts,
            location=GeoPoint(
                latitude=coord.get("lat", 0.0),
                longitude=coord.get("lon", 0.0),
                name=data.get("name"),
            ),
            temperature_celsius=main.get("temp", 0.0),
            feels_like_celsius=main.get("feels_like", 0.0),
            humidity=main.get("humidity", 0),
            pressure_hpa=main.get("pressure", 0.0),
            wind_speed_ms=wind.get("speed", 0.0),
            wind_direction_deg=wind.get("deg", 0),
            condition=_map_condition(weather.get("id", 800)),
            description=weather.get("description", ""),
            icon_code=weather.get("icon", ""),
            visibility_meters=data.get("visibility", 10000),
            clouds_percent=data.get("clouds", {}).get("all", 0),
            platform="openweather",
        )

    def _transform_forecast_entry(self, data: Dict[str, Any]) -> WeatherForecast:
        weather = data.get("weather", [{}])[0]
        main = data.get("main", {})

        ts = datetime.fromtimestamp(data.get("dt", 0), tz=timezone.utc)
        loc_str = f"forecast:{data.get('dt', 0)}"
        stable_id = f"ow:{hashlib.md5(loc_str.encode()).hexdigest()[:12]}"

        return WeatherForecast(
            id=stable_id,
            location=GeoPoint(latitude=0.0, longitude=0.0),
            forecast_time=ts,
            temperature_celsius=main.get("temp", 0.0),
            feels_like_celsius=main.get("feels_like", 0.0),
            condition=_map_condition(weather.get("id", 800)),
            description=weather.get("description", ""),
            precipitation_probability=data.get("pop", 0.0),
            precipitation_mm=data.get("rain", {}).get("3h", 0.0)
            + data.get("snow", {}).get("3h", 0.0),
            humidity=main.get("humidity", 0),
            wind_speed_ms=data.get("wind", {}).get("speed", 0.0),
            platform="openweather",
        )

    @classmethod
    def normalize_category_for_tools(cls, raw_category_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize weather data for tool consumption."""
        return {
            "current": raw_category_data.get("current"),
            "forecasts": raw_category_data.get("forecasts", [])[:8],
            "platforms": raw_category_data.get("platforms", []),
        }

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": False,
            "real_time": True,
            "batch": False,
            "webhooks": False,
            "current_weather": True,
            "forecast": True,
        }
