"""Meta WhatsApp Cloud API helper utilities."""

from __future__ import annotations

import os
from typing import Any

import requests


def _normalize_base_url(base_url: str) -> str:
    base = base_url.strip()
    if not base:
        return "https://graph.facebook.com"
    return base.rstrip("/")


def load_whatsapp_config() -> dict[str, str]:
    """Load WhatsApp Cloud API settings from environment variables."""
    return {
        "base_url": _normalize_base_url(os.getenv("META_GRAPH_BASE_URL", "https://graph.facebook.com")),
        "api_version": os.getenv("META_GRAPH_API_VERSION", "v20.0").strip(),
        "access_token": os.getenv("META_WHATSAPP_ACCESS_TOKEN", "").strip(),
        "phone_number_id": os.getenv("META_WHATSAPP_PHONE_NUMBER_ID", "").strip(),
        "verify_token": os.getenv("META_WHATSAPP_VERIFY_TOKEN", "").strip(),
    }


def is_whatsapp_configured() -> bool:
    cfg = load_whatsapp_config()
    return bool(cfg["access_token"] and cfg["phone_number_id"])


def send_whatsapp_text(to_number: str, text: str) -> tuple[int, dict[str, Any]]:
    """
    Send an outbound WhatsApp text message using Meta WhatsApp Cloud API.

    Returns: (status_code, response_json_or_error)
    """
    cfg = load_whatsapp_config()
    if not cfg["access_token"] or not cfg["phone_number_id"]:
        return 500, {"error": "WhatsApp integration is not configured."}

    endpoint = (
        f"{cfg['base_url']}/{cfg['api_version']}/"
        f"{cfg['phone_number_id']}/messages"
    )
    headers = {
        "Authorization": f"Bearer {cfg['access_token']}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        data = response.json() if response.content else {}
        return response.status_code, data
    except requests.RequestException as exc:
        return 502, {"error": f"Failed to call Meta WhatsApp API: {exc}"}
    except ValueError:
        return response.status_code, {"raw": response.text}


def send_whatsapp_image(
    to_number: str,
    image_url: str,
    caption: str = "",
) -> tuple[int, dict[str, Any]]:
    """
    Send an outbound WhatsApp image message using a public URL.

    The image_url must be publicly accessible (https).
    Returns: (status_code, response_json_or_error)
    """
    cfg = load_whatsapp_config()
    if not cfg["access_token"] or not cfg["phone_number_id"]:
        return 500, {"error": "WhatsApp integration is not configured."}

    endpoint = (
        f"{cfg['base_url']}/{cfg['api_version']}/"
        f"{cfg['phone_number_id']}/messages"
    )
    headers = {
        "Authorization": f"Bearer {cfg['access_token']}",
        "Content-Type": "application/json",
    }
    image_obj: dict[str, Any] = {"link": image_url}
    if caption:
        image_obj["caption"] = caption

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "image",
        "image": image_obj,
    }

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        data = response.json() if response.content else {}
        return response.status_code, data
    except requests.RequestException as exc:
        return 502, {"error": f"Failed to call Meta WhatsApp API: {exc}"}
    except ValueError:
        return response.status_code, {"raw": response.text}


def extract_inbound_text_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    """
    Parse Meta WhatsApp webhook payload and return text messages.

    Output rows: {"id": "<message-id>", "from": "<phone>", "text": "<message>"}
    """
    messages: list[dict[str, str]] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return messages

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue

        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            inbound = value.get("messages")
            if not isinstance(inbound, list):
                continue

            for message in inbound:
                if not isinstance(message, dict):
                    continue
                if message.get("type") != "text":
                    continue
                message_id = str(message.get("id", "")).strip()
                from_number = str(message.get("from", "")).strip()
                text_obj = message.get("text")
                text = ""
                if isinstance(text_obj, dict):
                    text = str(text_obj.get("body", "")).strip()
                if from_number and text:
                    messages.append({"id": message_id, "from": from_number, "text": text})

    return messages


