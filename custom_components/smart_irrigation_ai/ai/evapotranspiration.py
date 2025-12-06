"""Evapotranspiration calculator using Penman-Monteith equation."""
from __future__ import annotations

import math
import logging
from datetime import datetime, date
from typing import Any

_LOGGER = logging.getLogger(__name__)


class EvapotranspirationCalculator:
    """Calculate reference evapotranspiration (ET0) using FAO Penman-Monteith equation.

    This is the gold standard for calculating how much water plants lose through
    evaporation and transpiration, which directly informs irrigation needs.
    """

    def __init__(self, latitude: float, elevation: float = 0) -> None:
        """Initialize the ET calculator.

        Args:
            latitude: Location latitude in degrees
            elevation: Elevation above sea level in meters
        """
        self.latitude = latitude
        self.latitude_rad = math.radians(latitude)
        self.elevation = elevation

    def calculate_et0(
        self,
        date_val: date,
        temp_min_c: float,
        temp_max_c: float,
        humidity_min: float,
        humidity_max: float,
        wind_speed_ms: float,
        solar_radiation: float | None = None,
        sunshine_hours: float | None = None,
    ) -> float:
        """Calculate daily reference evapotranspiration (ET0) in mm/day.

        Uses the FAO Penman-Monteith equation (FAO-56).

        Args:
            date_val: Date for calculation (affects solar geometry)
            temp_min_c: Minimum daily temperature in Celsius
            temp_max_c: Maximum daily temperature in Celsius
            humidity_min: Minimum relative humidity (%)
            humidity_max: Maximum relative humidity (%)
            wind_speed_ms: Wind speed at 2m height in m/s
            solar_radiation: Measured solar radiation (MJ/m²/day), optional
            sunshine_hours: Actual sunshine hours, optional

        Returns:
            Reference ET in mm/day
        """
        # Mean temperature
        temp_mean = (temp_min_c + temp_max_c) / 2

        # Atmospheric pressure (kPa) based on elevation
        pressure = 101.3 * ((293 - 0.0065 * self.elevation) / 293) ** 5.26

        # Psychrometric constant (kPa/°C)
        gamma = 0.665e-3 * pressure

        # Saturation vapor pressure (kPa)
        e_s_min = self._saturation_vapor_pressure(temp_min_c)
        e_s_max = self._saturation_vapor_pressure(temp_max_c)
        e_s = (e_s_min + e_s_max) / 2

        # Actual vapor pressure (kPa)
        e_a = (e_s_min * humidity_max / 100 + e_s_max * humidity_min / 100) / 2

        # Vapor pressure deficit
        vpd = e_s - e_a

        # Slope of saturation vapor pressure curve
        delta = self._vapor_pressure_slope(temp_mean)

        # Solar geometry
        day_of_year = date_val.timetuple().tm_yday
        dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)  # Inverse relative distance
        declination = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)

        # Sunset hour angle
        ws = math.acos(-math.tan(self.latitude_rad) * math.tan(declination))

        # Extraterrestrial radiation (MJ/m²/day)
        gsc = 0.0820  # Solar constant
        ra = (24 * 60 / math.pi) * gsc * dr * (
            ws * math.sin(self.latitude_rad) * math.sin(declination) +
            math.cos(self.latitude_rad) * math.cos(declination) * math.sin(ws)
        )

        # Clear-sky solar radiation (MJ/m²/day)
        rso = (0.75 + 2e-5 * self.elevation) * ra

        # Net solar radiation
        if solar_radiation is not None:
            rs = solar_radiation
        elif sunshine_hours is not None:
            # Estimate from sunshine hours (Angstrom formula)
            n = sunshine_hours
            N = 24 * ws / math.pi  # Daylight hours
            rs = (0.25 + 0.5 * n / N) * ra if N > 0 else 0.25 * ra
        else:
            # Estimate assuming partly cloudy conditions
            rs = 0.6 * rso

        # Net shortwave radiation (albedo = 0.23 for grass)
        rns = 0.77 * rs

        # Net longwave radiation
        temp_min_k = temp_min_c + 273.16
        temp_max_k = temp_max_c + 273.16
        sigma = 4.903e-9  # Stefan-Boltzmann constant

        rnl = sigma * ((temp_max_k ** 4 + temp_min_k ** 4) / 2) * \
              (0.34 - 0.14 * math.sqrt(e_a)) * \
              (1.35 * rs / rso - 0.35) if rso > 0 else 0

        # Net radiation (MJ/m²/day)
        rn = rns - rnl

        # Soil heat flux (assume G ≈ 0 for daily calculations)
        g = 0

        # FAO Penman-Monteith equation
        # ET0 = [0.408 Δ(Rn-G) + γ(900/(T+273))u2(es-ea)] / [Δ + γ(1+0.34u2)]
        numerator = 0.408 * delta * (rn - g) + gamma * (900 / (temp_mean + 273)) * wind_speed_ms * vpd
        denominator = delta + gamma * (1 + 0.34 * wind_speed_ms)

        et0 = numerator / denominator

        return max(0, et0)

    def calculate_et0_simple(
        self,
        date_val: date,
        temp_mean_c: float,
        temp_min_c: float,
        temp_max_c: float,
    ) -> float:
        """Calculate ET0 using the Hargreaves-Samani equation.

        A simpler method when only temperature data is available.

        Args:
            date_val: Date for calculation
            temp_mean_c: Mean daily temperature in Celsius
            temp_min_c: Minimum daily temperature in Celsius
            temp_max_c: Maximum daily temperature in Celsius

        Returns:
            Reference ET in mm/day
        """
        # Solar geometry
        day_of_year = date_val.timetuple().tm_yday
        dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
        declination = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)

        ws = math.acos(-math.tan(self.latitude_rad) * math.tan(declination))

        # Extraterrestrial radiation
        gsc = 0.0820
        ra = (24 * 60 / math.pi) * gsc * dr * (
            ws * math.sin(self.latitude_rad) * math.sin(declination) +
            math.cos(self.latitude_rad) * math.cos(declination) * math.sin(ws)
        )

        # Hargreaves-Samani equation
        # ET0 = 0.0023 * (Tmean + 17.8) * (Tmax - Tmin)^0.5 * Ra / λ
        # λ (latent heat of vaporization) ≈ 2.45 MJ/kg
        et0 = 0.0023 * (temp_mean_c + 17.8) * math.sqrt(max(0, temp_max_c - temp_min_c)) * ra / 2.45

        return max(0, et0)

    def calculate_etc(self, et0: float, crop_coefficient: float) -> float:
        """Calculate crop evapotranspiration.

        Args:
            et0: Reference evapotranspiration in mm/day
            crop_coefficient: Crop coefficient (Kc) for the specific vegetation

        Returns:
            Crop evapotranspiration in mm/day
        """
        return et0 * crop_coefficient

    def mm_to_inches(self, mm: float) -> float:
        """Convert millimeters to inches."""
        return mm * 0.0393701

    def inches_to_mm(self, inches: float) -> float:
        """Convert inches to millimeters."""
        return inches * 25.4

    def _saturation_vapor_pressure(self, temp_c: float) -> float:
        """Calculate saturation vapor pressure (kPa) at given temperature."""
        return 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))

    def _vapor_pressure_slope(self, temp_c: float) -> float:
        """Calculate slope of saturation vapor pressure curve (kPa/°C)."""
        return 4098 * self._saturation_vapor_pressure(temp_c) / ((temp_c + 237.3) ** 2)

    def fahrenheit_to_celsius(self, temp_f: float) -> float:
        """Convert Fahrenheit to Celsius."""
        return (temp_f - 32) * 5 / 9

    def mph_to_ms(self, mph: float) -> float:
        """Convert miles per hour to meters per second."""
        return mph * 0.44704


