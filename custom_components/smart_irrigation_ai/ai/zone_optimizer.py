"""Zone optimizer for Smart Irrigation AI."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, time
from typing import Any
from dataclasses import dataclass, field

from ..const import (
    ZONE_TYPES,
    SOIL_TYPES,
    SLOPE_TYPES,
    SUN_EXPOSURE,
    NOZZLE_TYPES,
    SEASONAL_FACTORS,
    DEFAULT_MAX_DAILY_RUNTIME,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ZoneConfig:
    """Configuration for a single irrigation zone."""

    zone_id: str
    name: str
    zone_type: str = "cool_season_grass"
    soil_type: str = "loam"
    slope: str = "flat"
    sun_exposure: str = "full_sun"
    nozzle_type: str = "fixed_spray"
    root_depth: float = 6.0  # inches
    area_sqft: float = 1000  # square feet
    efficiency: float = 0.80  # irrigation efficiency
    enabled: bool = True

    @property
    def crop_coefficient(self) -> float:
        """Get crop coefficient for this zone type."""
        return ZONE_TYPES.get(self.zone_type, {}).get("kc", 0.80)

    @property
    def infiltration_rate(self) -> float:
        """Get soil infiltration rate (in/hr)."""
        return SOIL_TYPES.get(self.soil_type, {}).get("infiltration_rate", 0.35)

    @property
    def water_holding_capacity(self) -> float:
        """Get soil water holding capacity."""
        return SOIL_TYPES.get(self.soil_type, {}).get("water_holding_capacity", 0.17)

    @property
    def runoff_factor(self) -> float:
        """Get slope runoff factor."""
        return SLOPE_TYPES.get(self.slope, {}).get("runoff_factor", 1.0)

    @property
    def et_factor(self) -> float:
        """Get sun exposure ET factor."""
        return SUN_EXPOSURE.get(self.sun_exposure, {}).get("et_factor", 1.0)

    @property
    def precip_rate(self) -> float:
        """Get nozzle precipitation rate (in/hr)."""
        return NOZZLE_TYPES.get(self.nozzle_type, {}).get("precip_rate", 1.5)


@dataclass
class WateringRecommendation:
    """Recommendation for watering a zone."""

    zone_id: str
    zone_name: str
    should_water: bool
    duration_minutes: int
    water_amount_inches: float
    confidence: float  # 0.0 to 1.0
    priority: int  # 1 = highest priority
    factors: dict = field(default_factory=dict)
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "should_water": self.should_water,
            "duration_minutes": self.duration_minutes,
            "water_amount_inches": round(self.water_amount_inches, 3),
            "confidence": round(self.confidence, 2),
            "priority": self.priority,
            "factors": self.factors,
            "skip_reason": self.skip_reason,
        }


class ZoneOptimizer:
    """Optimize irrigation for multiple zones."""

    def __init__(
        self,
        zones: dict[str, ZoneConfig],
        max_daily_runtime: int = DEFAULT_MAX_DAILY_RUNTIME,
        watering_window_start: time = time(5, 0),
        watering_window_end: time = time(9, 0),
    ) -> None:
        """Initialize the zone optimizer.

        Args:
            zones: Dict of zone_id -> ZoneConfig
            max_daily_runtime: Maximum total runtime in minutes
            watering_window_start: Earliest time to start watering
            watering_window_end: Latest time to finish watering
        """
        self.zones = zones
        self.max_daily_runtime = max_daily_runtime
        self.watering_window_start = watering_window_start
        self.watering_window_end = watering_window_end

    def calculate_base_duration(
        self,
        zone: ZoneConfig,
        water_needed_inches: float,
    ) -> int:
        """Calculate base watering duration for a zone.

        Args:
            zone: Zone configuration
            water_needed_inches: Amount of water needed in inches

        Returns:
            Duration in minutes
        """
        if water_needed_inches <= 0:
            return 0

        # Account for irrigation efficiency
        actual_water_needed = water_needed_inches / zone.efficiency

        # Calculate time based on precipitation rate
        duration_hours = actual_water_needed / zone.precip_rate
        duration_minutes = int(duration_hours * 60)

        return max(1, duration_minutes)

    def calculate_cycle_soak(
        self,
        zone: ZoneConfig,
        total_duration: int,
    ) -> list[dict[str, int]]:
        """Calculate cycle and soak schedule for a zone.

        Cycle/soak helps prevent runoff on slopes or with high precip rates.

        Args:
            zone: Zone configuration
            total_duration: Total watering time needed in minutes

        Returns:
            List of {cycle: minutes, soak: minutes} dicts
        """
        if total_duration <= 0:
            return []

        # Calculate max runtime before runoff
        # Based on infiltration rate vs precipitation rate
        if zone.precip_rate > zone.infiltration_rate:
            # Risk of runoff - need cycle/soak
            max_cycle_hours = zone.infiltration_rate / zone.precip_rate * 0.8  # 80% safety margin
            max_cycle_minutes = int(max_cycle_hours * 60)

            # Adjust for slope
            max_cycle_minutes = int(max_cycle_minutes * zone.runoff_factor)

            # Minimum reasonable cycle
            max_cycle_minutes = max(3, min(max_cycle_minutes, 15))

            # Calculate soak time (at least equal to cycle time for infiltration)
            soak_time = max(max_cycle_minutes, 10)

            cycles = []
            remaining = total_duration

            while remaining > 0:
                cycle_duration = min(remaining, max_cycle_minutes)
                cycles.append({
                    "cycle": cycle_duration,
                    "soak": soak_time if remaining > cycle_duration else 0,
                })
                remaining -= cycle_duration

            return cycles

        else:
            # No runoff risk - single cycle
            return [{"cycle": total_duration, "soak": 0}]

    def optimize_schedule(
        self,
        recommendations: list[WateringRecommendation],
        available_window_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """Optimize watering schedule for multiple zones.

        Prioritizes zones, handles cycle/soak, and fits within time window.

        Args:
            recommendations: List of zone recommendations
            available_window_minutes: Override for available time window

        Returns:
            Optimized schedule as list of dicts
        """
        # Calculate available window
        if available_window_minutes is None:
            start_dt = datetime.combine(datetime.today(), self.watering_window_start)
            end_dt = datetime.combine(datetime.today(), self.watering_window_end)
            available_window_minutes = int((end_dt - start_dt).total_seconds() / 60)

        # Apply max daily runtime limit
        available_time = min(available_window_minutes, self.max_daily_runtime)

        # Filter to zones that should water and sort by priority
        to_water = [r for r in recommendations if r.should_water and r.duration_minutes > 0]
        to_water.sort(key=lambda x: (x.priority, -x.confidence))

        schedule = []
        total_time = 0

        for rec in to_water:
            zone = self.zones.get(rec.zone_id)
            if not zone or not zone.enabled:
                continue

            # Check if we have time
            if total_time + rec.duration_minutes > available_time:
                # Try to fit partial watering
                remaining_time = available_time - total_time
                if remaining_time >= 5:  # Minimum 5 minutes
                    adjusted_duration = remaining_time
                else:
                    continue  # Skip this zone
            else:
                adjusted_duration = rec.duration_minutes

            # Calculate cycle/soak if needed
            cycles = self.calculate_cycle_soak(zone, adjusted_duration)

            # Add to schedule
            schedule_entry = {
                "zone_id": rec.zone_id,
                "zone_name": rec.zone_name,
                "duration_minutes": adjusted_duration,
                "water_amount_inches": rec.water_amount_inches * (adjusted_duration / rec.duration_minutes) if rec.duration_minutes > 0 else 0,
                "priority": rec.priority,
                "confidence": rec.confidence,
                "cycles": cycles,
                "factors": rec.factors,
            }

            schedule.append(schedule_entry)
            total_time += adjusted_duration

            # Account for soak times in total
            soak_time = sum(c.get("soak", 0) for c in cycles)
            # Note: soak time doesn't count against runtime but does affect schedule length

        return schedule

    def get_seasonal_factor(self, month: int | None = None) -> float:
        """Get seasonal adjustment factor.

        Args:
            month: Month number (1-12), defaults to current month

        Returns:
            Seasonal factor (0.35 - 1.05)
        """
        if month is None:
            month = datetime.now().month

        return SEASONAL_FACTORS.get(month, 1.0)

    def calculate_water_need(
        self,
        zone: ZoneConfig,
        et_inches: float,
        precipitation_inches: float = 0,
        moisture_deficit_pct: float = 50,
        days_since_watering: int = 1,
    ) -> float:
        """Calculate water need for a zone.

        Args:
            zone: Zone configuration
            et_inches: Evapotranspiration in inches
            precipitation_inches: Recent precipitation in inches
            moisture_deficit_pct: Current moisture deficit (0-100%)
            days_since_watering: Days since last watering

        Returns:
            Water needed in inches
        """
        # Base water need from ET
        etc = et_inches * zone.crop_coefficient * zone.et_factor

        # Subtract effective precipitation (with efficiency factor)
        effective_precip = precipitation_inches * 0.75  # 75% efficiency

        # Calculate net water need
        net_need = etc - effective_precip

        # Adjust based on moisture deficit
        if moisture_deficit_pct < 30:
            # Soil is fairly moist, reduce watering
            net_need *= 0.5
        elif moisture_deficit_pct > 70:
            # Soil is dry, increase watering
            net_need *= 1.3

        # Apply soil characteristics
        # Deep watering for deep roots, less frequent
        root_factor = zone.root_depth / 6.0  # Normalize to 6" standard

        # Target: refill root zone to field capacity
        max_application = zone.root_depth * zone.water_holding_capacity * 0.5

        net_need = min(net_need * root_factor, max_application)

        return max(0, net_need)

    def prioritize_zones(
        self,
        zone_analyses: dict[str, dict[str, Any]],
    ) -> dict[str, int]:
        """Assign priority to zones based on their needs.

        Args:
            zone_analyses: Dict of zone_id -> analysis data

        Returns:
            Dict of zone_id -> priority (1 = highest)
        """
        # Score each zone
        scores = {}

        for zone_id, analysis in zone_analyses.items():
            zone = self.zones.get(zone_id)
            if not zone:
                continue

            score = 0

            # Urgency from soil moisture
            urgency = analysis.get("urgency", 0.5)
            score += urgency * 40

            # Water deficit
            deficit = analysis.get("water_deficit_pct", 50)
            score += deficit * 0.3

            # Zone type priority (new plantings, vegetables higher)
            type_priority = {
                "new_seed": 15,
                "new_sod": 12,
                "vegetables": 10,
                "annuals": 8,
                "cool_season_grass": 5,
                "warm_season_grass": 5,
                "perennials": 4,
                "shrubs": 3,
                "native_plants": 2,
                "trees": 2,
            }
            score += type_priority.get(zone.zone_type, 5)

            # Moisture trend
            trend = analysis.get("trend", "stable")
            if trend == "falling_fast":
                score += 10
            elif trend == "falling":
                score += 5

            scores[zone_id] = score

        # Convert scores to priorities (1 = highest)
        sorted_zones = sorted(scores.keys(), key=lambda z: scores[z], reverse=True)
        priorities = {z: i + 1 for i, z in enumerate(sorted_zones)}

        return priorities

    def get_zone_summary(self, zone_id: str) -> dict[str, Any]:
        """Get a summary of zone configuration and characteristics."""
        zone = self.zones.get(zone_id)
        if not zone:
            return {}

        return {
            "zone_id": zone_id,
            "name": zone.name,
            "type": ZONE_TYPES.get(zone.zone_type, {}).get("name", zone.zone_type),
            "soil": SOIL_TYPES.get(zone.soil_type, {}).get("name", zone.soil_type),
            "slope": SLOPE_TYPES.get(zone.slope, {}).get("name", zone.slope),
            "sun": SUN_EXPOSURE.get(zone.sun_exposure, {}).get("name", zone.sun_exposure),
            "nozzle": NOZZLE_TYPES.get(zone.nozzle_type, {}).get("name", zone.nozzle_type),
            "crop_coefficient": zone.crop_coefficient,
            "infiltration_rate": zone.infiltration_rate,
            "precip_rate": zone.precip_rate,
            "root_depth": zone.root_depth,
            "efficiency": zone.efficiency,
            "enabled": zone.enabled,
            "needs_cycle_soak": zone.precip_rate > zone.infiltration_rate,
        }
