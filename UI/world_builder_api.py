"""
world_builder_api.py — Claude-assisted authoring for the World Builder.

Turns a natural-language description ("a glowing red sphere back-left, a pink
cube near the glass") into a list of validated, clamped ``placeable_objects``
dicts for the Grid Room (see obsidian-docs/architecture/grid-creator-tool-plan.md
§8). The Claude call is the only new outward-facing piece; EVERYTHING it returns
is run back through ``Worlds.placeable.sanitize_objects`` before it can reach a
draw call or disk, so a prompt can never break the box, escape the
``builtin:*`` allowlist, or touch a frozen field (grid_divisions / grid_depth /
camera / shaders). Reliability is the product — any failure returns ``[]``.

API key resolution (first hit wins), so the same code works whether IRIS is run
from a terminal (shell env) or as a Finder-launched .app (which does NOT inherit
shell env — the file fallback is what makes the shipped app work):
  1. ANTHROPIC_API_KEY env var
  2. IRIS_OPENAI_KEY env var (legacy alias)
  3. ~/.iris/anthropic_key            (raw key, one line)
  4. ~/.iris/config.json              ({"anthropic_api_key": "..."})

Model override: IRIS_WB_MODEL.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Persistent, per-device key store — mirrors the rest of the ~/.iris flag/pref
# files. Lets the Finder-launched .app find the key without a shell environment.
_IRIS_DIR      = Path.home() / ".iris"
_KEY_FILE      = _IRIS_DIR / "anthropic_key"
_CONFIG_FILE   = _IRIS_DIR / "config.json"


def _resolve_api_key() -> str | None:
    """Return the Anthropic API key from env or a ~/.iris file, or None.

    Total and crash-proof: any unreadable/malformed source is skipped silently so
    a bad file can never raise into the HUD — it just reads as "no key".
    """
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("IRIS_OPENAI_KEY")
    if key:
        return key.strip()
    try:
        if _KEY_FILE.exists():
            k = _KEY_FILE.read_text().strip()
            if k:
                return k
    except Exception:
        pass
    try:
        if _CONFIG_FILE.exists():
            data = json.loads(_CONFIG_FILE.read_text())
            k = (data or {}).get("anthropic_api_key") or (data or {}).get("ANTHROPIC_API_KEY")
            if isinstance(k, str) and k.strip():
                return k.strip()
    except Exception:
        pass
    return None


def diagnose() -> dict:
    """Readiness probe for tooling (e.g. the world-builder CLI / skill).

    Reports whether the two real-time gates are satisfied WITHOUT making a network
    call: the anthropic SDK import and a resolvable API key. Never raises.
    """
    try:
        import anthropic  # noqa: F401
        sdk = True
    except Exception:
        sdk = False
    key = _resolve_api_key()
    source = None
    if key:
        if os.environ.get("ANTHROPIC_API_KEY"):
            source = "env:ANTHROPIC_API_KEY"
        elif os.environ.get("IRIS_OPENAI_KEY"):
            source = "env:IRIS_OPENAI_KEY"
        elif _KEY_FILE.exists():
            source = f"file:{_KEY_FILE}"
        elif _CONFIG_FILE.exists():
            source = f"file:{_CONFIG_FILE}"
    return {
        "sdk_installed": sdk,
        "key_present": bool(key),
        "key_source": source,
        "model": DEFAULT_MODEL,
        "ready": bool(sdk and key),
    }

# sanitize_objects is the safety layer; import it robustly whether the repo root
# or UI/ is the import root (mirrors demo_overlay's UI.buttons fallback).
try:
    from Worlds.placeable import sanitize_objects
except ImportError:                                       # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from Worlds.placeable import sanitize_objects


# claude-sonnet-4-6 is fast + capable for this short structured-output call;
# override with IRIS_WB_MODEL if a different model is preferred.
DEFAULT_MODEL = os.environ.get("IRIS_WB_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = """\
You are the IRIS World Builder authoring assistant. The user describes a scene to \
place inside a fixed 3-D "Grid Room" — a wireframe shadow-box that the monitor \
looks into. You convert that description into placeable objects positioned on an \
integer grid.

OUTPUT CONTRACT (strict):
- Output ONLY a JSON array. No markdown, no code fences, no prose, no trailing text.
- Each element is exactly:
  {"id": "<short_snake_case>", "model": "builtin:cube" | "builtin:sphere" | \
"builtin:cylinder", "grid_position": [gx, gy, gz], "scale": <float>, \
"color": [r, g, b], "emissive": <bool>, "rotation": [rx, ry, rz]}