def extract_inbound_image_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    """
    Parse Meta WhatsApp webhook payload and return image messages.

    Output rows: {"id": "<message-id>", "from": "<phone>",
                  "media_id": "<media-id>", "mime_type": "image/jpeg",
                  "caption": "<optional caption>"}
    """
    messages: list[dict[str, str]] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return messages

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue

        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            inbound = value.get("messages")
            if not isinstance(inbound, list):
                continue

            for message in inbound:
                if not isinstance(message, dict):
                    continue
                if message.get("type") != "image":
                    continue
                message_id = str(message.get("id", "")).strip()
                from_number = str(message.get("from", "")).strip()
                image_obj = message.get("image")
                if not isinstance(image_obj, dict):
                    continue
                media_id = str(image_obj.get("id", "")).strip()
                mime_type = str(image_obj.get("mime_type", "image/jpeg")).strip()
                caption = str(image_obj.get("caption", "")).strip()
                if from_number and media_id:
                    messages.append({
                        "id": message_id,
                        "from": from_number,
                        "media_id": media_id,
                        "mime_type": mime_type,
                        "caption": caption,
                    })

    return messages


def download_whatsapp_media(media_id: str) -> tuple[bytes | None, str]:
    """
    Download media from Meta WhatsApp Cloud API.

    1. GET /media_id to get the download URL
    2. GET the download URL to get the binary data

    Returns: (image_bytes_or_None, mime_type)
    """
    cfg = load_whatsapp_config()
    if not cfg["access_token"]:
        return None, ""

    headers = {"Authorization": f"Bearer {cfg['access_token']}"}

    # Step 1: Get media URL
    media_url_endpoint = f"{cfg['base_url']}/{cfg['api_version']}/{media_id}"
    try:
        resp = requests.get(media_url_endpoint, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None, ""
        data = resp.json()
        download_url = data.get("url", "")
        mime_type = data.get("mime_type", "image/jpeg")
        if not download_url:
            return None, ""
    except (requests.RequestException, ValueError):
        return None, ""

    # Step 2: Download the actual media
    try:
        resp = requests.get(download_url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return None, ""
        return resp.content, mime_type
    except requests.RequestException:
        return None, ""


def send_whatsapp_interactive_list(
    to_number: str,
    header_text: str = "Explore UCU Campus",
    body_text: str = (
        "Hello! I can answer questions about UCU using a verified knowledge base "
        "and official university documents. What would you like to know?\n\n"
        "You can also explore what's happening around campus:"
    ),
    footer_text: str = "Tap to explore",
) -> tuple[int, dict[str, Any]]:
    """
    Send a WhatsApp interactive list message with campus sections.
    """
    cfg = load_whatsapp_config()
    if not cfg["access_token"] or not cfg["phone_number_id"]:
        return 500, {"error": "WhatsApp integration is not configured."}

    endpoint = (
        f"{cfg['base_url']}/{cfg['api_version']}/"
        f"{cfg['phone_number_id']}/messages"
    )
    headers = {
        "Authorization": f"Bearer {cfg['access_token']}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header_text},
            "body": {"text": body_text},
            "footer": {"text": footer_text},
            "action": {
                "button": "Explore Campus",
                "sections": [
                    {
                        "title": "What's going on around Campus",
                        "rows": [
                            {
                                "id": "campus_events",
                                "title": "Campus Events",
                                "description": "See upcoming events, festivals & activities",
                            },
                            {
                                "id": "campus_news",
                                "title": "Campus News",
                                "description": "Latest announcements & updates",
                            },
                        ],
                    },
                    {
                        "title": "Find your Tribe",
                        "rows": [
                            {
                                "id": "clubs_groups",
                                "title": "Clubs & Groups",
                                "description": "Launch Padders, Debate Club & more",
                            },
                            {
                                "id": "sports_teams",
                                "title": "Sports Teams",
                                "description": "Join a varsity or intramural team",
                            },
                        ],
                    },
                ],
            },
        },
    }

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        data = response.json() if response.content else {}
        return response.status_code, data
    except requests.RequestException as exc:
        return 502, {"error": f"Failed to call Meta WhatsApp API: {exc}"}
    except ValueError:
        return response.status_code, {"raw": response.text}
