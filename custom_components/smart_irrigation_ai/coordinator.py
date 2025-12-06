"""Data update coordinator for Smart Irrigation AI."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)


class SmartIrrigationCoordinator(DataUpdateCoordinator):
    """Coordinator for Smart Irrigation AI data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        rachio_api,
        ai_model,
        scheduler,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.entry = entry
        self.rachio_api = rachio_api
        self.ai_model = ai_model
        self.scheduler = scheduler
        self._zones_data: dict[str, Any] = {}
        self._device_data: dict[str, Any] = {}
        self._weather_data: dict[str, Any] = {}
        self._moisture_data: dict[str, Any] = {}
        self._schedule_data: dict[str, Any] = {}
        self._ai_recommendations: dict[str, Any] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from all sources."""
        try:
            # Fetch Rachio device status
            self._device_data = await self.rachio_api.async_get_device_status()

            # Fetch zone statuses
            self._zones_data = await self.rachio_api.async_get_zones_status()

            # Get weather data from configured weather entity
            self._weather_data = await self._async_get_weather_data()

            # Get moisture sensor data
            self._moisture_data = await self._async_get_moisture_data()

            # Get rain sensor status
            rain_sensor_data = await self._async_get_rain_sensor_data()

            # Update AI model with latest data
            await self.ai_model.async_update_inputs(
                weather_data=self._weather_data,
                moisture_data=self._moisture_data,
                rain_sensor_data=rain_sensor_data,
            )

            # Get AI recommendations for all zones
            self._ai_recommendations = await self.ai_model.async_get_all_recommendations()

            # Get current schedule
            self._schedule_data = await self.scheduler.async_get_schedule()

            return {
                "device": self._device_data,
                "zones": self._zones_data,
                "weather": self._weather_data,
                "moisture": self._moisture_data,
                "rain_sensor": rain_sensor_data,
                "recommendations": self._ai_recommendations,
                "schedule": self._schedule_data,
                "last_update": datetime.now().isoformat(),
            }

        except Exception as err:
            _LOGGER.error("Error fetching Smart Irrigation data: %s", err)
            raise UpdateFailed(f"Error fetching data: {err}") from err

    async def _async_get_weather_data(self) -> dict[str, Any]:
        """Get weather data from Home Assistant weather entity."""
        weather_entity = self.entry.data.get("weather_entity")
        if not weather_entity:
            return {}

        state = self.hass.states.get(weather_entity)
        if not state:
            _LOGGER.warning("Weather entity %s not found", weather_entity)
            return {}

        attributes = state.attributes
        return {
            "condition": state.state,
            "temperature": attributes.get("temperature"),
            "humidity": attributes.get("humidity"),
            "wind_speed": attributes.get("wind_speed"),
            "wind_bearing": attributes.get("wind_bearing"),
            "pressure": attributes.get("pressure"),
            "visibility": attributes.get("visibility"),
            "forecast": attributes.get("forecast", []),
            "precipitation": attributes.get("precipitation", 0),
            "precipitation_probability": attributes.get("precipitation_probability", 0),
        }

    async def _async_get_moisture_data(self) -> dict[str, Any]:
        """Get moisture sensor data from configured sensors."""
        moisture_sensors = self.entry.data.get("moisture_sensors", {})
        moisture_data = {}

        for zone_id, sensor_entity in moisture_sensors.items():
            if not sensor_entity:
                continue

            state = self.hass.states.get(sensor_entity)
            if state:
                try:
                    moisture_data[zone_id] = {
                        "value": float(state.state) if state.state not in ("unknown", "unavailable") else None,
                        "unit": state.attributes.get("unit_of_measurement", "%"),
                        "last_updated": state.last_updated.isoformat() if state.last_updated else None,
                    }
                except (ValueError, TypeError):
                    moisture_data[zone_id] = {"value": None, "unit": "%", "last_updated": None}
            else:
                _LOGGER.debug("Moisture sensor %s not found for zone %s", sensor_entity, zone_id)

        return moisture_data

    async def _async_get_rain_sensor_data(self) -> dict[str, Any]:
        """Get rain sensor data from Rachio or configured sensor."""
        # First try to get from Rachio device
        rain_sensor = await self.rachio_api.async_get_rain_sensor_status()

        # Also check for configured external rain sensor
        external_rain_sensor = self.entry.data.get("rain_sensor")
        if external_rain_sensor:
            state = self.hass.states.get(external_rain_sensor)
            if state:
                rain_sensor["external"] = {
                    "state": state.state,
                    "value": state.attributes.get("rain_rate") or state.attributes.get("precipitation"),
                    "last_updated": state.last_updated.isoformat() if state.last_updated else None,
                }

        return rain_sensor

    @property
    def zones_data(self) -> dict[str, Any]:
        """Return zones data."""
        return self._zones_data

    @property
    def device_data(self) -> dict[str, Any]:
        """Return device data."""
        return self._device_data

    @property
    def weather_data(self) -> dict[str, Any]:
        """Return weather data."""
        return self._weather_data

    @property
    def moisture_data(self) -> dict[str, Any]:
        """Return moisture data."""
        return self._moisture_data

    @property
    def schedule_data(self) -> dict[str, Any]:
        """Return schedule data."""
        return self._schedule_data

    @property
    def ai_recommendations(self) -> dict[str, Any]:
        """Return AI recommendations."""
        return self._ai_recommendations
