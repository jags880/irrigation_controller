"""Calendar entity for Smart Irrigation AI."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .scheduling.calendar_manager import IrrigationCalendar

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Irrigation AI calendar."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    scheduler = data["scheduler"]

    # Create calendar manager
    calendar_manager = IrrigationCalendar(hass, scheduler)

    entities = [
        IrrigationScheduleCalendar(coordinator, entry, calendar_manager),
    ]

    async_add_entities(entities)


class IrrigationScheduleCalendar(CoordinatorEntity, CalendarEntity):
    """Calendar entity showing irrigation schedule."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        calendar_manager: IrrigationCalendar,
    ) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator)
        self._entry = entry
        self._calendar_manager = calendar_manager
        self._attr_name = "Smart Irrigation Schedule"
        self._attr_unique_id = f"{entry.entry_id}_calendar"

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

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        if self.coordinator.data is None:
            return None

        schedule = self.coordinator.data.get("schedule", {})
        next_run = schedule.get("next_run")

        if not next_run:
            return None

        try:
            next_run_dt = datetime.fromisoformat(next_run)
        except (ValueError, TypeError):
            return None

        sched_data = schedule.get("schedule", {})
        zones = sched_data.get("zones", [])
        total_duration = sched_data.get("total_runtime", 0)
        zone_count = sched_data.get("zones_to_water", 0)

        return CalendarEvent(
            start=next_run_dt,
            end=next_run_dt + timedelta(minutes=total_duration),
            summary=f"Irrigation: {zone_count} zones, {total_duration} min",
            description=self._build_event_description(zones),
        )

    def _build_event_description(self, zones: list[dict[str, Any]]) -> str:
        """Build event description from zone schedule."""
        lines = ["**Scheduled Watering**\n"]

        for zone in zones:
            if zone.get("duration_minutes", 0) > 0:
                lines.append(
                    f"- {zone.get('zone_name', 'Zone')}: "
                    f"{zone.get('duration_minutes')} min "
                    f"({zone.get('water_amount_inches', 0):.2f}\")"
                )

        # Add weather info
        if self.coordinator.data:
            weather = self.coordinator.data.get("weather", {})
            if weather:
                lines.append("\n**Weather**")
                lines.append(f"- Condition: {weather.get('condition', 'Unknown')}")
                lines.append(f"- Temperature: {weather.get('temperature', 'N/A')}°F")

        return "\n".join(lines)

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return await self._calendar_manager.async_get_events(start_date, end_date)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        forecast = self._calendar_manager.get_watering_forecast(7)

        return {
            "forecast": forecast,
            "next_watering_days": [
                f["date"] for f in forecast if f["is_watering_day"]
            ][:3],
        }
