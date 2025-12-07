"""Switch entities for Smart Irrigation AI."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Irrigation AI switches."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    rachio_api = data["rachio_api"]
    scheduler = data["scheduler"]
    zones_info = data.get("zones_info", [])

    entities = []

    # Main controller switches
    entities.extend([
        SchedulerEnabledSwitch(coordinator, entry, scheduler),
        RainDelaySwitch(coordinator, entry, scheduler),
    ])

    # Zone switches
    for zone in zones_info:
        zone_id = zone.get("zone_id") or zone.get("entity_id")
        zone_name = zone.get("name", f"Zone {zone.get('zone_number', '?')}")
        zone_number = zone.get("zone_number", 0)

        # Skip zones without valid ID
        if not zone_id:
            _LOGGER.warning("Skipping zone switch creation - no valid zone ID: %s", zone)
            continue

        entities.append(
            ZoneSwitch(coordinator, entry, rachio_api, scheduler, zone_id, zone_name, zone_number)
        )

    async_add_entities(entities)


class SmartIrrigationSwitchBase(CoordinatorEntity, SwitchEntity):
    """Base class for Smart Irrigation switches."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        switch_type: str,
        name: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._switch_type = switch_type
        self._attr_name = f"Smart Irrigation {name}"
        self._attr_unique_id = f"{entry.entry_id}_{switch_type}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Smart Irrigation AI Controller",
            manufacturer="Smart Irrigation AI",
            model="AI Irrigation Controller",
            sw_version="1.0.0",
        )


class SchedulerEnabledSwitch(SmartIrrigationSwitchBase):
    """Switch to enable/disable the scheduler."""

    def __init__(self, coordinator, entry: ConfigEntry, scheduler) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry, "scheduler_enabled", "Scheduler")
        self._scheduler = scheduler
        self._attr_icon = "mdi:calendar-check"
        self._is_on = True

    @property
    def is_on(self) -> bool:
        """Return if scheduler is enabled."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the scheduler."""
        self._is_on = True
        await self._scheduler.async_start()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the scheduler."""
        self._is_on = False
        # Don't stop completely, just pause scheduling
        self._scheduler._skip_next = True
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        schedule = self.coordinator.data.get("schedule", {})
        return {
            "next_run": schedule.get("next_run"),
            "watering_days": schedule.get("watering_days"),
            "start_time": schedule.get("start_time"),
        }


class RainDelaySwitch(SmartIrrigationSwitchBase):
    """Switch for rain delay."""

    def __init__(self, coordinator, entry: ConfigEntry, scheduler) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry, "rain_delay", "Rain Delay")
        self._scheduler = scheduler
        self._attr_icon = "mdi:weather-rainy"

    @property
    def is_on(self) -> bool:
        """Return if rain delay is active."""
        if self.coordinator.data is None:
            return False

        schedule = self.coordinator.data.get("schedule", {})
        return schedule.get("rain_delay_until") is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable 24-hour rain delay."""
        await self._scheduler.async_set_rain_delay(24)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Cancel rain delay."""
        await self._scheduler.async_cancel_rain_delay()
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        schedule = self.coordinator.data.get("schedule", {})
        rain_sensor = self.coordinator.data.get("rain_sensor", {})

        return {
            "rain_delay_until": schedule.get("rain_delay_until"),
            "rain_sensor_tripped": rain_sensor.get("tripped"),
            "rain_intensity": rain_sensor.get("intensity"),
        }


class ZoneSwitch(SmartIrrigationSwitchBase):
    """Switch for individual zone control."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        rachio_api,
        scheduler,
        zone_id: str,
        zone_name: str,
        zone_number: int,
    ) -> None:
        """Initialize the switch."""
        super().__init__(
            coordinator,
            entry,
            f"zone_{zone_id}",
            f"{zone_name}",
        )
        self._rachio_api = rachio_api
        self._scheduler = scheduler
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._zone_number = zone_number
        self._attr_icon = "mdi:sprinkler"

    @property
    def is_on(self) -> bool:
        """Return if zone is currently running."""
        if self.coordinator.data is None:
            return False

        zones = self.coordinator.data.get("zones", {})
        zone_status = zones.get(self._zone_id, {})

        return zone_status.get("running", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the zone."""
        # Get AI-recommended duration or default to 10 minutes
        ai_model = self.hass.data[DOMAIN][self._entry.entry_id]["ai_model"]
        duration = await ai_model.async_get_recommended_duration(self._zone_id)
        if duration <= 0:
            duration = 10  # Default 10 minutes

        await self._rachio_api.async_run_zone(self._zone_id, duration * 60)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the zone."""
        await self._rachio_api.async_stop_zone(self._zone_id)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        attrs = {
            "zone_id": self._zone_id,
            "zone_number": self._zone_number,
        }

        if self.coordinator.data is None:
            return attrs

        zones = self.coordinator.data.get("zones", {})
        zone_status = zones.get(self._zone_id, {})

        attrs.update({
            "enabled": zone_status.get("enabled", True),
            "remaining_runtime": zone_status.get("remaining_runtime", 0),
            "last_watered": zone_status.get("last_watered_date"),
            "last_duration": zone_status.get("last_watered_duration"),
        })

        # Add recommendation info
        recommendations = self.coordinator.data.get("recommendations", {})
        rec = recommendations.get(self._zone_id)
        if rec and hasattr(rec, 'should_water'):
            attrs.update({
                "ai_should_water": rec.should_water,
                "ai_duration": rec.duration_minutes,
                "ai_confidence": rec.confidence,
                "ai_skip_reason": rec.skip_reason,
            })

        return attrs
