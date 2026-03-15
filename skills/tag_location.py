"""Skill: Tag activities with ZIP/neighborhood/borough from address text."""

import json
import re
from brain.orchestrator import register_skill
from db.queries.neighborhoods import lookup_zip


# Regex to find NYC ZIP codes (10xxx and 11xxx)
NYC_ZIP_RE = re.compile(r"\b(1[01]\d{3})\b")


@register_skill({
    "name": "tag_location",
    "description": "Extract ZIP code from address text and return neighborhood/borough info. Works with full addresses or just ZIP codes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "Address text or ZIP code to look up",
            },
        },
        "required": ["address"],
    },
})
async def tag_location_skill(address: str) -> str:
    # Try regex extraction
    match = NYC_ZIP_RE.search(address)
    if match:
        zip_code = match.group(1)
        info = lookup_zip(zip_code)
        if info:
            return json.dumps({
                "zip_code": zip_code,
                "neighborhood": info["neighborhood"],
                "borough": info["borough"],
                "source": "zip_lookup",
            })
        return json.dumps({
            "zip_code": zip_code,
            "neighborhood": None,
            "borough": None,
            "source": "zip_not_found",
        })

    addr_lower = address.lower()

    # Check neighborhoods first (more specific than borough)
    neighborhood_borough = {
        "harlem": ("Harlem", "Manhattan"),
        "chelsea": ("Chelsea", "Manhattan"),
        "soho": ("SoHo", "Manhattan"),
        "tribeca": ("Tribeca", "Manhattan"),
        "williamsburg": ("Williamsburg", "Brooklyn"),
        "park slope": ("Park Slope", "Brooklyn"),
        "astoria": ("Astoria", "Queens"),
        "flushing": ("Flushing", "Queens"),
        "long island city": ("Long Island City", "Queens"),
        "upper west side": ("Upper West Side", "Manhattan"),
        "upper east side": ("Upper East Side", "Manhattan"),
        "greenpoint": ("Greenpoint", "Brooklyn"),
        "bushwick": ("Bushwick", "Brooklyn"),
        "crown heights": ("Crown Heights", "Brooklyn"),
        "bed-stuy": ("Bedford-Stuyvesant", "Brooklyn"),
        "bedford-stuyvesant": ("Bedford-Stuyvesant", "Brooklyn"),
        "fort greene": ("Fort Greene", "Brooklyn"),
        "dumbo": ("DUMBO", "Brooklyn"),
        "prospect heights": ("Prospect Heights", "Brooklyn"),
        "bay ridge": ("Bay Ridge", "Brooklyn"),
        "sunset park": ("Sunset Park", "Brooklyn"),
        "jackson heights": ("Jackson Heights", "Queens"),
        "forest hills": ("Forest Hills", "Queens"),
        "riverdale": ("Riverdale", "Bronx"),
        "mott haven": ("Mott Haven", "Bronx"),
    }
    for key, (neighborhood, borough) in neighborhood_borough.items():
        if key in addr_lower:
            return json.dumps({
                "zip_code": None,
                "neighborhood": neighborhood,
                "borough": borough,
                "source": "neighborhood_inference",
            })

    # Fall back to borough inference
    borough_map = {
        "manhattan": "Manhattan",
        "brooklyn": "Brooklyn",
        "queens": "Queens",
        "bronx": "Bronx",
        "the bronx": "Bronx",
        "staten island": "Staten Island",
    }
    for key, borough in borough_map.items():
        if key in addr_lower:
            return json.dumps({
                "zip_code": None,
                "neighborhood": None,
                "borough": borough,
                "source": "text_inference",
            })

    return json.dumps({
        "zip_code": None,
        "neighborhood": None,
        "borough": None,
        "source": "unknown",
    })
