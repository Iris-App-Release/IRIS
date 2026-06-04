#!/usr/bin/env python3
"""
world_builder_cli.py — drive the REAL World Builder pipeline from the terminal.

This is the headed-app's authoring flow, minus the GUI. It calls the EXACT same
code the in-app **Send** button calls — `UI.world_builder_api.generate_world_objects`
→ `Worlds.placeable.sanitize_objects` — and mirrors the **Save** / **Delete World**
semantics from `UI/demo_overlay.py`. So running this is a faithful test of the live
feature: if a prompt works here, it works in the app (same model, same system
prompt, same clamps, same files). The `/world-builder-live` skill wraps this.

It NEVER touches the frozen camera/physics/shader core. The only outward call is
the Claude request inside `generate_world_objects`; everything it returns is
re-sanitized before it can reach disk.

Subcommands:
  status                       Readiness probe (SDK + API key + worlds list). No network.
  preview "<prompt>"           Generate (real Claude call) → write the grid_room
                               scratch + switch the active world to grid_room, so a
                               RUNNING app hot-reloads it into a live preview. (= Send)
  save "<prompt>" [--name N]   Generate → commit a NEW Worlds/<slug>/world.json that
                               joins the Worlds-tab cycle. (= Send then Save)
  list                         Show built-in vs user worlds + the active world.
  use <slug>                   Set the active world (~/.iris/preferences.json).
  delete <slug>                Delete a USER world dir (built-ins/path-escapes refused).
  clear                        Blank the grid_room scratch (empty preview).

Offline testing / manual authoring:
  preview/save also accept  --objects '<json-array>'  to inject a ready-made object
  list INSTEAD of calling Claude — used by the headless self-test and by the manual
  /world-builder skill to route hand-authored JSON through the same save path.

  Hidden:  --selftest          Exercise preview→save→delete on canned objects in a
                               temp Worlds dir (no network, no ~/.iris writes). Exit 0 = pass.

Run with the project venv:
  .venv/bin/python Scripts/world_builder_cli.py status
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# Repo root = this file's parent's parent (Scripts/ is a direct child of the root).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Worlds.placeable import sanitize_objects                      # noqa: E402
from UI.world_builder_api import generate_world_objects, diagnose  # noqa: E402

# Mirror UI/demo_overlay.py: worlds that ship with the app + the World Builder
# scratch. These are never offered for deletion and never collide as a save slug.
BUILTIN_WORLDS = {"earth", "gem", "the_watcher", "grid_room"}

CONFIG_DIR = Path.home() / ".iris"
PREFS_FILE = CONFIG_DIR / "preferences.json"


# ── paths (match demo_overlay._worlds_dir / _grid_room_path) ──────────────────
def worlds_dir(root: Path = ROOT) -> Path:
    wdir = root / "Worlds"
    return wdir if wdir.exists() else root / "worlds"


def grid_room_path(root: Path = ROOT) -> Path:
    return worlds_dir(root) / "grid_room" / "world.json"


def list_world_keys(root: Path = ROOT) -> list[str]:
    wd = worlds_dir(root)
    if not wd.exists():
        return []
    return sorted(p.name for p in wd.iterdir()
                  if p.is_dir() and (p / "world.json").exists())


def world_display_name(slug: str, root: Path = ROOT) -> str:
    try:
        d = json.loads((worlds_dir(root) / slug / "world.json").read_text())
        return d.get("name", slug)
    except Exception:
        return slug


# ── prefs (match demo_overlay._save_pref) ─────────────────────────────────────
def read_pref(key: str, default=None):
    try:
        return json.loads(PREFS_FILE.read_text()).get(key, default)
    except Exception:
        return default


def save_pref(key: str, value) -> None:
    try:
        CONFIG_DIR.mkdir(exist_ok=True)
        data = {}
        if PREFS_FILE.exists():
            try:
                data = json.loads(PREFS_FILE.read_text())
            except Exception:
                data = {}
        data[key] = value
        PREFS_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


# ── naming (match demo_overlay._derive_world_name / _unique_world_slug) ────────
def derive_world_name(prompt: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", prompt or "")[:5]
    if not words:
        return "My World"
    return " ".join(w.capitalize() for w in words)[:40]


def unique_world_slug(name: str, root: Path = ROOT) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_") or "world"
    existing = set(list_world_keys(root)) | BUILTIN_WORLDS
    slug, i = base, 2
    while slug in existing or (worlds_dir(root) / slug).exists():
        slug = f"{base}_{i}"
        i += 1
    return slug


# ── core ops ──────────────────────────────────────────────────────────────────
def _read_grid_room(root: Path = ROOT) -> dict:
    return json.loads(grid_room_path(root).read_text())


def _objects_from_args(prompt: str, inject: str | None, divisions: int) -> list[dict]:
    """Either inject a hand-supplied JSON array (offline) or do the real Claude call.

    Both paths end in sanitize_objects so the result is always clamped/allowlisted —
    identical to what the in-app Send button writes.
    """
    if inject is not None:
        try:
            raw = json.loads(inject)
        except Exception as e:
            print(f"error: --objects is not valid JSON: {e}", file=sys.stderr)
            return []
        return sanitize_objects(raw, divisions)
    return generate_world_objects(prompt, {"rendering": {
        "grid_divisions": divisions,
        "grid_depth": float(_read_grid_room().get("rendering", {}).get("grid_depth", 18.0)),
    }})


def cmd_status(_args) -> int:
    d = diagnose()
    print("World Builder readiness")
    print(f"  anthropic SDK installed : {d['sdk_installed']}")
    print(f"  API key present         : {d['key_present']}"
          + (f"  ({d['key_source']})" if d['key_source'] else ""))
    print(f"  model                   : {d['model']}")
    print(f"  READY for real-time     : {d['ready']}")
    if not d["ready"]:
        if not d["sdk_installed"]:
            print("\n  → install the SDK:  .venv/bin/python -m pip install anthropic")
        if not d["key_present"]:
            print("\n  → provide a key (any one):")
            print("      export ANTHROPIC_API_KEY=sk-ant-...           # terminal launch")
            print("      printf %s \"sk-ant-...\" > ~/.iris/anthropic_key  # .app + terminal")
    active = read_pref("world", "earth")
    keys = list_world_keys()
    user = [k for k in keys if k not in BUILTIN_WORLDS]
    print(f"\n  active world : {active}")
    print(f"  built-ins    : {[k for k in keys if k in BUILTIN_WORLDS]}")
    print(f"  user worlds  : {user or '(none yet)'}")
    return 0


def cmd_preview(args) -> int:
    """= the in-app Send button: generate → grid_room scratch → live preview."""
    prompt = (args.prompt or "").strip()
    if prompt is None or (not prompt and args.objects is None):
        print("error: describe your world (or pass --objects)", file=sys.stderr)
        return 2
    try:
        gr = _read_grid_room()
    except Exception as e:
        print(f"error: couldn't read grid_room world.json: {e}", file=sys.stderr)
        return 1
    divisions = int(gr.get("rendering", {}).get("grid_divisions", 8) or 8)

    if args.objects is None:
        d = diagnose()
        if not d["ready"]:
            print("error: World Builder not ready — run `status`. "
                  "(SDK installed: %s, key present: %s)"
                  % (d["sdk_installed"], d["key_present"]), file=sys.stderr)
            return 1
        print(f"Building your world… (model {d['model']})")

    objects = _objects_from_args(prompt, args.objects, divisions)
    if not objects:
        print("No objects generated — try rephrasing (or check `status`).",
              file=sys.stderr)
        return 1

    # Mirror demo_overlay._write_scratch: preserve grid_room config, swap objects.
    gr.setdefault("assets", {})["placeable_objects"] = objects
    grid_room_path().write_text(json.dumps(gr, indent=2))
    save_pref("world", "grid_room")   # switch the live scene to the preview
    print(f"Preview ready — {len(objects)} object(s) in grid_room "
          "(a running app hot-reloads it live).")
    print(json.dumps(objects, indent=2))
    return 0


def cmd_save(args) -> int:
    """= Send then Save: generate → commit a NEW Worlds/<slug>/world.json."""
    prompt = (args.prompt or "").strip()
    try:
        gr = _read_grid_room()
    except Exception as e:
        print(f"error: couldn't read grid_room world.json: {e}", file=sys.stderr)
        return 1
    divisions = int(gr.get("rendering", {}).get("grid_divisions", 8) or 8)

    if args.objects is None:
        d = diagnose()
        if not d["ready"]:
            print("error: World Builder not ready — run `status`.", file=sys.stderr)
            return 1
        if not prompt:
            print("error: describe your world (or pass --objects)", file=sys.stderr)
            return 2
        print(f"Building your world… (model {d['model']})")

    objects = _objects_from_args(prompt, args.objects, divisions)
    if not objects:
        print("No objects generated — nothing saved.", file=sys.stderr)
        return 1

    name = args.name or derive_world_name(prompt)
    slug = unique_world_slug(name)
    gr["name"] = name
    gr.setdefault("assets", {})["placeable_objects"] = objects
    wdir = worlds_dir() / slug
    wdir.mkdir(parents=True, exist_ok=True)
    (wdir / "world.json").write_text(json.dumps(gr, indent=2))
    # Reset the scratch (the app does this after Save).
    blank = _read_grid_room()
    blank.setdefault("assets", {})["placeable_objects"] = []
    grid_room_path().write_text(json.dumps(blank, indent=2))
    print(f"Saved “{name}” → Worlds/{slug}/  ({len(objects)} object(s)).")
    print(f"  view it:  .venv/bin/python {Path(__file__).name.replace('.py','')} "
          f"use {slug}   (or cycle to it on the Worlds tab)")
    return 0


def cmd_list(_args) -> int:
    keys = list_world_keys()
    active = read_pref("world", "earth")
    print("Worlds:")
    for k in keys:
        tag = "builtin" if k in BUILTIN_WORLDS else "user"
        star = " *" if k == active else ""
        print(f"  {k:28s} [{tag}]  “{world_display_name(k)}”{star}")
    print(f"\n  (* = active.  delete only works on [user] worlds.)")
    return 0


def cmd_use(args) -> int:
    if args.slug not in list_world_keys():
        print(f"error: no such world '{args.slug}'", file=sys.stderr)
        return 1
    save_pref("world", args.slug)
    print(f"Active world → {args.slug} (a running app switches live).")
    return 0


def cmd_delete(args) -> int:
    """Match demo_overlay._delete_world safety: refuse built-ins + path escapes."""
    slug = args.slug
    wd = worlds_dir()
    target = (wd / slug).resolve()
    if slug in BUILTIN_WORLDS or target.parent != wd.resolve() or not target.is_dir():
        print(f"error: '{slug}' can't be deleted (built-in, missing, or escapes Worlds/).",
              file=sys.stderr)
        return 1
    name = world_display_name(slug)
    shutil.rmtree(target)
    if read_pref("world") == slug:
        save_pref("world", "earth")
        print("  (was active — fell back to earth)")
    print(f"Deleted “{name}” (Worlds/{slug}/).")
    return 0


def cmd_clear(_args) -> int:
    try:
        gr = _read_grid_room()
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    gr.setdefault("assets", {})["placeable_objects"] = []
    grid_room_path().write_text(json.dumps(gr, indent=2))
    print("Cleared the grid_room scratch (empty preview).")
    return 0


def cmd_selftest(_args) -> int:
    """Offline end-to-end: preview→save→delete on canned objects in a temp tree.

    Proves the CLI's data-plane wiring (scratch write, new-world commit, delete
    safety) without any network or ~/.iris writes. The Claude call itself is
    covered by `status` + a live `preview`; here we inject objects via the same
    sanitize path the API output flows through.
    """
    import tempfile
    canned = [
        {"id": "a", "model": "builtin:sphere", "grid_position": [99, -99, 99],
         "scale": 9.0, "color": [2, -1, 0.5], "emissive": True, "rotation": [0, 45, 0]},
        {"id": "b", "model": "builtin:teapot", "grid_position": [0, 0, 0]},  # dropped
        {"id": "c", "model": "builtin:cube", "grid_position": [-2, 1, 4],
         "scale": 0.8, "color": [0.1, 0.2, 0.9], "emissive": True, "rotation": [0, 0, 0]},
    ]
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and cond
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        gr_dir = root / "Worlds" / "grid_room"
        gr_dir.mkdir(parents=True)
        base = {"name": "Grid Room", "rendering": {"grid_divisions": 8, "grid_depth": 18.0},
                "assets": {"placeable_objects": []}}
        (gr_dir / "world.json").write_text(json.dumps(base))
        # seed a couple of built-ins so list/slug logic has company
        for b in ("earth", "the_watcher"):
            (root / "Worlds" / b).mkdir(parents=True)
            (root / "Worlds" / b / "world.json").write_text('{"name":"%s"}' % b)

        divisions = 8
        objs = sanitize_objects(canned, divisions)
        check("sanitize drops the non-allowlisted model, clamps the wild one", len(objs) == 2)
        check("out-of-range cell clamped into the box",
              objs[0]["grid_position"] == (4.0, -4.0, 8.0))

        # preview = scratch write
        gr = json.loads((gr_dir / "world.json").read_text())
        gr.setdefault("assets", {})["placeable_objects"] = objs
        (gr_dir / "world.json").write_text(json.dumps(gr))
        reloaded = json.loads((gr_dir / "world.json").read_text())
        check("preview writes objects into grid_room scratch",
              len(reloaded["assets"]["placeable_objects"]) == 2)

        # save = new world dir (use the module fns against the temp root)
        name = derive_world_name("a glowing blue cube in the middle")
        slug = unique_world_slug(name, root)
        check("derived a non-empty display name", bool(name) and name != "My World")
        check("slug avoids built-ins/collisions", slug not in BUILTIN_WORLDS)
        nd = root / "Worlds" / slug
        nd.mkdir(parents=True)
        saved = dict(base); saved["name"] = name
        saved.setdefault("assets", {})["placeable_objects"] = objs
        (nd / "world.json").write_text(json.dumps(saved))
        check("save created the new world dir", (nd / "world.json").exists())
        check("saved world baked in the objects",
              len(json.loads((nd / 'world.json').read_text())['assets']['placeable_objects']) == 2)
        check("save baked NO change into a frozen field (grid_divisions intact)",
              json.loads((nd / 'world.json').read_text())['rendering']['grid_divisions'] == 8)

        # delete safety
        wd_resolved = (root / "Worlds").resolve()
        for bad in ("earth", "the_watcher", "..", "../evil"):
            t = (root / "Worlds" / bad).resolve()
            refused = bad in BUILTIN_WORLDS or t.parent != wd_resolved or not t.is_dir()
            check(f"delete refuses protected/escaping target '{bad}'", refused)
        # delete the user world for real
        shutil.rmtree(nd)
        check("delete removed the user world dir", not nd.exists())

    print(f"\nRESULT: {'all checks passed' if ok else 'a check FAILED'}")
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="world_builder_cli",
                                description="Drive the real IRIS World Builder pipeline.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", help="readiness probe (SDK + key + worlds)")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("preview", help="generate → live grid_room preview (= Send)")
    sp.add_argument("prompt", nargs="?", default="")
    sp.add_argument("--objects", default=None,
                    help="inject a JSON object array instead of calling Claude")
    sp.set_defaults(func=cmd_preview)

    sp = sub.add_parser("save", help="generate → commit a new world (= Send+Save)")
    sp.add_argument("prompt", nargs="?", default="")
    sp.add_argument("--name", default=None, help="override the derived world name")
    sp.add_argument("--objects", default=None,
                    help="inject a JSON object array instead of calling Claude")
    sp.set_defaults(func=cmd_save)

    sp = sub.add_parser("list", help="list worlds + the active one")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("use", help="set the active world")
    sp.add_argument("slug")
    sp.set_defaults(func=cmd_use)

    sp = sub.add_parser("delete", help="delete a user world")
    sp.add_argument("slug")
    sp.set_defaults(func=cmd_delete)

    sp = sub.add_parser("clear", help="blank the grid_room scratch")
    sp.set_defaults(func=cmd_clear)

    sp = sub.add_parser("selftest", help="offline data-plane self-test (no network)")
    sp.set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
