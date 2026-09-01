# src/tools/geo_tool.py
from strands import tool
from src.matching import zone_distance_miles


def geo_distance_impl(zone_a: str, zone_b: str) -> float:
    """Return the distance in miles between two named zones (as found in ZONE_GAZETTEER).

    If either zone is unknown to the gazetteer, returns -1.0 -- callers must treat -1.0 as
    "zone unknown" rather than a real distance.
    """
    try:
        result = zone_distance_miles(zone_a, zone_b)
        if result is None:
            return -1.0
        return result
    except Exception:
        return -1.0


geo_distance_tool = tool(geo_distance_impl)
