"""Rachio API client for Smart Irrigation AI."""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from datetime import datetime

import aiohttp
from async_timeout import timeout as async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

RACHIO_API_BASE = "https://api.rach.io/1/public"
RACHIO_API_TIMEOUT = 30


class RachioAPIError(Exception):
    """Exception for Rachio API errors."""
    pass


class RachioAPI:
    """Rachio API client."""

    def __init__(self, api_key: str, hass: HomeAssistant) -> None:
        """Initialize the Rachio API client."""
        self._api_key = api_key
        self._hass = hass
        self._session: aiohttp.ClientSession | None = None
        self._person_id: str | None = None
        self._device_id: str | None = None
        self._device_info: dict[str, Any] = {}
        self._zones: list[dict[str, Any]] = []

    @property
    def headers(self) -> dict[str, str]:
        """Return API headers."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _async_request(
        self, method: str, endpoint: str, data: dict | None = None
    ) -> dict[str, Any]:
        """Make an API request."""
        if self._session is None:
            self._session = async_get_clientsession(self._hass)

        url = f"{RACHIO_API_BASE}/{endpoint}"

        try:
            async with async_timeout(RACHIO_API_TIMEOUT):
                if method == "GET":
                    response = await self._session.get(url, headers=self.headers)
                elif method == "POST":
                    response = await self._session.post(
                        url, headers=self.headers, json=data
                    )
                elif method == "PUT":
                    response = await self._session.put(
                        url, headers=self.headers, json=data
                    )
                else:
                    raise RachioAPIError(f"Unsupported method: {method}")

                if response.status == 204:
                    return {}

                if response.status not in (200, 201):
                    error_text = await response.text()
                    raise RachioAPIError(
                        f"API request failed: {response.status} - {error_text}"
                    )

                return await response.json()

        except asyncio.TimeoutError as err:
            raise RachioAPIError(f"API request timed out: {endpoint}") from err
        except aiohttp.ClientError as err:
            raise RachioAPIError(f"API request failed: {err}") from err

    async def async_verify_connection(self) -> bool:
        """Verify API connection and get person/device info."""
        try:
            # Get person info
            person_info = await self._async_request("GET", "person/info")
            self._person_id = person_info.get("id")

            if not self._person_id:
                _LOGGER.error("Failed to get person ID from Rachio")
                return False

            # Get person details with devices
            person_details = await self._async_request(
                "GET", f"person/{self._person_id}"
            )

            devices = person_details.get("devices", [])
            if not devices:
                _LOGGER.error("No Rachio devices found")
                return False

            # Use the first device (most users have one)
            self._device_info = devices[0]
            self._device_id = self._device_info.get("id")
            self._zones = self._device_info.get("zones", [])

            _LOGGER.info(
                "Connected to Rachio device: %s with %d zones",
                self._device_info.get("name"),
                len(self._zones),
            )
            return True

        except RachioAPIError as err:
            _LOGGER.error("Failed to verify Rachio connection: %s", err)
            return False

    async def async_get_device_info(self) -> dict[str, Any]:
        """Get device information."""
        if not self._device_id:
            await self.async_verify_connection()

        return {
            "id": self._device_id,
            "name": self._device_info.get("name"),
            "model": self._device_info.get("model"),
            "serial_number": self._device_info.get("serialNumber"),
            "mac_address": self._device_info.get("macAddress"),
            "status": self._device_info.get("status"),
            "latitude": self._device_info.get("latitude"),
            "longitude": self._device_info.get("longitude"),
            "timezone": self._device_info.get("timeZone"),
            "utc_offset": self._device_info.get("utcOffset"),
            "zip_code": self._device_info.get("zip"),
        }

    async def async_get_device_status(self) -> dict[str, Any]:
        """Get current device status."""
        if not self._device_id:
            await self.async_verify_connection()

        try:
            device = await self._async_request("GET", f"device/{self._device_id}")
            return {
                "status": device.get("status"),
                "on": device.get("on"),
                "paused": device.get("paused"),
                "rain_delay_expires": device.get("rainDelayExpirationDate"),
                "rain_delay_start": device.get("rainDelayStartDate"),
                "rain_sensor_tripped": device.get("rainSensorTripped", False),
                "last_run": device.get("lastRun"),
            }
        except RachioAPIError as err:
            _LOGGER.error("Failed to get device status: %s", err)
            return {}

    async def async_get_zones(self) -> list[dict[str, Any]]:
        """Get all zones."""
        if not self._device_id:
            await self.async_verify_connection()

        zones = []
        for zone in self._zones:
            zones.append({
                "id": zone.get("id"),
                "zone_number": zone.get("zoneNumber"),
                "name": zone.get("name"),
                "enabled": zone.get("enabled", True),
                "image_url": zone.get("imageUrl"),
                "custom_nozzle": zone.get("customNozzle", {}),
                "custom_soil": zone.get("customSoil", {}),
                "custom_slope": zone.get("customSlope", {}),
                "custom_shade": zone.get("customShade", {}),
                "custom_crop": zone.get("customCrop", {}),
                "available_water": zone.get("availableWater", 0),
                "root_zone_depth": zone.get("rootZoneDepth", 6),
                "efficiency": zone.get("efficiency", 0.8),
                "saturated_depth_of_water": zone.get("saturatedDepthOfWater", 0),
                "depth_of_water": zone.get("depthOfWater", 0),
                "max_runtime": zone.get("maxRuntime", 10800),
                "runtime": zone.get("runtime", 0),
                "last_watered_date": zone.get("lastWateredDate"),
                "last_watered_duration": zone.get("lastWateredDuration"),
            })

        return zones

    async def async_get_zones_status(self) -> dict[str, Any]:
        """Get current status of all zones."""
        if not self._device_id:
            await self.async_verify_connection()

        try:
            device = await self._async_request("GET", f"device/{self._device_id}")
            current_schedule = await self._async_get_current_schedule()

            zones_status = {}
            for zone in device.get("zones", []):
                zone_id = zone.get("id")
                zones_status[zone_id] = {
                    "id": zone_id,
                    "name": zone.get("name"),
                    "zone_number": zone.get("zoneNumber"),
                    "enabled": zone.get("enabled", True),
                    "running": current_schedule.get("running_zone") == zone_id,
                    "remaining_runtime": current_schedule.get("remaining_runtime", 0) if current_schedule.get("running_zone") == zone_id else 0,
                    "depth_of_water": zone.get("depthOfWater", 0),
                    "last_watered_date": zone.get("lastWateredDate"),
                    "last_watered_duration": zone.get("lastWateredDuration"),
                }

            return zones_status

        except RachioAPIError as err:
            _LOGGER.error("Failed to get zones status: %s", err)
            return {}

    async def _async_get_current_schedule(self) -> dict[str, Any]:
        """Get current running schedule."""
        try:
            current = await self._async_request(
                "GET", f"device/{self._device_id}/current_schedule"
            )
            if current:
                return {
                    "running_zone": current.get("zoneId"),
                    "remaining_runtime": current.get("remainingTime", 0),
                    "start_time": current.get("startTime"),
                    "schedule_type": current.get("type"),
                }
            return {}
        except RachioAPIError:
            return {}

    async def async_get_rain_sensor_status(self) -> dict[str, Any]:
        """Get rain sensor status from device."""
        if not self._device_id:
            await self.async_verify_connection()

        try:
            device = await self._async_request("GET", f"device/{self._device_id}")
            return {
                "tripped": device.get("rainSensorTripped", False),
                "rain_delay_active": device.get("rainDelayExpirationDate") is not None,
                "rain_delay_expires": device.get("rainDelayExpirationDate"),
            }
        except RachioAPIError as err:
            _LOGGER.error("Failed to get rain sensor status: %s", err)
            return {"tripped": False, "rain_delay_active": False}

    async def async_run_zone(self, zone_id: str, duration_seconds: int) -> bool:
        """Run a specific zone for the given duration."""
        try:
            await self._async_request(
                "PUT",
                "zone/start",
                {"id": zone_id, "duration": duration_seconds},
            )
            _LOGGER.info(
                "Started zone %s for %d seconds", zone_id, duration_seconds
            )
            return True
        except RachioAPIError as err:
            _LOGGER.error("Failed to start zone %s: %s", zone_id, err)
            return False

    async def async_run_multiple_zones(
        self, zones: list[dict[str, Any]]
    ) -> bool:
        """Run multiple zones in sequence.

        Args:
            zones: List of dicts with 'id' and 'duration' (in seconds)
        """
        try:
            await self._async_request(
                "PUT",
                "zone/start_multiple",
                {"zones": zones},
            )
            _LOGGER.info("Started %d zones in sequence", len(zones))
            return True
        except RachioAPIError as err:
            _LOGGER.error("Failed to start multiple zones: %s", err)
            return False

    async def async_stop_zone(self, zone_id: str) -> bool:
        """Stop a specific zone."""
        try:
            await self._async_request("PUT", "zone/stop", {"id": zone_id})
            _LOGGER.info("Stopped zone %s", zone_id)
            return True
        except RachioAPIError as err:
            _LOGGER.error("Failed to stop zone %s: %s", zone_id, err)
            return False

    async def async_stop_all(self) -> bool:
        """Stop all zones on the device."""
        if not self._device_id:
            await self.async_verify_connection()

        try:
            await self._async_request(
                "PUT", "device/stop_water", {"id": self._device_id}
            )
            _LOGGER.info("Stopped all zones")
            return True
        except RachioAPIError as err:
            _LOGGER.error("Failed to stop all zones: %s", err)
            return False

    async def async_set_rain_delay(self, duration_seconds: int) -> bool:
        """Set a rain delay on the device."""
        if not self._device_id:
            await self.async_verify_connection()

        try:
            await self._async_request(
                "PUT",
                "device/rain_delay",
                {"id": self._device_id, "duration": duration_seconds},
            )
            _LOGGER.info("Set rain delay for %d seconds", duration_seconds)
            return True
        except RachioAPIError as err:
            _LOGGER.error("Failed to set rain delay: %s", err)
            return False

    async def async_cancel_rain_delay(self) -> bool:
        """Cancel any active rain delay."""
        return await self.async_set_rain_delay(0)

    async def async_standby_on(self) -> bool:
        """Put device in standby mode."""
        if not self._device_id:
            await self.async_verify_connection()

        try:
            await self._async_request(
                "PUT", "device/off", {"id": self._device_id}
            )
            _LOGGER.info("Device put in standby mode")
            return True
        except RachioAPIError as err:
            _LOGGER.error("Failed to set standby mode: %s", err)
            return False

    async def async_standby_off(self) -> bool:
        """Take device out of standby mode."""
        if not self._device_id:
            await self.async_verify_connection()

        try:
            await self._async_request(
                "PUT", "device/on", {"id": self._device_id}
            )
            _LOGGER.info("Device taken out of standby mode")
            return True
        except RachioAPIError as err:
            _LOGGER.error("Failed to disable standby mode: %s", err)
            return False

    async def async_get_forecast(self) -> list[dict[str, Any]]:
        """Get weather forecast from Rachio."""
        if not self._device_id:
            await self.async_verify_connection()

        try:
            forecast = await self._async_request(
                "GET", f"device/{self._device_id}/forecast?units=US"
            )
            return forecast.get("forecast", [])
        except RachioAPIError as err:
            _LOGGER.error("Failed to get forecast: %s", err)
            return []

    async def async_get_events(
        self, start_time: int | None = None, end_time: int | None = None
    ) -> list[dict[str, Any]]:
        """Get device events/history."""
        if not self._device_id:
            await self.async_verify_connection()

        try:
            # If no times specified, get last 7 days
            if start_time is None:
                import time
                end_time = int(time.time() * 1000)
                start_time = end_time - (7 * 24 * 60 * 60 * 1000)

            events = await self._async_request(
                "GET",
                f"device/{self._device_id}/event?startTime={start_time}&endTime={end_time}",
            )
            return events if isinstance(events, list) else []
        except RachioAPIError as err:
            _LOGGER.error("Failed to get events: %s", err)
            return []
