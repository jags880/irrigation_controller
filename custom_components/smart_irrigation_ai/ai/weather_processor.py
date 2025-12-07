"""Weather data processor for Smart Irrigation AI."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..const import (
    RAIN_THRESHOLD_LIGHT,
    RAIN_THRESHOLD_MODERATE,
    RAIN_THRESHOLD_HEAVY,
    WIND_THRESHOLD_HIGH,
    WIND_THRESHOLD_VERY_HIGH,
    TEMP_THRESHOLD_FREEZE,
    TEMP_THRESHOLD_HOT,
)

_LOGGER = logging.getLogger(__name__)


class WeatherProcessor:
    """Process weather data for irrigation decisions."""

    def __init__(self) -> None:
        """Initialize the weather processor."""
        self._current_weather: dict[str, Any] = {}
        self._forecast: list[dict[str, Any]] = []
        self._historical: list[dict[str, Any]] = []
        self._last_update: datetime | None = None

    def update(
        self,
        current_weather: dict[str, Any],
        forecast: list[dict[str, Any]] | None = None,
    ) -> None:
        """Update weather data."""
        self._current_weather = current_weather
        if forecast:
            self._forecast = forecast
        self._last_update = datetime.now(timezone.utc)

    @property
    def current_temperature(self) -> float | None:
        """Get current temperature in Fahrenheit."""
        temp = self._current_weather.get("temperature")
        if temp is not None:
            return float(temp)
        return None

    @property
    def current_humidity(self) -> float | None:
        """Get current humidity percentage."""
        humidity = self._current_weather.get("humidity")
        if humidity is not None:
            return float(humidity)
        return None

    @property
    def current_wind_speed(self) -> float | None:
        """Get current wind speed in mph."""
        wind = self._current_weather.get("wind_speed")
        if wind is not None:
            return float(wind)
        return None

    @property
    def current_condition(self) -> str:
        """Get current weather condition."""
        return self._current_weather.get("condition", "unknown")

    def get_precipitation_last_24h(self) -> float:
        """Get precipitation in the last 24 hours (inches)."""
        return self._current_weather.get("precipitation", 0.0)

    def get_precipitation_next_24h(self) -> float:
        """Get forecasted precipitation for next 24 hours (inches)."""
        total = 0.0
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=24)

        for forecast in self._forecast:
            forecast_time = forecast.get("datetime")
            if forecast_time:
                if isinstance(forecast_time, str):
                    try:
                        forecast_time = datetime.fromisoformat(forecast_time.replace("Z", "+00:00"))
                    except ValueError:
                        continue

                if now <= forecast_time <= cutoff:
                    precip = forecast.get("precipitation", 0) or 0
                    total += precip

        return total

    def get_precipitation_probability_next_24h(self) -> float:
        """Get average precipitation probability for next 24 hours."""
        probabilities = []
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=24)

        for forecast in self._forecast:
            forecast_time = forecast.get("datetime")
            if forecast_time:
                if isinstance(forecast_time, str):
                    try:
                        forecast_time = datetime.fromisoformat(forecast_time.replace("Z", "+00:00"))
                    except ValueError:
                        continue

                if now <= forecast_time <= cutoff:
                    prob = forecast.get("precipitation_probability")
                    if prob is not None:
                        probabilities.append(prob)

        return sum(probabilities) / len(probabilities) if probabilities else 0

    def get_temperature_range_next_24h(self) -> tuple[float | None, float | None]:
        """Get min and max temperature forecast for next 24 hours."""
        temps = []
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=24)

        for forecast in self._forecast:
            forecast_time = forecast.get("datetime")
            if forecast_time:
                if isinstance(forecast_time, str):
                    try:
                        forecast_time = datetime.fromisoformat(forecast_time.replace("Z", "+00:00"))
                    except ValueError:
                        continue

                if now <= forecast_time <= cutoff:
                    temp = forecast.get("temperature")
                    if temp is not None:
                        temps.append(temp)

        if temps:
            return min(temps), max(temps)
        return None, None

    def get_weather_factor(self) -> float:
        """Calculate a weather adjustment factor for irrigation.

        Returns:
            Factor between 0.0 and 1.5:
            - 0.0 = Skip watering (rain, freeze)
            - 0.5-0.8 = Reduce watering
            - 1.0 = Normal watering
            - 1.1-1.5 = Increase watering (hot, dry, windy)
        """
        factor = 1.0
        skip_reasons = []
        adjustment_reasons = []

        # Check for freezing conditions
        temp = self.current_temperature
        if temp is not None and temp <= TEMP_THRESHOLD_FREEZE:
            return 0.0  # Skip watering

        # Check recent precipitation
        recent_precip = self.get_precipitation_last_24h()
        if recent_precip >= RAIN_THRESHOLD_HEAVY:
            return 0.0  # Skip watering
        elif recent_precip >= RAIN_THRESHOLD_MODERATE:
            factor *= 0.5
            adjustment_reasons.append(f"Recent moderate rain ({recent_precip}in)")
        elif recent_precip >= RAIN_THRESHOLD_LIGHT:
            factor *= 0.75
            adjustment_reasons.append(f"Recent light rain ({recent_precip}in)")

        # Check forecasted precipitation
        forecast_precip = self.get_precipitation_next_24h()
        forecast_prob = self.get_precipitation_probability_next_24h()

        if forecast_prob > 70 and forecast_precip >= RAIN_THRESHOLD_MODERATE:
            factor *= 0.3  # Likely significant rain coming
            adjustment_reasons.append(f"Rain likely ({forecast_prob}% chance, {forecast_precip}in)")
        elif forecast_prob > 50 and forecast_precip >= RAIN_THRESHOLD_LIGHT:
            factor *= 0.6
            adjustment_reasons.append(f"Rain possible ({forecast_prob}% chance)")

        # High temperature adjustment
        if temp is not None:
            if temp >= TEMP_THRESHOLD_HOT:
                factor *= 1.3
                adjustment_reasons.append(f"Hot temperature ({temp}°F)")
            elif temp >= TEMP_THRESHOLD_HOT - 10:
                factor *= 1.15
                adjustment_reasons.append(f"Warm temperature ({temp}°F)")

        # Wind adjustment
        wind = self.current_wind_speed
        if wind is not None:
            if wind >= WIND_THRESHOLD_VERY_HIGH:
                # High wind reduces irrigation efficiency significantly
                # But also increases ET, so adjust accordingly
                factor *= 0.7  # Reduce due to drift/evaporation
                adjustment_reasons.append(f"Very high wind ({wind} mph)")
            elif wind >= WIND_THRESHOLD_HIGH:
                factor *= 0.85
                adjustment_reasons.append(f"High wind ({wind} mph)")

        # Humidity adjustment
        humidity = self.current_humidity
        if humidity is not None:
            if humidity < 30:
                factor *= 1.15  # Very dry air increases ET
                adjustment_reasons.append(f"Low humidity ({humidity}%)")
            elif humidity > 80:
                factor *= 0.9  # High humidity reduces ET
                adjustment_reasons.append(f"High humidity ({humidity}%)")

        # Weather condition adjustments
        condition = self.current_condition.lower()
        if "rain" in condition or "shower" in condition:
            if "light" in condition:
                factor *= 0.7
            else:
                factor *= 0.3
            adjustment_reasons.append(f"Current condition: {condition}")
        elif "cloudy" in condition or "overcast" in condition:
            factor *= 0.9  # Reduced solar radiation
            adjustment_reasons.append(f"Cloudy conditions")
        elif "sunny" in condition or "clear" in condition:
            factor *= 1.05
            adjustment_reasons.append(f"Sunny conditions")

        # Clamp to reasonable range
        factor = max(0.0, min(1.5, factor))

        _LOGGER.debug(
            "Weather factor: %.2f (adjustments: %s)",
            factor,
            ", ".join(adjustment_reasons) if adjustment_reasons else "none",
        )

        return factor

    def should_skip_watering(self) -> tuple[bool, str]:
        """Determine if watering should be skipped entirely.

        Returns:
            Tuple of (should_skip, reason)
        """
        # Freezing conditions
        temp = self.current_temperature
        if temp is not None and temp <= TEMP_THRESHOLD_FREEZE:
            return True, f"Freezing temperature ({temp}°F)"

        # Currently raining
        condition = self.current_condition.lower()
        if "rain" in condition and "light" not in condition:
            return True, f"Currently raining ({condition})"

        # Heavy recent precipitation
        recent_precip = self.get_precipitation_last_24h()
        if recent_precip >= RAIN_THRESHOLD_HEAVY:
            return True, f"Heavy recent precipitation ({recent_precip}in)"

        # Very high winds
        wind = self.current_wind_speed
        if wind is not None and wind >= 30:
            return True, f"Dangerous wind speed ({wind} mph)"

        # Heavy rain imminent (high probability + high amount)
        forecast_precip = self.get_precipitation_next_24h()
        forecast_prob = self.get_precipitation_probability_next_24h()
        if forecast_prob >= 80 and forecast_precip >= RAIN_THRESHOLD_HEAVY:
            return True, f"Heavy rain imminent ({forecast_prob}% chance of {forecast_precip}in)"

        return False, ""

    def get_optimal_watering_window(self) -> tuple[int, int]:
        """Get the optimal watering window (start hour, end hour).

        Considers wind, temperature, and evaporation to find the best time.
        Returns hours in 24-hour format.
        """
        # Default: Early morning is best (less evaporation, less wind)
        default_start = 5
        default_end = 9

        # Look at forecast to find optimal window
        best_window = (default_start, default_end)
        best_score = float("-inf")

        for start_hour in range(0, 12):  # Check early hours
            end_hour = start_hour + 4  # 4-hour window

            score = 0
            for forecast in self._forecast:
                forecast_time = forecast.get("datetime")
                if forecast_time:
                    if isinstance(forecast_time, str):
                        try:
                            forecast_time = datetime.fromisoformat(forecast_time.replace("Z", "+00:00"))
                        except ValueError:
                            continue

                    if start_hour <= forecast_time.hour < end_hour:
                        # Lower temperature = better
                        temp = forecast.get("temperature", 70)
                        score -= (temp - 60) * 0.5

                        # Lower wind = better
                        wind = forecast.get("wind_speed", 5)
                        score -= wind * 2

                        # Higher humidity = less evaporation
                        humidity = forecast.get("humidity", 50)
                        score += humidity * 0.1

            if score > best_score:
                best_score = score
                best_window = (start_hour, end_hour)

        return best_window

    def get_et_factors(self) -> dict[str, float]:
        """Get factors for ET calculation from current weather."""
        temp = self.current_temperature
        humidity = self.current_humidity
        wind = self.current_wind_speed

        return {
            "temperature_f": temp if temp is not None else 70,
            "temperature_c": (temp - 32) * 5 / 9 if temp is not None else 21,
            "humidity": humidity if humidity is not None else 50,
            "wind_speed_mph": wind if wind is not None else 5,
            "wind_speed_ms": wind * 0.44704 if wind is not None else 2.2,
            "solar_factor": self._get_solar_factor(),
        }

    def _get_solar_factor(self) -> float:
        """Estimate solar radiation factor from weather condition."""
        condition = self.current_condition.lower()

        if "sunny" in condition or "clear" in condition:
            return 1.0
        elif "partly" in condition:
            return 0.75
        elif "cloudy" in condition:
            return 0.5
        elif "overcast" in condition:
            return 0.35
        elif "rain" in condition or "storm" in condition:
            return 0.25
        else:
            return 0.6  # Default moderate

    def get_status(self) -> dict[str, Any]:
        """Get current weather processor status."""
        return {
            "temperature": self.current_temperature,
            "humidity": self.current_humidity,
            "wind_speed": self.current_wind_speed,
            "condition": self.current_condition,
            "precipitation_last_24h": self.get_precipitation_last_24h(),
            "precipitation_next_24h": self.get_precipitation_next_24h(),
            "precipitation_probability": self.get_precipitation_probability_next_24h(),
            "weather_factor": self.get_weather_factor(),
            "should_skip": self.should_skip_watering(),
            "last_update": self._last_update.isoformat() if self._last_update else None,
        }
