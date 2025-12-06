"""Home Assistant Rachio integration controller for Smart Irrigation AI.

This module provides zone control through the existing Home Assistant Rachio integration,
avoiding duplicate API calls and leveraging existing entity states.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.const import STATE_ON, STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN

_LOGGER = logging.getLogger(__name__)

# Rachio integration domain
RACHIO_DOMAIN = "rachio"

# Rachio services
SERVICE_START_WATERING = "start_watering"
SERVICE_STOP_WATERING = "stop_watering"
SERVICE_PAUSE_WATERING = "pause_watering"
SERVICE_RESUME_WATERING = "resume_watering"
SERVICE_SET_RAIN_DELAY = "set_rain_delay"


class HAZoneController:
    """Controller that uses Home Assistant's Rachio integration for zone control."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the controller.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._zones_cache: dict[str, dict[str, Any]] = {}
        self._device_id: str | None = None

    async def async_discover_rachio_entities(self) -> dict[str, Any]:
        """Discover Rachio entities from Home Assistant.

        Returns:
            Dictionary with device info, zones, and sensors
        """
        entity_reg = er.async_get(self.hass)

        zones = []
        rain_sensors = []
        device_info = {}
        controller_switches = []

        _LOGGER.debug("Starting Rachio entity discovery")

        # Find all Rachio entities
        for entity in entity_reg.entities.values():
            if entity.platform != RACHIO_DOMAIN:
                continue

            _LOGGER.debug("Found Rachio entity: %s (domain: %s)", entity.entity_id, entity.domain)

            # Get entity state
            state = self.hass.states.get(entity.entity_id)
            if not state:
                _LOGGER.debug("No state for entity: %s", entity.entity_id)
                continue

            # Zone switches - Rachio zones are switches but NOT the main controller
            # The main controller switch typically has "controller" or is the device itself
            if entity.domain == "switch":
                # Check if this is a zone by looking at attributes or unique_id
                # Rachio zone unique_ids typically contain the zone ID
                # Controller switches have different patterns
                is_controller = (
                    "controller" in entity.entity_id.lower() or
                    "standby" in entity.entity_id.lower() or
                    state.attributes.get("device_class") == "switch"
                )

                # Also check if it has zone-specific attributes
                has_zone_attrs = (
                    state.attributes.get("zone_number") is not None or
                    "zone" in entity.entity_id.lower() or
                    # Rachio zones have these attributes
                    state.attributes.get("enabled") is not None
                )

                if is_controller:
                    controller_switches.append(entity.entity_id)
                    _LOGGER.debug("Identified as controller switch: %s", entity.entity_id)
                else:
                    # This is likely a zone switch
                    zone_num = self._extract_zone_number(entity.entity_id, state)
                    zone_info = {
                        "entity_id": entity.entity_id,
                        "name": state.attributes.get("friendly_name", entity.entity_id),
                        "zone_id": entity.unique_id or entity.entity_id,
                        "enabled": state.state != STATE_UNAVAILABLE,
                        "zone_number": zone_num,
                    }
                    zones.append(zone_info)
                    _LOGGER.debug("Found zone: %s (zone_number: %d)", entity.entity_id, zone_num)

                    # Get device info from first zone
                    if not device_info and entity.device_id:
                        self._device_id = entity.device_id
                        device_info = await self._get_device_info(entity.device_id)

            # Rain sensor
            elif entity.domain == "binary_sensor" and "rain" in entity.entity_id.lower():
                rain_sensors.append({
                    "entity_id": entity.entity_id,
                    "name": state.attributes.get("friendly_name", "Rain Sensor"),
                    "state": state.state == STATE_ON,
                })
                _LOGGER.debug("Found rain sensor: %s", entity.entity_id)

        # Sort zones by zone number
        zones.sort(key=lambda z: z.get("zone_number", 0))

        _LOGGER.info(
            "Rachio discovery complete: %d zones, %d rain sensors, %d controller switches",
            len(zones), len(rain_sensors), len(controller_switches)
        )

        return {
            "device_info": device_info,
            "zones": zones,
            "rain_sensors": rain_sensors,
        }

    async def _get_device_info(self, device_id: str) -> dict[str, Any]:
        """Get device information from device registry."""
        from homeassistant.helpers import device_registry as dr

        device_reg = dr.async_get(self.hass)
        device = device_reg.async_get(device_id)

        if device:
            return {
                "id": device_id,
                "name": device.name or "Rachio Controller",
                "model": device.model,
                "manufacturer": device.manufacturer,
                "sw_version": device.sw_version,
            }
        return {"id": device_id, "name": "Rachio Controller"}

    def _extract_zone_number(self, entity_id: str, state) -> int:
        """Extract zone number from entity or attributes."""
        # Try from attributes first
        zone_num = state.attributes.get("zone_number")
        if zone_num is not None:
            return int(zone_num)

        # Try to extract from entity_id (e.g., switch.rachio_front_lawn_zone_1)
        import re
        match = re.search(r'zone[_\s]*(\d+)', entity_id.lower())
        if match:
            return int(match.group(1))

        # Fallback - use order
        return 0

    async def async_get_zones(self) -> list[dict[str, Any]]:
        """Get all Rachio zones from Home Assistant.

        Returns:
            List of zone dictionaries
        """
        discovery = await self.async_discover_rachio_entities()
        return discovery.get("zones", [])

    async def async_get_zone_status(self, zone_entity_id: str) -> dict[str, Any]:
        """Get current status of a zone.

        Args:
            zone_entity_id: The entity ID of the zone switch

        Returns:
            Zone status dictionary
        """
        state = self.hass.states.get(zone_entity_id)
        if not state:
            return {"available": False}

        return {
            "entity_id": zone_entity_id,
            "name": state.attributes.get("friendly_name"),
            "running": state.state == STATE_ON,
            "available": state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN),
            "last_changed": state.last_changed.isoformat() if state.last_changed else None,
            "attributes": dict(state.attributes),
        }

    async def async_get_all_zones_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all zones.

        Returns:
            Dictionary of zone_entity_id -> status
        """
        zones = await self.async_get_zones()
        statuses = {}

        for zone in zones:
            entity_id = zone["entity_id"]
            statuses[entity_id] = await self.async_get_zone_status(entity_id)

        return statuses

    async def async_run_zone(
        self,
        zone_entity_id: str,
        duration_minutes: int,
    ) -> bool:
        """Run a specific zone.

        Args:
            zone_entity_id: The entity ID of the zone switch
            duration_minutes: Duration in minutes

        Returns:
            True if successful
        """
        try:
            # Use Rachio service if available
            if self._has_rachio_service(SERVICE_START_WATERING):
                await self.hass.services.async_call(
                    RACHIO_DOMAIN,
                    SERVICE_START_WATERING,
                    {
                        "entity_id": zone_entity_id,
                        "duration": duration_minutes,
                    },
                    blocking=True,
                )
            else:
                # Fallback to switch.turn_on
                # Note: This doesn't support duration, zone will run until turned off
                await self.hass.services.async_call(
                    "switch",
                    "turn_on",
                    {"entity_id": zone_entity_id},
                    blocking=True,
                )

            _LOGGER.info("Started zone %s for %d minutes", zone_entity_id, duration_minutes)
            return True

        except Exception as err:
            _LOGGER.error("Failed to start zone %s: %s", zone_entity_id, err)
            return False

    async def async_run_multiple_zones(
        self,
        zones: list[dict[str, Any]],
    ) -> bool:
        """Run multiple zones in sequence.

        Args:
            zones: List of dicts with 'entity_id' and 'duration_minutes'

        Returns:
            True if all zones started successfully
        """
        # Rachio handles sequencing automatically when called via service
        # We'll call each zone and let Rachio queue them
        success = True

        for zone in zones:
            entity_id = zone.get("entity_id")
            duration = zone.get("duration_minutes", 10)

            if entity_id:
                result = await self.async_run_zone(entity_id, duration)
                if not result:
                    success = False

        return success

    async def async_stop_zone(self, zone_entity_id: str) -> bool:
        """Stop a specific zone.

        Args:
            zone_entity_id: The entity ID of the zone switch

        Returns:
            True if successful
        """
        try:
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": zone_entity_id},
                blocking=True,
            )
            _LOGGER.info("Stopped zone %s", zone_entity_id)
            return True

        except Exception as err:
            _LOGGER.error("Failed to stop zone %s: %s", zone_entity_id, err)
            return False

    async def async_stop_all(self) -> bool:
        """Stop all running zones.

        Returns:
            True if successful
        """
        try:
            # Use Rachio stop service if available
            if self._has_rachio_service(SERVICE_STOP_WATERING):
                # Get all zone entity IDs
                zones = await self.async_get_zones()
                for zone in zones:
                    await self.hass.services.async_call(
                        RACHIO_DOMAIN,
                        SERVICE_STOP_WATERING,
                        {"entity_id": zone["entity_id"]},
                        blocking=True,
                    )
            else:
                # Fallback - turn off all zone switches
                zones = await self.async_get_zones()
                for zone in zones:
                    await self.hass.services.async_call(
                        "switch",
                        "turn_off",
                        {"entity_id": zone["entity_id"]},
                        blocking=True,
                    )

            _LOGGER.info("Stopped all zones")
            return True

        except Exception as err:
            _LOGGER.error("Failed to stop all zones: %s", err)
            return False

    async def async_get_rain_sensor_status(self) -> dict[str, Any]:
        """Get rain sensor status from Home Assistant entity.

        Returns:
            Rain sensor status dictionary
        """
        discovery = await self.async_discover_rachio_entities()
        rain_sensors = discovery.get("rain_sensors", [])

        if rain_sensors:
            sensor = rain_sensors[0]
            state = self.hass.states.get(sensor["entity_id"])

            if state:
                return {
                    "entity_id": sensor["entity_id"],
                    "tripped": state.state == STATE_ON,
                    "available": state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN),
                    "last_changed": state.last_changed.isoformat() if state.last_changed else None,
                }

        return {"tripped": False, "available": False}

    async def async_set_rain_delay(self, hours: int) -> bool:
        """Set a rain delay.

        Args:
            hours: Number of hours to delay

        Returns:
            True if successful
        """
        try:
            if self._has_rachio_service(SERVICE_SET_RAIN_DELAY):
                # Get device entity to call service on
                zones = await self.async_get_zones()
                if zones:
                    await self.hass.services.async_call(
                        RACHIO_DOMAIN,
                        SERVICE_SET_RAIN_DELAY,
                        {
                            "entity_id": zones[0]["entity_id"],
                            "duration": hours * 3600,  # Convert to seconds
                        },
                        blocking=True,
                    )
                    _LOGGER.info("Set rain delay for %d hours", hours)
                    return True

            _LOGGER.warning("Rachio rain delay service not available")
            return False

        except Exception as err:
            _LOGGER.error("Failed to set rain delay: %s", err)
            return False

    def _has_rachio_service(self, service_name: str) -> bool:
        """Check if a Rachio service is available.

        Args:
            service_name: Name of the service

        Returns:
            True if service is available
        """
        return self.hass.services.has_service(RACHIO_DOMAIN, service_name)

    async def async_get_running_zone(self) -> dict[str, Any] | None:
        """Get the currently running zone, if any.

        Returns:
            Zone info dict if a zone is running, None otherwise
        """
        zones = await self.async_get_zones()

        for zone in zones:
            state = self.hass.states.get(zone["entity_id"])
            if state and state.state == STATE_ON:
                return {
                    "entity_id": zone["entity_id"],
                    "name": zone["name"],
                    "zone_number": zone["zone_number"],
                    "running_since": state.last_changed.isoformat() if state.last_changed else None,
                }

        return None

    async def async_get_device_state(self) -> dict[str, Any]:
        """Get overall device state.

        Returns:
            Device state dictionary
        """
        zones_status = await self.async_get_all_zones_status()
        rain_sensor = await self.async_get_rain_sensor_status()
        running_zone = await self.async_get_running_zone()

        any_running = any(z.get("running") for z in zones_status.values())
        all_available = all(z.get("available") for z in zones_status.values())

        return {
            "available": all_available,
            "running": any_running,
            "running_zone": running_zone,
            "rain_sensor_tripped": rain_sensor.get("tripped", False),
            "total_zones": len(zones_status),
            "enabled_zones": sum(1 for z in zones_status.values() if z.get("available")),
        }
