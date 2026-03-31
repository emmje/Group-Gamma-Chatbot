"""Vision module — analyse images using Groq's vision-capable LLM.

Supports:
  • Dress-code compliance checks
  • UCU building identification
  • Document / notice / poster reading
  • General image Q&A with RAG context
"""

from __future__ import annotations

import base64
import os
from typing import List, Optional

from groq import Groq


# ── Groq client (shared helper) ──────────────────────────────────────────────

def _build_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for vision.")
    raw_base_url = os.getenv("GROQ_BASE_URL", "").strip()
    if not raw_base_url:
        return Groq(api_key=api_key)
    normalized = raw_base_url.rstrip("/")
    if normalized.endswith("/openai/v1"):
        normalized = normalized[: -len("/openai/v1")]
    return Groq(api_key=api_key, base_url=normalized)


# ── Vision model name ────────────────────────────────────────────────────────

VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")


# ── System prompts for different scenarios ───────────────────────────────────

_SYSTEM_GENERAL = (
    "You are the Gamma Chatbot vision assistant for Uganda Christian University (UCU). "
    "Analyse the image the user has uploaded and answer their question. "
    "If relevant UCU document context is provided below, use it to ground your answer. "
    "Be helpful, concise, and conversational."
)

_SYSTEM_DRESS_CODE = (
    "You are the Gamma Chatbot dress-code advisor for Uganda Christian University. "
    "The user has uploaded a photo of an outfit. Examine it carefully and determine "
    "whether it complies with UCU's dress code policy as described in the Context below.\n\n"
    "RULES:\n"
    "1. Describe what you see in the image.\n"
    "2. Compare it against the UCU dress code policy from the Context.\n"
    "3. Give a clear verdict: ACCEPTABLE or NOT ACCEPTABLE.\n"
    "4. If not acceptable, explain which specific rule is violated and suggest corrections.\n"
    "5. Be respectful and encourage the student."
)

_SYSTEM_BUILDING = (
    "You are the Gamma Chatbot campus guide for Uganda Christian University. "
    "The user has uploaded a photo of a building or campus area. "
    "Using the UCU campus information from the Context below:\n\n"
    "1. Try to identify the building or location in the image.\n"
    "2. Provide its name, purpose, and location on campus.\n"
    "3. If you cannot identify it with certainty, describe what you see and suggest "
    "   which UCU buildings it might be based on the Context.\n"
    "4. Offer helpful directions or related information.\n\n"
    "Known UCU buildings:\n"
    "- Bishop Tucker Building (Vice Chancellor's office, chapel, Theology & Divinity)\n"
    "- Hamu Mukasa Library (3-level library with reading rooms & computer labs)\n"
    "- Nkoyoyo Hall (community gathering hall, named after Archbishop Nkoyoyo)\n"
    "- K-Block / Bishop Festo Kivengere Lecture Block\n"
    "- M-Block / Bishop Eliphazi Maari Lecture Block\n"
    "- N-Block / Stephen & Peggy Noll Lecture Block\n"
    "- Janan Luwum Dining Hall (feeds 2500+ students daily)\n"
    "- Sabiiti & Nsibambi Halls (female residence halls)\n"
    "- Allan Galpin Health Centre (student & community clinic)\n"
    "- Misaeri Kawuma Block (Academics Department offices)"
)

_SYSTEM_DOCUMENT = (
    "You are the Gamma Chatbot assistant for Uganda Christian University. "
    "The user has uploaded a photo of a document, notice, poster, timetable, or form. "
    "Read and interpret the content of the document in the image. "
    "Summarise the key information and answer any question the user has about it. "
    "If relevant UCU context is provided, use it to give additional helpful information."
)


def _pick_system_prompt(scenario: str) -> str:
    return {
        "dress_code": _SYSTEM_DRESS_CODE,
        "building": _SYSTEM_BUILDING,
        "document": _SYSTEM_DOCUMENT,
    }.get(scenario, _SYSTEM_GENERAL)


# ── Core vision function ────────────────────────────────────────────────────

def analyse_image(
    image_bytes: bytes,
    question: str,
    rag_context: str = "",
    scenario: str = "general",
    mime_type: str = "image/jpeg",
) -> str:
    """Send an image + question to Groq's vision model and return the answer.

    Parameters
    ----------
    image_bytes : raw bytes of the uploaded image
    question    : the user's text question about the image
    rag_context : optional text from RAG retrieval to ground the answer
    scenario    : one of "general", "dress_code", "building", "document"
    mime_type   : MIME type of the image (image/jpeg, image/png, etc.)
    """
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64}"

    system = _pick_system_prompt(scenario)

    # Append RAG context to the system prompt if available
    if rag_context:
        system += (
            "\n\n--- UCU Document Context ---\n"
            f"{rag_context}\n"
            "--- End Context ---"
        )

    user_content: list = [
        {"type": "image_url", "image_url": {"url": data_url}},
        {"type": "text", "text": question},
    ]

    client = _build_groq_client()
    response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        max_tokens=500,
    )
    return (response.choices[0].message.content or "").strip()


# ── Scenario detection from the user's question ─────────────────────────────

_DRESS_KEYWORDS = {
    "dress", "outfit", "wear", "wearing", "clothes", "clothing", "attire",
    "decent", "indecent", "appropriate", "dress code", "dresscode",
    "skirt", "trouser", "shorts", "mini", "allowed",
}

_BUILDING_KEYWORDS = {
    "building", "block", "hall", "campus", "where is", "location",
    "identify", "which building", "structure", "lecture",
    "nkoyoyo", "galpin", "m block", "n block",
}

_DOCUMENT_KEYWORDS = {
    "document", "notice", "poster", "timetable", "form", "schedule",
    "announcement", "read", "what does it say", "interpret",
}


def detect_scenario(question: str) -> str:
    q = question.lower()
    if any(kw in q for kw in _DRESS_KEYWORDS):
        return "dress_code"
    if any(kw in q for kw in _BUILDING_KEYWORDS):
        return "building"
    if any(kw in q for kw in _DOCUMENT_KEYWORDS):
        return "document"
    return "general"


# ── RAG context fetchers per scenario ────────────────────────────────────────

_SCENARIO_QUERIES = {
    "dress_code": "UCU dress code policy clothing students allowed not allowed",
    "building": "UCU campus buildings blocks halls locations directions",
    "document": "",
    "general": "",
}


def get_rag_context_for_scenario(
    scenario: str,
    user_question: str,
    pipeline=None,
) -> str:
    """Retrieve relevant UCU documents to ground the vision response."""
    if pipeline is None:
        return ""

    # Use a scenario-specific query, fall back to user question
    query = _SCENARIO_QUERIES.get(scenario, "")
    if not query:
        query = user_question

    try:
        chunks = pipeline.retrieve(query)
        if not chunks:
            return ""
        return "\n\n".join(
            f"[{c.metadata.get('title', 'Document')}]: {c.text}"
            for c in chunks
        )
    except Exception:
        return ""