COORDINATE SYSTEM (integer grid cells; D = grid_divisions):
- gx: left -> right, range [-D/2 .. +D/2], 0 = centre. Negative = left, positive = right.
- gy: down -> up, range [-D/2 .. +D/2], 0 = centre. Negative = low/floor, positive = high.
- gz: depth, range [0 .. D]. 0 = right at the glass (closest to viewer), D = back wall (farthest).
- color components are 0.0-1.0 floats. scale is a float ~0.3-2.0 (1.0 = about one cell).
- emissive true means the object glows as a flat color in the void (recommended for the look).
- rotation is degrees [pitch, yaw, roll]; [0, 0, 0] is fine unless the user asks for a turn.

RULES:
- Use ONLY builtin:cube, builtin:sphere, builtin:cylinder. Never invent other models.
- Keep every grid_position inside range; clamp it yourself before output.
- Interpret spatial language: "back-left" -> gx negative, gz near D; "up front / near the
  glass" -> gz near 0; "floating high" -> gy positive; "on the floor" -> gy near -D/2;
  "centre / middle" -> 0.
- Pick colors that match the words ("glowing red" -> [1.0, 0.1, 0.1], emissive true).
- Output 1-8 objects unless the user clearly asks for more (hard max 64).
- NEVER include grid_divisions, grid_depth, camera, lighting, or any field other than the
  object fields above. Objects only."""


def _build_user_message(prompt: str, divisions: int, depth: float) -> str:
    half = divisions / 2.0
    return (
        "Grid Room context:\n"
        f"- grid_divisions (D) = {divisions}\n"
        f"- grid_depth = {depth}\n"
        f"- valid cells: gx,gy in [{-half:g} .. {half:g}], gz in [0 .. {divisions}]\n\n"
        "User description:\n"
        f'"""{prompt}"""\n\n'
        "Output the JSON array now."
    )


def _parse_json_objects(text: str):
    """Parse Claude's reply into a list, tolerating stray fences/prose.

    The system prompt forbids markdown, but we still defend against it: strip a
    ```json fence if present, else fall back to the outermost [...] slice. Always
    returns a list (possibly empty) — never raises.
    """
    if not text:
        return []
    s = text.strip()
    if s.startswith("```"):
        # ```json\n[...]\n```  ->  [...]
        parts = s.split("```")
        s = parts[1] if len(parts) > 1 else ""
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
        s = s.strip()
    try:
        data = json.loads(s)
    except Exception:
        start, end = s.find("["), s.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            data = json.loads(s[start:end + 1])
        except Exception:
            return []
    if isinstance(data, dict):
        data = data.get("placeable_objects", data.get("objects", []))
    return data if isinstance(data, list) else []


def generate_world_objects(prompt: str, world_def: dict) -> list[dict]:
    """Call Claude to generate placeable_objects from a natural-language prompt.

    Args:
        prompt: User description (e.g. "glowing red sphere back-left").
        world_def: Full world.json dict (for context: grid_divisions, grid_depth).

    Returns:
        List of validated, clamped placeable_objects dicts, or [] on any error
        (no key, SDK missing, network/parse failure). The list is always passed
        through ``sanitize_objects`` so the caller can write it verbatim.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return []

    rendering = (world_def or {}).get("rendering", {}) or {}
    try:
        divisions = int(rendering.get("grid_divisions", 8) or 8)
    except (TypeError, ValueError):
        divisions = 8
    try:
        depth = float(rendering.get("grid_depth", 18.0) or 18.0)
    except (TypeError, ValueError):
        depth = 18.0

    api_key = _resolve_api_key()
    if not api_key:
        return []

    try:
        import anthropic
    except ImportError:
        return []

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=1500,
            # Cache the (static) system prompt — every save reuses it, so the
            # repeated tokens are billed at the cache rate after the first call.
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": _build_user_message(prompt, divisions, depth),
            }],
        )
        text = "".join(
            block.text for block in resp.content
            if getattr(block, "type", None) == "text"
        )
    except Exception:
        return []

    raw = _parse_json_objects(text)
    # The safety gate: clamp to the box, allowlist the model, cap the count.
    return sanitize_objects(raw, divisions)
