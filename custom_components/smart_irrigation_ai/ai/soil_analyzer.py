"""Soil moisture analyzer for Smart Irrigation AI."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from collections import deque

from ..const import (
    MOISTURE_THRESHOLD_DRY,
    MOISTURE_THRESHOLD_WET,
    MOISTURE_THRESHOLD_OPTIMAL,
    SOIL_TYPES,
)

_LOGGER = logging.getLogger(__name__)


class SoilAnalyzer:
    """Analyze soil moisture data for irrigation decisions."""

    def __init__(self) -> None:
        """Initialize the soil analyzer."""
        self._zone_moisture: dict[str, float | None] = {}
        self._zone_history: dict[str, deque] = {}
        self._zone_soil_types: dict[str, str] = {}
        self._last_update: datetime | None = None
        self._calibration: dict[str, dict[str, float]] = {}

    def configure_zone(
        self,
        zone_id: str,
        soil_type: str = "loam",
        dry_threshold: float | None = None,
        wet_threshold: float | None = None,
        field_capacity: float | None = None,
        wilting_point: float | None = None,
    ) -> None:
        """Configure a zone for soil analysis.

        Args:
            zone_id: Zone identifier
            soil_type: Soil type (from SOIL_TYPES)
            dry_threshold: Custom dry threshold (% moisture)
            wet_threshold: Custom wet threshold (% moisture)
            field_capacity: Custom field capacity (% moisture at saturation)
            wilting_point: Custom wilting point (% moisture when plants wilt)
        """
        self._zone_soil_types[zone_id] = soil_type

        # Get soil type defaults
        soil_info = SOIL_TYPES.get(soil_type, SOIL_TYPES["loam"])

        # Calculate default thresholds based on soil type
        # Field capacity and wilting point vary by soil type
        fc = field_capacity or self._estimate_field_capacity(soil_type)
        wp = wilting_point or self._estimate_wilting_point(soil_type)

        # Calculate management allowed depletion (MAD) thresholds
        # Typically water when 50% of available water is depleted
        available_water = fc - wp
        mad_threshold = fc - (available_water * 0.5)

        self._calibration[zone_id] = {
            "dry_threshold": dry_threshold or mad_threshold,
            "wet_threshold": wet_threshold or fc,
            "field_capacity": fc,
            "wilting_point": wp,
            "available_water": available_water,
        }

        if zone_id not in self._zone_history:
            self._zone_history[zone_id] = deque(maxlen=288)  # 24h at 5min intervals

    def _estimate_field_capacity(self, soil_type: str) -> float:
        """Estimate field capacity based on soil type."""
        # Field capacity (% volumetric moisture)
        fc_map = {
            "sand": 15,
            "loamy_sand": 20,
            "sandy_loam": 28,
            "loam": 35,
            "clay_loam": 40,
            "clay": 45,
        }
        return fc_map.get(soil_type, 35)

    def _estimate_wilting_point(self, soil_type: str) -> float:
        """Estimate wilting point based on soil type."""
        # Permanent wilting point (% volumetric moisture)
        wp_map = {
            "sand": 5,
            "loamy_sand": 7,
            "sandy_loam": 10,
            "loam": 15,
            "clay_loam": 20,
            "clay": 25,
        }
        return wp_map.get(soil_type, 15)

    def update_moisture(
        self,
        zone_id: str,
        moisture_value: float | None,
        timestamp: datetime | None = None,
    ) -> None:
        """Update moisture reading for a zone.

        Args:
            zone_id: Zone identifier
            moisture_value: Moisture percentage (0-100) or None if unavailable
            timestamp: Reading timestamp (defaults to now)
        """
        if moisture_value is not None:
            self._zone_moisture[zone_id] = moisture_value

            # Add to history
            if zone_id not in self._zone_history:
                self._zone_history[zone_id] = deque(maxlen=288)

            self._zone_history[zone_id].append({
                "value": moisture_value,
                "timestamp": timestamp or datetime.now(timezone.utc),
            })

        self._last_update = datetime.now(timezone.utc)

    def update_all_moisture(self, moisture_data: dict[str, dict[str, Any]]) -> None:
        """Update moisture for all zones from coordinator data.

        Args:
            moisture_data: Dict of zone_id -> {value, unit, last_updated}
        """
        for zone_id, data in moisture_data.items():
            value = data.get("value")
            if value is not None:
                timestamp = None
                if data.get("last_updated"):
                    try:
                        timestamp = datetime.fromisoformat(data["last_updated"])
                    except ValueError:
                        pass
                self.update_moisture(zone_id, value, timestamp)

    def get_moisture(self, zone_id: str) -> float | None:
        """Get current moisture level for a zone."""
        return self._zone_moisture.get(zone_id)

    def get_moisture_status(self, zone_id: str) -> str:
        """Get moisture status category for a zone.

        Returns:
            One of: 'dry', 'low', 'optimal', 'wet', 'saturated', 'unknown'
        """
        moisture = self._zone_moisture.get(zone_id)
        if moisture is None:
            return "unknown"

        calibration = self._calibration.get(zone_id, {})
        dry = calibration.get("dry_threshold", MOISTURE_THRESHOLD_DRY)
        wet = calibration.get("wet_threshold", MOISTURE_THRESHOLD_WET)
        fc = calibration.get("field_capacity", 40)
        wp = calibration.get("wilting_point", 15)

        if moisture >= fc:
            return "saturated"
        elif moisture >= wet:
            return "wet"
        elif moisture >= dry:
            return "optimal"
        elif moisture >= wp:
            return "low"
        else:
            return "dry"

    def needs_water(self, zone_id: str) -> tuple[bool, float]:
        """Determine if a zone needs water.

        Returns:
            Tuple of (needs_water, urgency_factor)
            urgency_factor: 0.0 = no water needed, 1.0+ = urgent
        """
        moisture = self._zone_moisture.get(zone_id)

        # If no sensor, can't determine - assume may need water
        if moisture is None:
            return True, 0.5  # Moderate urgency

        calibration = self._calibration.get(zone_id, {})
        dry = calibration.get("dry_threshold", MOISTURE_THRESHOLD_DRY)
        wet = calibration.get("wet_threshold", MOISTURE_THRESHOLD_WET)
        wp = calibration.get("wilting_point", 15)

        if moisture >= wet:
            return False, 0.0  # Already wet enough

        if moisture <= wp:
            return True, 1.5  # Critical - at wilting point

        if moisture < dry:
            # Calculate urgency based on how close to wilting point
            if moisture <= wp:
                urgency = 1.5
            else:
                urgency = 1.0 + (dry - moisture) / (dry - wp) * 0.5
            return True, urgency

        # Between dry and wet thresholds
        # Calculate urgency based on position
        optimal = (dry + wet) / 2
        if moisture < optimal:
            urgency = (optimal - moisture) / (optimal - dry) * 0.5
            return True, urgency

        return False, 0.0

    def get_moisture_trend(self, zone_id: str, hours: float = 6) -> str:
        """Analyze moisture trend for a zone.

        Args:
            zone_id: Zone identifier
            hours: Number of hours to analyze

        Returns:
            One of: 'rising', 'stable', 'falling', 'falling_fast', 'unknown'
        """
        history = self._zone_history.get(zone_id)
        if not history or len(history) < 2:
            return "unknown"

        # Get readings within the time window
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_readings = [
            r for r in history
            if r["timestamp"] >= cutoff
        ]

        if len(recent_readings) < 2:
            return "unknown"

        # Calculate trend using linear regression slope
        first_value = recent_readings[0]["value"]
        last_value = recent_readings[-1]["value"]

        change = last_value - first_value
        change_rate = change / hours  # % per hour

        if change_rate > 2:
            return "rising"
        elif change_rate > 0.5:
            return "rising_slow"
        elif change_rate < -3:
            return "falling_fast"
        elif change_rate < -1:
            return "falling"
        elif change_rate < -0.2:
            return "falling_slow"
        else:
            return "stable"

    def calculate_water_deficit(self, zone_id: str) -> float:
        """Calculate water deficit as percentage of available water.

        Returns:
            Deficit percentage (0 = at field capacity, 100 = at wilting point)
        """
        moisture = self._zone_moisture.get(zone_id)
        if moisture is None:
            return 50.0  # Assume moderate deficit

        calibration = self._calibration.get(zone_id, {})
        fc = calibration.get("field_capacity", 40)
        wp = calibration.get("wilting_point", 15)
        available = fc - wp

        if available <= 0:
            return 50.0

        if moisture >= fc:
            return 0.0
        elif moisture <= wp:
            return 100.0
        else:
            return (fc - moisture) / available * 100

    def estimate_time_to_dry(
        self, zone_id: str, et_rate_per_day: float = 0.1
    ) -> float | None:
        """Estimate hours until zone reaches dry threshold.

        Args:
            zone_id: Zone identifier
            et_rate_per_day: ET rate in inches per day

        Returns:
            Estimated hours until dry threshold, or None if unknown
        """
        moisture = self._zone_moisture.get(zone_id)
        if moisture is None:
            return None

        calibration = self._calibration.get(zone_id, {})
        dry = calibration.get("dry_threshold", MOISTURE_THRESHOLD_DRY)

        if moisture <= dry:
            return 0.0  # Already dry

        # Estimate based on current trend or ET rate
        trend = self.get_moisture_trend(zone_id, 6)

        if trend == "falling_fast":
            depletion_rate = 4.0  # % per hour
        elif trend == "falling":
            depletion_rate = 2.0
        elif trend == "falling_slow":
            depletion_rate = 0.5
        else:
            # Use ET rate to estimate
            # Rough conversion: 0.1" ET depletes ~1% soil moisture per day
            depletion_rate = et_rate_per_day * 10 / 24

        if depletion_rate <= 0:
            return None  # Not depleting

        return (moisture - dry) / depletion_rate

    def get_watering_factor(self, zone_id: str) -> float:
        """Calculate adjustment factor based on soil moisture.

        Returns:
            Factor between 0.0 and 1.5:
            - 0.0 = Skip (saturated)
            - 0.5 = Reduce (wet)
            - 1.0 = Normal
            - 1.0-1.5 = Increase (dry)
        """
        moisture = self._zone_moisture.get(zone_id)
        if moisture is None:
            return 1.0  # No data, use baseline

        calibration = self._calibration.get(zone_id, {})
        fc = calibration.get("field_capacity", 40)
        dry = calibration.get("dry_threshold", MOISTURE_THRESHOLD_DRY)
        wp = calibration.get("wilting_point", 15)
        optimal = calibration.get("dry_threshold", MOISTURE_THRESHOLD_OPTIMAL)

        if moisture >= fc:
            return 0.0  # Saturated, skip

        if moisture >= dry + 10:
            return 0.3  # Quite wet, minimal watering

        if moisture >= dry:
            return 0.7  # Slightly below optimal

        if moisture >= wp + 5:
            # Normal to somewhat dry
            deficit_ratio = (dry - moisture) / (dry - wp)
            return 1.0 + (deficit_ratio * 0.3)

        # Very dry - increase watering
        return 1.3 + (wp - moisture) / wp * 0.2

    def get_zone_analysis(self, zone_id: str) -> dict[str, Any]:
        """Get complete analysis for a zone."""
        moisture = self._zone_moisture.get(zone_id)
        needs, urgency = self.needs_water(zone_id)

        return {
            "zone_id": zone_id,
            "moisture_level": moisture,
            "status": self.get_moisture_status(zone_id),
            "needs_water": needs,
            "urgency": round(urgency, 2),
            "trend": self.get_moisture_trend(zone_id),
            "water_deficit_pct": round(self.calculate_water_deficit(zone_id), 1),
            "watering_factor": round(self.get_watering_factor(zone_id), 2),
            "soil_type": self._zone_soil_types.get(zone_id, "unknown"),
            "calibration": self._calibration.get(zone_id, {}),
        }

    def get_all_zones_analysis(self) -> dict[str, dict[str, Any]]:
        """Get analysis for all zones."""
        return {
            zone_id: self.get_zone_analysis(zone_id)
            for zone_id in set(self._zone_moisture.keys()) | set(self._calibration.keys())
        }


class RainSensorProcessor:
    """Process rain sensor data for irrigation decisions."""

    def __init__(self) -> None:
        """Initialize the rain sensor processor."""
        self._tripped = False
        self._trip_time: datetime | None = None
        self._external_rain_rate: float | None = None
        self._rain_delay_expires: datetime | None = None

    def update(
        self,
        tripped: bool,
        external_rain_rate: float | None = None,
        rain_delay_expires: str | None = None,
    ) -> None:
        """Update rain sensor status.

        Args:
            tripped: Whether the rain sensor is currently tripped
            external_rain_rate: Rain rate from external sensor (inches/hour)
            rain_delay_expires: When rain delay expires (ISO format)
        """
        if tripped and not self._tripped:
            self._trip_time = datetime.now(timezone.utc)

        self._tripped = tripped
        self._external_rain_rate = external_rain_rate

        if rain_delay_expires:
            try:
                self._rain_delay_expires = datetime.fromisoformat(
                    rain_delay_expires.replace("Z", "+00:00")
                )
            except ValueError:
                self._rain_delay_expires = None
        else:
            self._rain_delay_expires = None

    @property
    def is_raining(self) -> bool:
        """Check if it's currently raining based on sensor."""
        if self._tripped:
            return True
        if self._external_rain_rate and self._external_rain_rate > 0:
            return True
        return False

    @property
    def rain_intensity(self) -> str:
        """Get rain intensity level."""
        if not self.is_raining:
            return "none"

        rate = self._external_rain_rate or 0

        if rate >= 0.5:
            return "heavy"
        elif rate >= 0.2:
            return "moderate"
        elif rate > 0:
            return "light"
        elif self._tripped:
            return "light"  # Sensor tripped but no rate data
        else:
            return "none"

    def get_rain_factor(self) -> float:
        """Get adjustment factor based on rain sensor.

        Returns:
            Factor between 0.0 and 1.0:
            - 0.0 = Heavy rain, skip watering
            - 0.3 = Moderate rain
            - 0.6 = Light rain
            - 1.0 = No rain
        """
        if not self.is_raining:
            # Check if rain delay is active
            if self._rain_delay_expires and self._rain_delay_expires > datetime.now(timezone.utc):
                return 0.0

            return 1.0

        intensity = self.rain_intensity

        if intensity == "heavy":
            return 0.0
        elif intensity == "moderate":
            return 0.3
        elif intensity == "light":
            return 0.6
        else:
            return 1.0

    def time_since_rain_stopped(self) -> timedelta | None:
        """Get time since rain stopped, if applicable."""
        if self.is_raining:
            return None

        if self._trip_time:
            return datetime.now(timezone.utc) - self._trip_time

        return None

    def should_skip_watering(self) -> tuple[bool, str]:
        """Determine if watering should be skipped due to rain.

        Returns:
            Tuple of (should_skip, reason)
        """
        if self.rain_intensity == "heavy":
            return True, "Heavy rain detected"

        if self.rain_intensity == "moderate":
            return True, "Moderate rain detected"

        if self._rain_delay_expires and self._rain_delay_expires > datetime.now(timezone.utc):
            remaining = self._rain_delay_expires - datetime.now(timezone.utc)
            return True, f"Rain delay active ({remaining.seconds // 3600}h remaining)"

        return False, ""

    def get_status(self) -> dict[str, Any]:
        """Get rain sensor status."""
        return {
            "tripped": self._tripped,
            "is_raining": self.is_raining,
            "intensity": self.rain_intensity,
            "external_rain_rate": self._external_rain_rate,
            "rain_factor": self.get_rain_factor(),
            "rain_delay_active": self._rain_delay_expires is not None and self._rain_delay_expires > datetime.now(timezone.utc),
            "rain_delay_expires": self._rain_delay_expires.isoformat() if self._rain_delay_expires else None,
            "time_since_trip": str(datetime.now(timezone.utc) - self._trip_time) if self._trip_time else None,
        }