class ETTracker:
    """Track cumulative ET and water balance for irrigation scheduling."""

    def __init__(
        self,
        et_calculator: EvapotranspirationCalculator,
        root_zone_depth_inches: float = 6.0,
        soil_water_capacity: float = 0.15,
        allowed_depletion: float = 0.50,
    ) -> None:
        """Initialize the ET tracker.

        Args:
            et_calculator: ET calculator instance
            root_zone_depth_inches: Root zone depth in inches
            soil_water_capacity: Available water capacity (inches water per inch soil)
            allowed_depletion: Maximum allowable depletion before irrigation (0-1)
        """
        self.et_calculator = et_calculator
        self.root_zone_depth = root_zone_depth_inches
        self.soil_water_capacity = soil_water_capacity
        self.allowed_depletion = allowed_depletion

        # Total available water in root zone (inches)
        self.taw = root_zone_depth_inches * soil_water_capacity

        # Readily available water (how much can be depleted before stress)
        self.raw = self.taw * allowed_depletion

        # Current water balance tracking
        self._cumulative_et = 0.0
        self._cumulative_precip = 0.0
        self._cumulative_irrigation = 0.0
        self._last_update: datetime | None = None

    @property
    def water_deficit(self) -> float:
        """Current water deficit in inches (positive = needs water)."""
        return max(0, self._cumulative_et - self._cumulative_precip - self._cumulative_irrigation)

    @property
    def needs_irrigation(self) -> bool:
        """Check if irrigation is needed based on current deficit."""
        return self.water_deficit >= self.raw

    @property
    def irrigation_needed_inches(self) -> float:
        """Calculate how much irrigation is needed to refill root zone."""
        if not self.needs_irrigation:
            return 0.0
        # Aim to bring back to field capacity
        return min(self.water_deficit, self.taw)

    def add_et(self, et_inches: float, timestamp: datetime | None = None) -> None:
        """Add ET loss to the water balance."""
        self._cumulative_et += et_inches
        self._last_update = timestamp or datetime.now()

    def add_precipitation(self, precip_inches: float, efficiency: float = 0.75) -> None:
        """Add precipitation to the water balance.

        Args:
            precip_inches: Precipitation amount in inches
            efficiency: Fraction of precipitation that is effective (not runoff/evap)
        """
        effective_precip = precip_inches * efficiency
        self._cumulative_precip += effective_precip

    def add_irrigation(self, irrigation_inches: float, efficiency: float = 0.80) -> None:
        """Add irrigation to the water balance.

        Args:
            irrigation_inches: Irrigation amount in inches
            efficiency: Irrigation efficiency (accounting for evap, runoff, etc.)
        """
        effective_irrigation = irrigation_inches * efficiency
        self._cumulative_irrigation += effective_irrigation

    def reset(self) -> None:
        """Reset the water balance (e.g., after deep irrigation)."""
        self._cumulative_et = 0.0
        self._cumulative_precip = 0.0
        self._cumulative_irrigation = 0.0
        self._last_update = datetime.now()

    def get_status(self) -> dict[str, Any]:
        """Get current water balance status."""
        return {
            "cumulative_et": round(self._cumulative_et, 3),
            "cumulative_precip": round(self._cumulative_precip, 3),
            "cumulative_irrigation": round(self._cumulative_irrigation, 3),
            "water_deficit": round(self.water_deficit, 3),
            "needs_irrigation": self.needs_irrigation,
            "irrigation_needed": round(self.irrigation_needed_inches, 3),
            "total_available_water": round(self.taw, 3),
            "readily_available_water": round(self.raw, 3),
            "depletion_percent": round(self.water_deficit / self.taw * 100, 1) if self.taw > 0 else 0,
            "last_update": self._last_update.isoformat() if self._last_update else None,
        }
