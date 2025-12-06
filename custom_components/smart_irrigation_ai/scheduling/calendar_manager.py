"""Calendar integration for Smart Irrigation AI."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, date
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.components.calendar import CalendarEntity, CalendarEvent

_LOGGER = logging.getLogger(__name__)


class IrrigationCalendar:
    """Manage irrigation calendar events."""

    def __init__(self, hass: HomeAssistant, scheduler) -> None:
        """Initialize the calendar manager.

        Args:
            hass: Home Assistant instance
            scheduler: SmartScheduler instance
        """
        self.hass = hass
        self.scheduler = scheduler
        self._events: list[CalendarEvent] = []

    async def async_get_events(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Get calendar events for a date range.

        Args:
            start_date: Start of range
            end_date: End of range

        Returns:
            List of calendar events
        """
        events = []

        # Get current schedule
        schedule = await self.scheduler.async_get_schedule()
        zones = schedule.get("schedule", {}).get("zones", [])

        # Add next scheduled run
        next_run = schedule.get("next_run")
        if next_run:
            try:
                next_run_dt = datetime.fromisoformat(next_run)
                if start_date <= next_run_dt <= end_date:
                    # Calculate end time based on total duration
                    total_duration = sum(z.get("duration_minutes", 0) for z in zones)
                    end_time = next_run_dt + timedelta(minutes=total_duration)

                    # Build summary
                    zone_count = len([z for z in zones if z.get("duration_minutes", 0) > 0])
                    summary = f"Smart Irrigation: {zone_count} zones, {total_duration} min"

                    # Build description
                    description_parts = ["**Scheduled Watering**\n"]
                    for zone in zones:
                        if zone.get("duration_minutes", 0) > 0:
                            description_parts.append(
                                f"- {zone.get('zone_name', 'Zone')}: {zone.get('duration_minutes')} min "
                                f"({zone.get('water_amount_inches', 0):.2f}\")"
                            )

                    events.append(CalendarEvent(
                        start=next_run_dt,
                        end=end_time,
                        summary=summary,
                        description="\n".join(description_parts),
                    ))
            except (ValueError, TypeError):
                pass

        # Add historical runs
        history = self.scheduler.get_run_history()
        for run in history:
            try:
                run_time = datetime.fromisoformat(run["timestamp"])
                if start_date <= run_time <= end_date:
                    duration = run.get("total_duration", 0)
                    end_time = run_time + timedelta(minutes=duration)

                    events.append(CalendarEvent(
                        start=run_time,
                        end=end_time,
                        summary=f"Irrigation Complete: {run.get('zones', 0)} zones",
                        description=f"Watered {run.get('zones', 0)} zones for {duration} minutes",
                    ))
            except (ValueError, TypeError):
                pass

        # Add rain delay if active
        rain_delay = schedule.get("rain_delay_until")
        if rain_delay:
            try:
                delay_until = datetime.fromisoformat(rain_delay)
                if start_date <= delay_until <= end_date:
                    events.append(CalendarEvent(
                        start=datetime.now(),
                        end=delay_until,
                        summary="Rain Delay Active",
                        description="Irrigation paused due to rain delay",
                    ))
            except (ValueError, TypeError):
                pass

        return events

    async def async_get_upcoming_events(self, days: int = 7) -> list[dict[str, Any]]:
        """Get upcoming irrigation events.

        Args:
            days: Number of days to look ahead

        Returns:
            List of event dicts
        """
        now = datetime.now()
        end = now + timedelta(days=days)

        events = await self.async_get_events(now, end)

        return [
            {
                "start": event.start.isoformat(),
                "end": event.end.isoformat(),
                "summary": event.summary,
                "description": event.description,
            }
            for event in events
        ]

    def get_watering_forecast(self, days: int = 7) -> list[dict[str, Any]]:
        """Get watering forecast based on schedule and weather.

        Args:
            days: Number of days to forecast

        Returns:
            List of forecast dicts per day
        """
        forecast = []
        schedule = self.scheduler._schedule

        watering_days = self.scheduler._watering_days or [0, 2, 4, 6]
        start_time = self.scheduler._start_time

        for i in range(days):
            check_date = date.today() + timedelta(days=i)
            weekday = check_date.weekday()

            is_watering_day = weekday in watering_days
            zones = schedule.get("zones", []) if is_watering_day and i < 2 else []

            forecast.append({
                "date": check_date.isoformat(),
                "day_name": check_date.strftime("%A"),
                "is_watering_day": is_watering_day,
                "scheduled_time": start_time.isoformat() if is_watering_day else None,
                "zones_count": len([z for z in zones if z.get("duration_minutes", 0) > 0]),
                "total_duration": sum(z.get("duration_minutes", 0) for z in zones),
                "total_water_inches": sum(z.get("water_amount_inches", 0) for z in zones),
            })

        return forecast
