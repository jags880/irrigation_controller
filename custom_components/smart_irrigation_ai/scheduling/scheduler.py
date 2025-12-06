"""Smart Scheduler for irrigation timing and execution."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, time, date
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval, async_track_point_in_time
from homeassistant.util import dt as dt_util

from ..const import (
    DEFAULT_WATERING_DAYS,
    DEFAULT_START_TIME,
    DEFAULT_END_TIME,
    SCHEDULE_RECALC_HOURS,
)

_LOGGER = logging.getLogger(__name__)


class SmartScheduler:
    """Intelligent scheduler for irrigation operations."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        rachio_api,
        ai_model,
        use_ha_rachio: bool = True,
    ) -> None:
        """Initialize the scheduler.

        Args:
            hass: Home Assistant instance
            config: Integration configuration
            rachio_api: Rachio API client or HA controller
            ai_model: AI irrigation model
            use_ha_rachio: Whether using HA Rachio integration
        """
        self.hass = hass
        self.config = config
        self.rachio_api = rachio_api
        self.ai_model = ai_model
        self.use_ha_rachio = use_ha_rachio

        # Parse configuration
        self._watering_days = config.get("watering_days", DEFAULT_WATERING_DAYS)
        self._start_time = self._parse_time(config.get("watering_start_time", DEFAULT_START_TIME))
        self._end_time = self._parse_time(config.get("watering_end_time", DEFAULT_END_TIME))
        self._max_runtime = config.get("max_daily_runtime", 180)
        self._cycle_soak_enabled = config.get("cycle_soak_enabled", True)

        # State
        self._schedule: dict[str, Any] = {}
        self._next_run: datetime | None = None
        self._last_run: datetime | None = None
        self._is_running = False
        self._current_zone: str | None = None
        self._skip_next = False
        self._rain_delay_until: datetime | None = None
        self._unsub_timer: Callable | None = None
        self._unsub_recalc: Callable | None = None

        # History
        self._run_history: list[dict[str, Any]] = []

    def _parse_time(self, time_str: str) -> time:
        """Parse time string."""
        try:
            parts = time_str.split(":")
            return time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return time(5, 0)

    async def async_start(self) -> None:
        """Start the scheduler."""
        _LOGGER.info("Starting Smart Irrigation scheduler")

        # Calculate initial schedule
        await self.async_calculate_schedule()

        # Schedule next run
        await self._schedule_next_run()

        # Set up periodic recalculation
        self._unsub_recalc = async_track_time_interval(
            self.hass,
            self._async_recalculate_callback,
            timedelta(hours=SCHEDULE_RECALC_HOURS),
        )

    async def async_stop(self) -> None:
        """Stop the scheduler."""
        _LOGGER.info("Stopping Smart Irrigation scheduler")

        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

        if self._unsub_recalc:
            self._unsub_recalc()
            self._unsub_recalc = None

        # Stop any running zones
        if self._is_running:
            await self.rachio_api.async_stop_all()
            self._is_running = False

    @callback
    def _async_recalculate_callback(self, now: datetime) -> None:
        """Callback for periodic recalculation."""
        self.hass.async_create_task(self.async_calculate_schedule())

    async def async_calculate_schedule(self) -> dict[str, Any]:
        """Calculate the watering schedule.

        Returns:
            Schedule dictionary
        """
        _LOGGER.debug("Calculating irrigation schedule")

        try:
            # Get optimized schedule from AI model
            zone_schedule = await self.ai_model.async_get_optimized_schedule()

            # Build schedule
            self._schedule = {
                "calculated_at": datetime.now().isoformat(),
                "zones": zone_schedule,
                "total_runtime": sum(z.get("duration_minutes", 0) for z in zone_schedule),
                "zones_to_water": len([z for z in zone_schedule if z.get("duration_minutes", 0) > 0]),
            }

            # Calculate next run time
            self._next_run = self._calculate_next_run_time()
            self._schedule["next_run"] = self._next_run.isoformat() if self._next_run else None

            _LOGGER.info(
                "Schedule calculated: %d zones, %d minutes total, next run: %s",
                self._schedule["zones_to_water"],
                self._schedule["total_runtime"],
                self._next_run,
            )

            return self._schedule

        except Exception as err:
            _LOGGER.error("Error calculating schedule: %s", err)
            return {}

    def _calculate_next_run_time(self) -> datetime | None:
        """Calculate the next scheduled run time."""
        now = dt_util.now()

        # Check rain delay
        if self._rain_delay_until and now < self._rain_delay_until:
            return self._rain_delay_until

        # Find next valid watering day
        for days_ahead in range(8):  # Check up to a week ahead
            check_date = now.date() + timedelta(days=days_ahead)
            weekday = check_date.weekday()

            if weekday in self._watering_days:
                # Check if we can still run today
                run_datetime = datetime.combine(check_date, self._start_time)
                run_datetime = dt_util.as_local(run_datetime.replace(tzinfo=now.tzinfo))

                if run_datetime > now:
                    return run_datetime

        return None

    async def _schedule_next_run(self) -> None:
        """Schedule the next watering run."""
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

        if self._next_run is None:
            self._next_run = self._calculate_next_run_time()

        if self._next_run:
            self._unsub_timer = async_track_point_in_time(
                self.hass,
                self._async_run_callback,
                self._next_run,
            )
            _LOGGER.debug("Next run scheduled for %s", self._next_run)

    @callback
    def _async_run_callback(self, now: datetime) -> None:
        """Callback for scheduled run."""
        self.hass.async_create_task(self.async_execute_schedule())

    async def async_execute_schedule(self) -> bool:
        """Execute the current schedule.

        Returns:
            True if execution started successfully
        """
        _LOGGER.info("Executing irrigation schedule")

        # Check skip conditions
        if self._skip_next:
            _LOGGER.info("Skipping scheduled run (manual skip)")
            self._skip_next = False
            await self._schedule_next_run()
            return False

        if self._rain_delay_until and datetime.now() < self._rain_delay_until:
            _LOGGER.info("Skipping scheduled run (rain delay)")
            await self._schedule_next_run()
            return False

        # Recalculate schedule with fresh data
        await self.async_calculate_schedule()

        zones = self._schedule.get("zones", [])
        if not zones:
            _LOGGER.info("No zones to water")
            await self._schedule_next_run()
            return False

        self._is_running = True
        self._last_run = datetime.now()

        try:
            # Build zone list for Rachio
            zones_to_run = []
            for zone_info in zones:
                if zone_info.get("duration_minutes", 0) > 0:
                    # Handle cycle/soak if enabled
                    if self._cycle_soak_enabled and zone_info.get("cycles"):
                        # Run each cycle
                        for cycle in zone_info["cycles"]:
                            zones_to_run.append({
                                "id": zone_info["zone_id"],
                                "duration": cycle["cycle"] * 60,  # Convert to seconds
                            })
                            # Note: Soak time handled by Rachio or we'd need to
                            # implement our own sequencing
                    else:
                        zones_to_run.append({
                            "id": zone_info["zone_id"],
                            "duration": zone_info["duration_minutes"] * 60,
                        })

            if zones_to_run:
                success = await self.rachio_api.async_run_multiple_zones(zones_to_run)

                # Record history
                self._run_history.append({
                    "timestamp": self._last_run.isoformat(),
                    "zones": len(zones_to_run),
                    "total_duration": sum(z["duration"] for z in zones_to_run) // 60,
                    "success": success,
                    "schedule": self._schedule.copy(),
                })

                # Keep only last 30 runs
                if len(self._run_history) > 30:
                    self._run_history = self._run_history[-30:]

                return success

        except Exception as err:
            _LOGGER.error("Error executing schedule: %s", err)
            return False

        finally:
            self._is_running = False
            # Schedule next run
            self._next_run = None
            await self._schedule_next_run()

        return False

    async def async_run_zone_now(
        self, zone_id: str, duration_minutes: int | None = None
    ) -> bool:
        """Run a specific zone immediately.

        Args:
            zone_id: Zone to run
            duration_minutes: Duration (or use AI recommendation)

        Returns:
            True if started successfully
        """
        if duration_minutes is None:
            duration_minutes = await self.ai_model.async_get_recommended_duration(zone_id)
            if duration_minutes <= 0:
                duration_minutes = 10  # Default fallback

        _LOGGER.info("Running zone %s for %d minutes", zone_id, duration_minutes)

        return await self.rachio_api.async_run_zone(zone_id, duration_minutes * 60)

    async def async_stop_all_zones(self) -> bool:
        """Stop all running zones."""
        _LOGGER.info("Stopping all zones")
        self._is_running = False
        self._current_zone = None
        return await self.rachio_api.async_stop_all()

    async def async_skip_next(self, zone_id: str | None = None) -> None:
        """Skip the next scheduled watering.

        Args:
            zone_id: Specific zone to skip, or None for all
        """
        if zone_id:
            # Mark specific zone as skipped
            for zone in self._schedule.get("zones", []):
                if zone.get("zone_id") == zone_id:
                    zone["skipped"] = True
                    _LOGGER.info("Skipping zone %s for next run", zone_id)
        else:
            # Skip entire next run
            self._skip_next = True
            _LOGGER.info("Skipping next scheduled run")

    async def async_set_rain_delay(self, hours: int) -> None:
        """Set a rain delay.

        Args:
            hours: Number of hours to delay
        """
        self._rain_delay_until = datetime.now() + timedelta(hours=hours)
        _LOGGER.info("Rain delay set until %s", self._rain_delay_until)

        # Also set on Rachio device
        await self.rachio_api.async_set_rain_delay(hours * 3600)

        # Reschedule next run
        self._next_run = None
        await self._schedule_next_run()

    async def async_cancel_rain_delay(self) -> None:
        """Cancel any active rain delay."""
        self._rain_delay_until = None
        await self.rachio_api.async_cancel_rain_delay()
        _LOGGER.info("Rain delay cancelled")

        # Reschedule
        self._next_run = None
        await self._schedule_next_run()

    async def async_get_schedule(self) -> dict[str, Any]:
        """Get current schedule information."""
        return {
            "schedule": self._schedule,
            "next_run": self._next_run.isoformat() if self._next_run else None,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "is_running": self._is_running,
            "current_zone": self._current_zone,
            "skip_next": self._skip_next,
            "rain_delay_until": self._rain_delay_until.isoformat() if self._rain_delay_until else None,
            "watering_days": self._watering_days,
            "start_time": self._start_time.isoformat(),
            "end_time": self._end_time.isoformat(),
        }

    def get_run_history(self) -> list[dict[str, Any]]:
        """Get watering run history."""
        return self._run_history.copy()

    @property
    def is_running(self) -> bool:
        """Check if scheduler is currently running zones."""
        return self._is_running

    @property
    def next_run(self) -> datetime | None:
        """Get next scheduled run time."""
        return self._next_run

    @property
    def last_run(self) -> datetime | None:
        """Get last run time."""
        return self._last_run
