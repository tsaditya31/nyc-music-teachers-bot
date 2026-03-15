"""Neighborhood lookup queries."""
from __future__ import annotations

import json
import os


def _load_neighborhoods():
    """Load neighborhoods from JSON file into a dict keyed by ZIP."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "nyc_neighborhoods.json",
    )
    with open(path) as f:
        data = json.load(f)
    return {entry["zip_code"]: entry for entry in data}


_NEIGHBORHOODS = _load_neighborhoods()


def lookup_zip(zip_code: str) -> dict | None:
    """Return {zip_code, neighborhood, borough} or None."""
    return _NEIGHBORHOODS.get(zip_code)


def all_zips() -> list[str]:
    return list(_NEIGHBORHOODS.keys())


def zips_for_borough(borough: str) -> list[str]:
    return [z for z, n in _NEIGHBORHOODS.items() if n["borough"].lower() == borough.lower()]


def zips_for_neighborhood(neighborhood: str) -> list[str]:
    return [
        z
        for z, n in _NEIGHBORHOODS.items()
        if n["neighborhood"].lower() == neighborhood.lower()
    ]
