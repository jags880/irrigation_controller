"""Rachio Controller wrapper for Smart Irrigation AI."""
from __future__ import annotations

import logging
from typing import Any
from datetime import datetime, timedelta

from .api import RachioAPI

_LOGGER = logging.getLogger(__name__)


class RachioController:
    """High-level controller for Rachio operations."""

    def __init__(self, api: RachioAPI) -> None:
        """Initialize the controller."""
        self._api = api
        self._zones_cache: dict[str, dict[str, Any]] = {}
        self._last_cache_update: datetime | None = None
        self._cache_ttl = timedelta(minutes=5)

    async def async_refresh_zones_cache(self) -> None:
        """Refresh the zones cache."""
        zones = await self._api.async_get_zones()
        self._zones_cache = {z["id"]: z for z in zones}
        self._last_cache_update = datetime.now()

    async def async_get_zone(self, zone_id: str) -> dict[str, Any] | None:
        """Get a specific zone by ID."""
        if (
            self._last_cache_update is None
            or datetime.now() - self._last_cache_update > self._cache_ttl
        ):
            await self.async_refresh_zones_cache()

        return self._zones_cache.get(zone_id)

    async def async_get_zone_by_number(self, zone_number: int) -> dict[str, Any] | None:
        """Get a specific zone by zone number."""
        if (
            self._last_cache_update is None
            or datetime.now() - self._last_cache_update > self._cache_ttl
        ):
            await self.async_refresh_zones_cache()

        for zone in self._zones_cache.values():
            if zone.get("zone_number") == zone_number:
                return zone
        return None

    async def async_water_zone(
        self, zone_id: str, duration_minutes: int, reason: str = ""
    ) -> bool:
        """Water a specific zone."""
        zone = await self.async_get_zone(zone_id)
        if not zone:
            _LOGGER.error("Zone %s not found", zone_id)
            return False

        if not zone.get("enabled", True):
            _LOGGER.warning("Zone %s is disabled, skipping", zone_id)
            return False

        # Convert to seconds and respect max runtime
        duration_seconds = min(
            duration_minutes * 60,
            zone.get("max_runtime", 10800),
        )

        _LOGGER.info(
            "Watering zone %s (%s) for %d minutes. Reason: %s",
            zone.get("name"),
            zone_id,
            duration_seconds // 60,
            reason,
        )

        return await self._api.async_run_zone(zone_id, duration_seconds)

    async def async_run_schedule(
        self, zones_schedule: list[dict[str, Any]]
    ) -> bool:
        """Run a complete watering schedule.

        Args:
            zones_schedule: List of dicts with:
                - zone_id: Zone ID
                - duration_minutes: Duration in minutes
                - reason: Why this zone is being watered (optional)
        """
        if not zones_schedule:
            _LOGGER.info("No zones to water in schedule")
            return True

        # Build the zones list for the API
        zones_to_run = []
        for item in zones_schedule:
            zone = await self.async_get_zone(item["zone_id"])
            if not zone:
                _LOGGER.warning("Zone %s not found, skipping", item["zone_id"])
                continue

            if not zone.get("enabled", True):
                _LOGGER.warning(
                    "Zone %s (%s) is disabled, skipping",
                    zone.get("name"),
                    item["zone_id"],
                )
                continue

            duration_seconds = min(
                item["duration_minutes"] * 60,
                zone.get("max_runtime", 10800),
            )

            zones_to_run.append({
                "id": item["zone_id"],
                "duration": duration_seconds,
                "sortOrder": len(zones_to_run) + 1,
            })

            _LOGGER.info(
                "Scheduled zone %s (%s) for %d minutes. Reason: %s",
                zone.get("name"),
                item["zone_id"],
                duration_seconds // 60,
                item.get("reason", "Scheduled watering"),
            )

        if not zones_to_run:
            _LOGGER.info("No enabled zones to water")
            return True

        return await self._api.async_run_multiple_zones(zones_to_run)

    async def async_stop_current(self) -> bool:
        """Stop any currently running zone."""
        return await self._api.async_stop_all()

    async def async_get_running_status(self) -> dict[str, Any]:
        """Get the current running status."""
        zones_status = await self._api.async_get_zones_status()

        for zone_id, status in zones_status.items():
            if status.get("running"):
                return {
                    "running": True,
                    "zone_id": zone_id,
                    "zone_name": status.get("name"),
                    "remaining_runtime": status.get("remaining_runtime", 0),
                }

        return {"running": False}

    async def async_get_watering_history(
        self, days: int = 7
    ) -> list[dict[str, Any]]:
        """Get watering history for the past N days."""
        events = await self._api.async_get_events()

        watering_events = []
        for event in events:
            event_type = event.get("type", "")
            if "ZONE" in event_type and "RUN" in event_type:
                watering_events.append({
                    "timestamp": event.get("createDate"),
                    "zone_id": event.get("zoneId"),
                    "zone_name": event.get("zoneName"),
                    "duration": event.get("duration", 0),
                    "type": event_type,
                    "summary": event.get("summary"),
                })

        return watering_events

    async def async_calculate_water_applied(
        self, zone_id: str, days: int = 7
    ) -> float:
        """Calculate total water applied to a zone in the past N days (in inches)."""
        zone = await self.async_get_zone(zone_id)
        if not zone:
            return 0.0

        history = await self.async_get_watering_history(days)
        zone_history = [h for h in history if h.get("zone_id") == zone_id]

        # Calculate based on nozzle precipitation rate and duration
        nozzle = zone.get("custom_nozzle", {})
        precip_rate = nozzle.get("inchesPerHour", 1.5)  # Default spray head rate

        total_minutes = sum(h.get("duration", 0) / 60 for h in zone_history)
        total_inches = (total_minutes / 60) * precip_rate

        return round(total_inches, 2)
