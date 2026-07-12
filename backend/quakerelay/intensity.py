import math
from dataclasses import dataclass

from .geo import haversine_km


@dataclass(frozen=True)
class IntensityResult:
    epicentral_distance_km: float
    hypocentral_distance_km: float
    estimated_intensity: float | None
    intensity_level: int | None
    confidence: str
    model_version: str
    triggered: bool
    status: str
    error: str | None = None


class ChinaRegionalIntensityModel:
    """Conservative east/west regional intensity attenuation estimator.

    Coefficients are versioned rather than remotely configured so historical
    estimates remain reproducible. The output is an auxiliary estimate, not an
    official intensity forecast.
    """

    version = "china-regional-attenuation-2000-v1"
    transition_min_lon = 103.0
    transition_max_lon = 107.0
    max_distance_km = 1000.0
    safety_margin = 0.5

    @staticmethod
    def _east(magnitude: float, distance: float) -> float:
        return 5.019 + 1.446 * magnitude - 4.136 * math.log10(distance + 24.0)

    @staticmethod
    def _west(magnitude: float, distance: float) -> float:
        return 6.725 + 1.293 * magnitude - 3.105 * math.log10(distance + 18.0)

    def estimate(
        self,
        *,
        magnitude: float | None,
        depth_km: float | None,
        event_latitude: float,
        event_longitude: float,
        location_latitude: float,
        location_longitude: float,
    ) -> IntensityResult:
        epicentral = haversine_km(
            event_latitude, event_longitude, location_latitude, location_longitude
        )
        conservative_depth = max(1.0, depth_km if depth_km is not None else 10.0)
        hypocentral = math.hypot(epicentral, conservative_depth)
        if epicentral > self.max_distance_km:
            return IntensityResult(
                epicentral,
                hypocentral,
                None,
                None,
                "low",
                self.version,
                False,
                "out_of_range",
            )
        if magnitude is None:
            return IntensityResult(
                epicentral,
                hypocentral,
                None,
                None,
                "low",
                self.version,
                epicentral <= 300.0,
                "insufficient_data",
            )

        if event_longitude < self.transition_min_lon:
            raw = self._west(magnitude, hypocentral)
        elif event_longitude > self.transition_max_lon:
            raw = self._east(magnitude, hypocentral)
        else:
            raw = max(self._east(magnitude, hypocentral), self._west(magnitude, hypocentral))

        estimate = min(12.0, max(0.0, raw + self.safety_margin))
        level = max(1, min(12, math.ceil(estimate)))
        confidence = "high" if depth_km is not None and epicentral <= 300 else "medium"
        # High-sensitivity mode: the conservative estimate reaching intensity II is actionable.
        triggered = estimate >= 2.0
        return IntensityResult(
            round(epicentral, 2),
            round(hypocentral, 2),
            round(estimate, 2),
            level,
            confidence,
            self.version,
            triggered,
            "estimated",
        )
