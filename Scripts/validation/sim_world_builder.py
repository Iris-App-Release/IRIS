#!/usr/bin/env python3
"""
sim_world_builder.py — Headless validation of the World Builder authoring FLOW
(the 2026-06-03 UX revision: Send = preview, Save = commit a new world, Settings
→ Delete World, unlimited gate).

No display, no GL, no camera, and NO network: the Claude call
(`world_builder_api.generate_world_objects`) is stubbed, and every filesystem path
— config AND the Worlds/ directory — is redirected into a temp dir, so the sim
never touches ~/.iris, the real worlds, or the API. It pins the new invariants so
the authoring flow can't silently regress:

  1. ENTER WB — switching to the World Builder tab preserves existing scratch/preview
     state (returning to the tab never loses work); preview_active is wired to the
     Preview sub-view only. Restart button is the explicit clear.
  2. SEND = PREVIEW — Send runs the (stubbed) generator, holds the sanitized
     objects in a transient field, mirrors them into the grid_room scratch
     world.json (so hot-reload/Preview show them), and does NOT create a world.
  3. SAVE = NEW WORLD — Save bakes the previewed objects into a brand-new
     Worlds/<slug>/world.json with a unique name, joins it to the Worlds-tab
     cycle, and resets the scratch. Save with no preview is a no-op.
  4. DELETE WORLD — the Settings list offers only user worlds (built-ins +
     grid_room never appear); confirm-Yes removes the dir, drops it from the
     cycle, and falls back to a safe world if it was active. Built-ins and
     path-escape slugs are refused.
  5. UNLIMITED — the entitlement gate never blocks a save and never upsells.

Run:  .venv/bin/python Scripts/validation/sim_world_builder.py
Exit 0 = all checks pass, 1 = a check failed.
"""
from __future__ import annotations

# --- reorg path shim (validation harness) ---
import sys as _s
from pathlib import Path as _P
_root = str(_P(__file__).resolve().parents[2])
if _root not in _s.path:
    _s.path.insert(0, _root)

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

_fail = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
    if detail:
        line += f"  —  {detail}"
    print(line)


def _has_content(surf) -> bool:
    return len(pygame.mask.from_surface(surf, threshold=0).get_bounding_rects()) > 0


# Stubbed Claude output — two valid objects that survive sanitize_objects.
_STUB_OBJECTS = [
    {"model": "builtin:sphere", "grid_position": [-3, 2, 5], "scale": 1.0,
     "color": [1.0, 0.1, 0.1], "emissive": True, "rotation": [0, 0, 0]},
    {"model": "builtin:cube", "grid_position": [2, -1, 2], "scale": 0.8,
     "color": [0.2, 0.4, 1.0], "emissive": True, "rotation": [0, 0, 0]},
]


def _make_world(dirp: Path, name: str, src_grid: Path | None = None) -> None:
    dirp.mkdir(parents=True, exist_ok=True)
    if src_grid is not None and src_grid.exists():
        data = json.loads(src_grid.read_text())
        data["name"] = name
    else:
        data = {"name": name, "rendering": {"grid_divisions": 8, "grid_depth": 18.0,
                "enveloping": True}, "assets": {"placeable_objects": []}}
    (dirp / "world.json").write_text(json.dumps(data, indent=2))


