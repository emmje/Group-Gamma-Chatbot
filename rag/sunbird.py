from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os

import requests
from dotenv import dotenv_values, load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)
_DOTENV_VALUES = dotenv_values(_PROJECT_ROOT / ".env")


def _get_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is not None and value.strip() != "":
        return value.strip()
    dotenv_value = _DOTENV_VALUES.get(name)
    if isinstance(dotenv_value, str) and dotenv_value.strip() != "":
        return dotenv_value.strip()
    return default


class SunbirdError(RuntimeError):
    pass


@dataclass(frozen=True)
class SunbirdConfig:
    api_key: str
    base_url: str
    translate_endpoint: str
    language_id_endpoint: str
    tts_endpoint: str
    stt_endpoint: str
    timeout_seconds: int


def load_sunbird_config() -> SunbirdConfig:
    api_key = _get_env("SUNBIRD_API_KEY")
    base_url = _get_env("SUNBIRD_BASE_URL", "https://api.sunbird.ai").rstrip("/")
    translate_endpoint = _get_env("SUNBIRD_TRANSLATE_ENDPOINT", "/tasks/translate")
    language_id_endpoint = _get_env("SUNBIRD_LANGUAGE_ID_ENDPOINT", "/tasks/language_id")
    tts_endpoint = _get_env("SUNBIRD_TTS_ENDPOINT", "/tasks/tts")
    stt_endpoint = _get_env("SUNBIRD_STT_ENDPOINT", "/tasks/stt")
    timeout_seconds = int(_get_env("SUNBIRD_TIMEOUT_SECONDS", "120"))

    return SunbirdConfig(
        api_key=api_key,
        base_url=base_url,
        translate_endpoint=translate_endpoint,
        language_id_endpoint=language_id_endpoint,
        tts_endpoint=tts_endpoint,
        stt_endpoint=stt_endpoint,
        timeout_seconds=timeout_seconds,
    )


def _normalize_language(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if raw in {"ach", "teo", "eng", "lug", "lgg", "nyn", "swa", "xog", "ttj", "myx"}:
        return raw

    aliases = {
        "english": "eng",
        "luganda": "lug",
        "lugbara": "lgg",
        "runyankole": "nyn",
        "ateso": "teo",
        "acholi": "ach",
        "swahili": "swa",
        "lusoga": "xog",
        "rutooro": "ttj",
        "lumasaba": "myx",
    }
    return aliases.get(raw, raw)


class SunbirdClient:
    def __init__(self, config: SunbirdConfig | None = None) -> None:
        self.config = config or load_sunbird_config()

    def is_configured(self) -> bool:
        return bool(self.config.api_key and self.config.base_url)

    def _headers(self) -> dict[str, str]:
        if not self.config.api_key:
            raise SunbirdError("SUNBIRD_API_KEY is not configured.")
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Accept": "application/json",
        }

    def _url(self, endpoint: str) -> str:
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        return f"{self.config.base_url}{endpoint}"

    def detect_language(self, text: str) -> str:
        payload = {"text": text}
        try:
            response = requests.post(
                self._url(self.config.language_id_endpoint),
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise SunbirdError(f"Sunbird language detection request failed: {exc}") from exc

        self._raise_for_error(response, "language detection")
        data = response.json()

        if isinstance(data, dict):
            if isinstance(data.get("language"), str):
                return _normalize_language(data.get("language", ""))
            output = data.get("output")
            if isinstance(output, dict):
                for key in ("language", "detected_language", "lang", "label"):
                    value = output.get(key)
                    if isinstance(value, str):
                        return _normalize_language(value)
        return ""

    def _raise_for_error(self, response: requests.Response, operation: str) -> None:
        if response.ok:
            return
        detail = ""
        try:
            payload = response.json()
            detail = payload.get("detail") or payload.get("error") or str(payload)
        except Exception:
            detail = response.text[:500]
        raise SunbirdError(f"Sunbird {operation} failed ({response.status_code}): {detail}")

    def translate(self, text: str, source_language: str, target_language: str) -> dict[str, Any]:
        source_language = _normalize_language(source_language)
        target_language = _normalize_language(target_language)
        payload = {
            "text": text,
            "source_language": source_language,
            "target_language": target_language,
        }
        try:
            response = requests.post(
                self._url(self.config.translate_endpoint),
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise SunbirdError(f"Sunbird translate request failed: {exc}") from exc

        self._raise_for_error(response, "translation")
        data = response.json()

        translated_text = ""
        # Primary: output.translated_text (confirmed Sunbird response format)
        if isinstance(data.get("output"), dict):
            out = data["output"]
            translated_text = out.get("translated_text") or out.get("text") or ""
        # Fallback: top-level text
        if not translated_text:
            translated_text = data.get("text") or ""
        # Fallback: responses array
        if not translated_text:
            responses = data.get("responses")
            if isinstance(responses, list) and responses:
                first = responses[0] or {}
                translated_text = first.get("text") or ""

        return {
            "text": translated_text,
            "raw": data,
        }

    def text_to_speech(
        self,
        text: str,
        speaker_id: int = 248,
        response_mode: str = "url",
        temperature: float | None = None,
        max_new_audio_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "text": text,
            "speaker_id": speaker_id,
            "response_mode": response_mode,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_new_audio_tokens is not None:
            payload["max_new_audio_tokens"] = max_new_audio_tokens

        try:
            response = requests.post(
                self._url(self.config.tts_endpoint),
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise SunbirdError(f"Sunbird TTS request failed: {exc}") from exc

        self._raise_for_error(response, "TTS")
        data = response.json()

        audio_url = ""
        # Primary: output.audio_url (confirmed Sunbird response format)
        if isinstance(data, dict) and isinstance(data.get("output"), dict):
            audio_url = data["output"].get("audio_url", "")
        # Fallback: top-level audio_url
        if not audio_url and isinstance(data, dict):
            audio_url = data.get("audio_url", "")

        return {
            "audio_url": audio_url,
            "raw": data,
        }

    def speech_to_text(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
        language: str | None = None,
        adapter: str | None = None,
        whisper: bool | None = None,
        recognise_speakers: bool | None = None,
    ) -> dict[str, Any]:
        files = {
            "audio": (filename, audio_bytes, content_type or "application/octet-stream"),
        }

        data: dict[str, str] = {}
        if language:
            data["language"] = language
        if adapter:
            data["adapter"] = adapter
        if whisper is not None:
            data["whisper"] = "true" if whisper else "false"
        if recognise_speakers is not None:
            data["recognise_speakers"] = "true" if recognise_speakers else "false"

        try:
            response = requests.post(
                self._url(self.config.stt_endpoint),
                headers=self._headers(),
                files=files,
                data=data,
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise SunbirdError(f"Sunbird STT request failed: {exc}") from exc

        self._raise_for_error(response, "STT")
        resp_data = response.json()

        transcript = ""
        # Primary: output.text (confirmed Sunbird response format)
        if isinstance(resp_data, dict) and isinstance(resp_data.get("output"), dict):
            out = resp_data["output"]
            transcript = out.get("text") or out.get("audio_transcription") or ""
        # Fallback: top-level keys
        if not transcript and isinstance(resp_data, dict):
            transcript = (
                resp_data.get("audio_transcription")
                or resp_data.get("text")
                or resp_data.get("transcription")
                or ""
            )

        return {
            "text": transcript,
            "raw": resp_data,
        }
