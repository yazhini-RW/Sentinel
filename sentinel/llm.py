"""Gemini free-tier client (plain REST, no SDK dependency).

Returns parsed JSON from the model or raises GeminiError; callers fall back to
the rule-based mock on any failure so the pipeline never hard-requires a key.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import urllib.error
import urllib.request

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class GeminiError(RuntimeError):
    pass


def gemini_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def generate_json(prompt: str, timeout: int = 60):
    """Send a prompt asking for JSON output; parse and return the JSON value."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError("GEMINI_API_KEY not set")

    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }
    ).encode()
    req = urllib.request.Request(
        _ENDPOINT.format(model=GEMINI_MODEL),
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    # OSError covers URLError, ConnectionResetError, and TimeoutError;
    # HTTPException/UnicodeDecodeError can escape urllib while reading the body.
    except (OSError, http.client.HTTPException, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise GeminiError(f"Gemini request failed: {e}") from e

    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise GeminiError(f"Unexpected Gemini response shape: {payload}") from e

    # Strip accidental markdown fences before parsing.
    text = text.strip()
    text = re.sub(r"\A```(?:json)?[ \t]*\n?", "", text)
    text = re.sub(r"\n?```\Z", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise GeminiError(f"Gemini returned non-JSON: {text[:200]}") from e
