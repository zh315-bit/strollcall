import math


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def coord_key(lat: float, lon: float, ndigits: int = 4) -> str:
    """Cache key for a point; 4 decimals is about 11 m in NYC."""
    return f"{round(lat, ndigits):.{ndigits}f},{round(lon, ndigits):.{ndigits}f}"
