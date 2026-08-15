"""Geographic helpers."""

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088
# Average movement speed during flood relief (boats, detours, waterlogged roads).
RELIEF_SPEED_KMH = 15.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def eta_minutes(distance_km: float, speed_kmh: float = RELIEF_SPEED_KMH) -> int:
    return max(1, round(distance_km / speed_kmh * 60))


def valid_coords(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180
