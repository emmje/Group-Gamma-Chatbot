"""UCU campus building image lookup.

Maps building names/keywords to static image paths so the chatbot can
include photos when answering questions about campus buildings.
Supports multiple images per building.
"""

from __future__ import annotations

import re
from typing import Optional

# Each entry: (display_name, [image_filenames], keyword_pattern)
_BUILDINGS: list[tuple[str, list[str], re.Pattern]] = [
    (
        "Bishop Tucker Building",
        ["bishop_tucker_building.jpg", "bishop_tucker_building_2.jpeg"],
        re.compile(
            r"bishop\s*tucker|vice\s*chancellor.*(?:office|building)|"
            r"principal.*hall|chapel|theology|divinity",
            re.IGNORECASE,
        ),
    ),
    (
        "Hamu Mukasa Library",
        [
            "hamu_mukasa_library.jpg",
            "hamu_mukasa_library_2.jpeg",
            "hamu_mukasa_library_3.jpeg",
            "hamu_mukasa_library_back.jpeg",
        ],
        re.compile(r"hamu?\s*mukasa|main\s+library", re.IGNORECASE),
    ),
    (
        "Nkoyoyo Hall",
        ["nkoyoyo_hall.jpg", "nkoyoyo_hall_2.jpeg", "nkoyoyo_hall_back.jpeg"],
        re.compile(r"nkoyoyo", re.IGNORECASE),
    ),
    (
        "K-Block (Bishop Festo Kivengere Lecture Block)",
        ["k_block.jpg", "k_block_2.jpeg", "k_block_3.jpeg"],
        re.compile(r"\bk[\s-]*block\b|kivengere", re.IGNORECASE),
    ),
    (
        "M-Block (Bishop Eliphazi Maari Lecture Block)",
        ["m_block.jpg", "m_block_2.jpeg"],
        re.compile(r"\bm[\s-]*block\b|maari\s*(?:lecture|block)", re.IGNORECASE),
    ),
    (
        "N-Block (Stephen & Peggy Noll Lecture Block)",
        ["n_block.jpg"],
        re.compile(r"\bn[\s-]*block\b|noll", re.IGNORECASE),
    ),
    (
        "Janan Luwum Dining Hall",
        ["janan_luwum_dining_hall.jpg", "janan_luwum_dining_hall_2.jpeg"],
        re.compile(r"janan\s*luwum|dining\s*hall", re.IGNORECASE),
    ),
    (
        "Sabiiti & Nsibambi Halls",
        ["sabiiti_nsibambi_halls.jpg", "sabiiti_nsibambi_halls_2.jpeg", "sabiiti_nsibambi_halls_3.jpeg"],
        re.compile(r"sabii?ti|nsibambi", re.IGNORECASE),
    ),
    (
        "Allan Galpin Health Centre",
        ["allan_galpin_health_centre.jpg", "allan_galpin_health_centre_2.jpeg"],
        re.compile(r"allan\s*galpin|health\s*cent[re]", re.IGNORECASE),
    ),
    (
        "Misaeri Kawuma Block (Academics Department)",
        ["misaeri_kawuma_block.jpg", "misaeri_kawuma_block_2.jpeg"],
        re.compile(
            r"misaeri|kawuma|academics\s*(?:department|block|office)",
            re.IGNORECASE,
        ),
    ),
    (
        "Department of Computing",
        ["computing_department.jpeg"],
        re.compile(
            r"computing|computer\s*science|staff\s*room.*computing|comput.*department",
            re.IGNORECASE,
        ),
    ),
    (
        "Dustan Bukenya Library",
        ["dustan_bukenya_library.jpeg"],
        re.compile(r"dustan|bukenya", re.IGNORECASE),
    ),
    (
        "ICMI Social Health & Science Block",
        ["icmi_health_sciences_block.jpeg"],
        re.compile(r"icmi|social\s*health|health.*science\s*block", re.IGNORECASE),
    ),
    (
        "Main University Pitch",
        ["main_university_pitch.jpeg"],
        re.compile(r"main\s*(?:university\s*)?pitch|football\s*pitch|soccer\s*pitch", re.IGNORECASE),
    ),
    (
        "Road to Main Gate",
        ["road_to_main_gate.jpeg"],
        re.compile(r"main\s*gate|entrance.*road|road.*gate", re.IGNORECASE),
    ),
    (
        "University Basketball Pitch",
        ["university_basketball_pitch.jpeg"],
        re.compile(r"basketball\s*(?:pitch|court)", re.IGNORECASE),
    ),
]

_IMAGE_URL_PREFIX = "/static/images/buildings/"


def find_building_images(text: str) -> list[dict]:
    """
    Scan *text* for mentions of UCU buildings.

    Returns a list of dicts:
        [{"name": ..., "images": ["/static/images/buildings/file.jpg", ...]}, ...]
    De-duplicated, preserving order of first match.
    """
    seen: set[str] = set()
    results: list[dict] = []
    for display_name, filenames, pattern in _BUILDINGS:
        if display_name in seen:
            continue
        if pattern.search(text):
            seen.add(display_name)
            results.append({
                "name": display_name,
                "images": [f"{_IMAGE_URL_PREFIX}{f}" for f in filenames],
            })
    return results


def get_building_image(name: str) -> Optional[dict]:
    """Return image info for a single building name, or None."""
    for display_name, filenames, pattern in _BUILDINGS:
        if pattern.search(name):
            return {
                "name": display_name,
                "images": [f"{_IMAGE_URL_PREFIX}{f}" for f in filenames],
            }
    return None


def all_building_summaries() -> str:
    """Return a short text listing all known buildings (for vision grounding)."""
    return "\n".join(
        f"- {name} ({len(fnames)} photo{'s' if len(fnames) > 1 else ''})"
        for name, fnames, _ in _BUILDINGS
    )
