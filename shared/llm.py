"""
shared/llm.py
-------------
One small helper for talking to Claude. Every agent uses this.

WORKS WITH
  - OpenRouter  (OPENROUTER_API_KEY)  <- what you are using
  - Anthropic direct (ANTHROPIC_API_KEY)
  - No key at all -> automatic mock mode

TWO PROBLEMS THIS FILE SOLVES FOR YOU
  1. Your .env uses OpenRouter, so we point the anthropic SDK at it.
  2. Older anthropic SDK versions reject the 'temperature' argument.
     We now detect that and retry without it, so it works either way.
"""

import inspect
import json
import os
import re

from dotenv import load_dotenv

load_dotenv(override=True)


def _clean(value: str) -> str:
    """Strip whitespace and stray quotes from a .env value."""
    return (value or "").strip().strip('"').strip("'").strip()


def _resolve_config():
    """
    Decide which provider to use.
      1. OPENROUTER_API_KEY -> OpenRouter
      2. ANTHROPIC_API_KEY  -> Anthropic direct
    """
    openrouter_key = _clean(os.getenv("OPENROUTER_API_KEY", ""))
    anthropic_key = _clean(os.getenv("ANTHROPIC_API_KEY", ""))

    if openrouter_key:
        base_url = _clean(os.getenv("END_POINT", "https://openrouter.ai/api")).rstrip("/")
        # The SDK appends /v1/messages, so base_url must NOT already end in /v1
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]

        model = _clean(os.getenv("CLAUDE_MODEL", "anthropic/claude-haiku-4-5"))
        return {
            "provider": "openrouter",
            "api_key": openrouter_key,
            "base_url": base_url,
            "model": model,
        }

    if anthropic_key:
        return {
            "provider": "anthropic",
            "api_key": anthropic_key,
            "base_url": None,
            "model": _clean(os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")),
        }

    return {"provider": "none", "api_key": "", "base_url": None, "model": ""}


CONFIG = _resolve_config()
PROVIDER = CONFIG["provider"]
MODEL = CONFIG["model"]

USE_MOCK = _clean(os.getenv("USE_MOCK", "")).lower() == "true" or PROVIDER == "none"

_client = None
# Some older SDK builds do not accept 'temperature'. We find out once,
# then remember, instead of failing on every single call.
_supports_temperature = True


def _get_client():
    """Create the client once and reuse it."""
    global _client
    if _client is None:
        import anthropic

        if CONFIG["base_url"]:
            _client = anthropic.Anthropic(
                api_key=CONFIG["api_key"],
                base_url=CONFIG["base_url"],
            )
        else:
            _client = anthropic.Anthropic(api_key=CONFIG["api_key"])
    return _client


def _extract_json(text: str) -> dict:
    """Pull the first {...} block out of the reply and parse it."""
    match = re.search(r"\{.*\}", (text or "").strip(), re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in the reply: {(text or '')[:200]}")
    return json.loads(match.group(0))


def _read_text(response) -> str:
    """Get the text out of the response, across SDK versions."""
    content = getattr(response, "content", None)
    if isinstance(content, list) and content:
        block = content[0]
        return getattr(block, "text", None) or (
            block.get("text", "") if isinstance(block, dict) else ""
        )
    if isinstance(content, str):
        return content
    return str(response)


def _create(system_prompt: str, user_prompt: str):
    """
    Call the model. Tries with temperature, and if this SDK version does
    not support it, drops it and remembers for next time.
    """
    global _supports_temperature

    kwargs = {
        "model": MODEL,
        "max_tokens": 1000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    if _supports_temperature:
        try:
            return _get_client().messages.create(temperature=0, **kwargs)
        except TypeError as error:
            if "temperature" not in str(error):
                raise
            _supports_temperature = False
            print("[llm] This anthropic SDK does not accept 'temperature'. Continuing without it.")

    return _get_client().messages.create(**kwargs)


def ask_claude(system_prompt: str, user_prompt: str, fallback: dict) -> tuple[dict, bool]:
    """
    Ask the model a question and get a Python dict back.

    Returns (answer_dict, llm_was_actually_used)
    Never raises. On any failure it returns your fallback.
    """
    if USE_MOCK:
        return fallback, False

    try:
        return _extract_json(_read_text(_create(system_prompt, user_prompt))), True

    except Exception as first_error:
        # ONE retry, being much firmer about the JSON requirement.
        try:
            strict = system_prompt + (
                "\n\nIMPORTANT: Reply with raw JSON only. "
                "No markdown fences, no explanation, no text before or after."
            )
            return _extract_json(_read_text(_create(strict, user_prompt))), True
        except Exception as second_error:
            print(f"[llm] Model unavailable ({second_error}). Using the rule-based fallback.")
            return fallback, False


def diagnose() -> dict:
    """Used by check_setup.py to report what is configured."""
    try:
        import anthropic
        sdk_version = getattr(anthropic, "__version__", "unknown")
        signature = inspect.signature(anthropic.Anthropic.__init__)
        supports_base_url = "base_url" in signature.parameters
    except Exception:
        sdk_version = "not installed"
        supports_base_url = False

    return {
        "provider": PROVIDER,
        "model": MODEL,
        "base_url": CONFIG["base_url"],
        "key_tail": CONFIG["api_key"][-6:] if CONFIG["api_key"] else None,
        "mock": USE_MOCK,
        "sdk_version": sdk_version,
        "sdk_supports_base_url": supports_base_url,
    }
