"""UCU campus building image lookup.

Maps building names/keywords to static image paths so the chatbot can
include a photo when answering questions about campus buildings.
"""

from __future__ import annotations

import re
from typing import Optional

# Each entry: (display_name, image_filename, keyword_patterns)
# keyword_patterns are compiled into case-insensitive regex.
_BUILDINGS: list[tuple[str, str, re.Pattern]] = [
    (
        "Bishop Tucker Building",
        "bishop_tucker_building.jpg",
        re.compile(
            r"bishop\s*tucker|vice\s*chancellor.*(?:office|building)|"
            r"principal.*hall|chapel|theology|divinity",
            re.IGNORECASE,
        ),
    ),
    (
        "Hamu Mukasa Library",
        "hamu_mukasa_library.jpg",
        re.compile(r"hamu\s*mukasa|library", re.IGNORECASE),
    ),
    (
        "Nkoyoyo Hall",
        "nkoyoyo_hall.jpg",
        re.compile(r"nkoyoyo", re.IGNORECASE),
    ),
    (
        "K-Block (Bishop Festo Kivengere Lecture Block)",
        "k_block.jpg",
        re.compile(r"\bk[\s-]*block\b|kivengere", re.IGNORECASE),
    ),
    (
        "M-Block (Bishop Eliphazi Maari Lecture Block)",
        "m_block.jpg",
        re.compile(r"\bm[\s-]*block\b|maari\s*(?:lecture|block)", re.IGNORECASE),
    ),
    (
        "N-Block (Stephen & Peggy Noll Lecture Block)",
        "n_block.jpg",
        re.compile(r"\bn[\s-]*block\b|noll", re.IGNORECASE),
    ),
    (
        "Janan Luwum Dining Hall",
        "janan_luwum_dining_hall.jpg",
        re.compile(r"janan\s*luwum|dining\s*hall", re.IGNORECASE),
    ),
    (
        "Sabiiti & Nsibambi Halls",
        "sabiiti_nsibambi_halls.jpg",
        re.compile(r"sabii?ti|nsibambi", re.IGNORECASE),
    ),
    (
        "Allan Galpin Health Centre",
        "allan_galpin_health_centre.jpg",
        re.compile(r"allan\s*galpin|health\s*cent[re]", re.IGNORECASE),
    ),
    (
        "Misaeri Kawuma Block (Academics Department)",
        "misaeri_kawuma_block.jpg",
        re.compile(
            r"misaeri|kawuma|academics\s*(?:department|block|office)",
            re.IGNORECASE,
        ),
    ),
]

_IMAGE_URL_PREFIX = "/static/images/buildings/"


def find_building_images(text: str) -> list[dict[str, str]]:
    """
    Scan *text* (question or answer) for mentions of UCU buildings.

    Returns a list of dicts: [{"name": ..., "image_url": ...}, ...]
    De-duplicated, preserving order of first match.
    """
    seen: set[str] = set()
    results: list[dict[str, str]] = []
    for display_name, filename, pattern in _BUILDINGS:
        if filename in seen:
            continue
        if pattern.search(text):
            seen.add(filename)
            results.append({
                "name": display_name,
                "image_url": f"{_IMAGE_URL_PREFIX}{filename}",
            })
    return results


def get_building_image(name: str) -> Optional[dict[str, str]]:
    """Return image info for a single building name, or None."""
    for display_name, filename, pattern in _BUILDINGS:
        if pattern.search(name):
            return {"name": display_name, "image_url": f"{_IMAGE_URL_PREFIX}{filename}"}
    return None


def all_building_summaries() -> str:
    """Return a short text listing all known buildings (for vision grounding)."""
    return "\n".join(
        f"- {name} (image: {fname})" for name, fname, _ in _BUILDINGS
    )
