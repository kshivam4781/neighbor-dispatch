# src/tools/category_tool.py
from strands import tool
from src.matching import category_matches


def category_match_impl(category_a: str, category_b: str) -> bool:
    """Return True if two need/offer categories refer to the same taxonomy bucket."""
    return category_matches(category_a, category_b)


category_match_tool = tool(category_match_impl)