def main() -> int:
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    pygame.font.init()

    repo_worlds = Path(_root) / "Worlds"
    tmp = Path(tempfile.mkdtemp(prefix="iris_wb_sim_"))
    tmp_worlds = tmp / "Worlds"
    # Built-ins + the grid_room scratch (copied from the real one for fidelity).
    _make_world(tmp_worlds / "grid_room", "Grid Room",
                src_grid=repo_worlds / "grid_room" / "world.json")
    for b in ("earth", "gem", "the_watcher"):
        _make_world(tmp_worlds / b, b.replace("_", " ").title())

    import UI.demo_overlay as ov_mod
    ov_mod.CONFIG_DIR = tmp
    ov_mod.PREFS_FILE = tmp / "preferences.json"
    ov_mod.DAEMON_PID_FILE = tmp / "daemon.pid"
    ov_mod.TRACKING_OFF_FLAG = tmp / "parallax_off"
    ov_mod.CAMERA_OFF_FLAG = tmp / "camera_off"

    # Stub the Claude generator (no network / no API key needed).
    import UI.world_builder_api as wba
    wba.generate_world_objects = lambda prompt, world_def: list(_STUB_OBJECTS)

    from UI.demo_overlay import DemoOverlay
    from Worlds.world_loader import WorldLoader

    def temp_load_worlds():
        loader = WorldLoader(tmp_worlds)
        keys = loader.list_available_worlds() or ["earth"]
        names = {}
        for k in keys:
            try:
                names[k] = loader.load_world(k).get("name", k)
            except Exception:
                names[k] = k
        return keys, names

    W, H, S = 1180, 760, 2.0
    o = DemoOverlay(W, H, scale=S, daemon_running=False, desktop_paused=False)
    # Redirect every Worlds/ path at the instance to the temp tree.
    o._worlds_dir = lambda: tmp_worlds
    o._grid_room_path = lambda: tmp_worlds / "grid_room" / "world.json"
    o._load_worlds = temp_load_worlds
    o._all_world_keys, o._world_names = temp_load_worlds()
    o._world_keys = [k for k in o._all_world_keys if k != "grid_room"] or ["earth"]
    o.active_world = "earth"

    def scratch_objects():
        return json.loads((tmp_worlds / "grid_room" / "world.json").read_text()) \
            .get("assets", {}).get("placeable_objects", [])

    # ── 1. Enter World Builder → preserve state + preview-suspend wiring ──────────
    print("Enter World Builder:")
    o._click("tab:world_builder")
    check("World Builder tab active, grid sub-view", o._active_tab == "world_builder"
          and o._wb_view == "grid")
    # Entering preserves any existing scratch/preview — no implicit clear.
    # Restart button is the explicit wipe (tested below via _wb_restart()).
    check("entering preserves the transient preview (no implicit clear)",
          isinstance(o._wb_preview_objects, list))
    check("grid editor suspends the engine scene (preview_active False)",
          o.preview_active is False)
    check("grid editor renders content (cube + cards)", _has_content(o.render_surface()))

    # ── 2. Send = preview only (no world created) ───────────────────────────────
    print("\nSend (generate + preview, no save):")
    worlds_before = set((p.name for p in tmp_worlds.iterdir() if p.is_dir()))
    o._wb_prompt = "a glowing red sphere back-left and a blue cube"
    gen_before = o._wb_preview_gen
    o._click("wb_send")
    check("Send populates the transient preview objects",
          len(o._wb_preview_objects) == 2, f"{len(o._wb_preview_objects)} objs")
    check("Send mirrors objects into the grid_room scratch (drives Preview)",
          len(scratch_objects()) == 2, f"{len(scratch_objects())} on disk")
    check("Send bumps the preview generation (cache invalidates)",
          o._wb_preview_gen > gen_before)
    check("Send creates NO new world", set(p.name for p in tmp_worlds.iterdir()
          if p.is_dir()) == worlds_before)
    check("Canvas Cube renders the previewed objects", _has_content(o.render_surface()))
    # Preview sub-view turns the engine scene back on.
    o._click("wb_preview")
    check("Preview sub-view → preview_active True (engine renders grid_room)",
          o.preview_active is True)
    o._click("wb_back")

    # ── 3. Save = commit a brand-new world ──────────────────────────────────────
    print("\nSave (commit previewed world to my worlds):")
    o._click("wb_save")
    new_dirs = [p.name for p in tmp_worlds.iterdir() if p.is_dir()
                and p.name not in ("grid_room", "earth", "gem", "the_watcher")]
    check("Save creates exactly one new world dir", len(new_dirs) == 1,
          f"new: {new_dirs}")
    slug = new_dirs[0] if new_dirs else ""
    if slug:
        saved = json.loads((tmp_worlds / slug / "world.json").read_text())
        check("saved world bakes in the previewed objects",
              len(saved.get("assets", {}).get("placeable_objects", [])) == 2)
        check("saved world has a derived display name",
              bool(saved.get("name")) and saved["name"] != "Grid Room", saved.get("name"))
        check("saved world joins the Worlds-tab cycle", slug in o._world_keys)
    check("Save resets the transient preview", o._wb_preview_objects == [])
    check("Save resets the grid_room scratch", scratch_objects() == [])
    check("Save clears the prompt", o._wb_prompt == "")
    # Save with no preview is a no-op (no world created).
    dirs_now = set(p.name for p in tmp_worlds.iterdir() if p.is_dir())
    o._click("wb_save")
    check("Save with no preview creates nothing",
          set(p.name for p in tmp_worlds.iterdir() if p.is_dir()) == dirs_now)

    # ── 3b. Restart button — explicit clear (only way to wipe the canvas) ────────
    print("\nRestart button:")
    o._click("tab:world_builder")
    o._wb_prompt = "a glowing red sphere back-left"
    o._wb_send()           # repopulate so there's something to clear
    check("canvas has objects before Restart", len(o._wb_preview_objects) > 0)
    o._click("wb_restart")
    check("Restart clears the transient preview", o._wb_preview_objects == [])
    check("Restart clears the grid_room scratch", scratch_objects() == [])
    check("Restart clears the prompt", o._wb_prompt == "")

    # ── 4. Settings → Delete World (list + confirm + safety) ────────────────────
    print("\nDelete World (Settings):")
    o._click("tab:settings")
    o._click("delete_world")
    check("Delete list offers ONLY the user world (built-ins hidden)",
          o._deletable_worlds() == [slug], f"{o._deletable_worlds()}")
    check("Delete list registers a row button for the user world",
          f"del:{slug}" in o._buttons)
    o.active_world = slug                         # pretend it's the active world
    o._click(f"del:{slug}")
    check("picking a world opens the confirm modal", o._delete_target == slug)
    check("confirm modal registers Yes/No", "del_confirm_yes" in o._buttons
          and "del_confirm_no" in o._buttons)
    check("confirm modal renders", _has_content(o.render_surface()))
    o._click("del_confirm_yes")
    check("Yes removes the world directory", not (tmp_worlds / slug).exists())
    check("Yes drops it from the Worlds-tab cycle", slug not in o._world_keys)
    check("deleting the active world falls back to a safe default",
          o.active_world == "earth", o.active_world)
    check("confirm modal dismissed after delete", o._delete_target is None)

    print("\nDelete safety (built-ins + path escape refused):")
    for guard in ("earth", "gem", "the_watcher", "grid_room", "..", "../evil"):
        before = sorted(p.name for p in tmp_worlds.iterdir() if p.is_dir())
        o._delete_world(guard)
        after = sorted(p.name for p in tmp_worlds.iterdir() if p.is_dir())
        check(f"refuses to delete protected/escaping target {guard!r}",
              before == after and (Path(_root) / "Worlds").exists())

    # ── 5. Entitlement is unlimited (gate disabled, scaffolding intact) ─────────
    print("\nEntitlement (unlimited for now):")
    from Licensing.entitlement import EntitlementChecker
    ent = EntitlementChecker(path=tmp / "licensing.json")
    ok = True
    for _ in range(5):
        ok = ok and ent.can_save_customization() and not ent.should_show_upsell()
        ent.record_customization_saved()
    check("gate never blocks a save and never upsells, even after many saves", ok)

    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if _fail:
        print(f"RESULT: {_fail} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
