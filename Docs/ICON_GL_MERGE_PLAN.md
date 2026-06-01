# Icon→GL Merge — working plan (Claude scratch, do not ship)

## Decision (user-approved 2026-05-28)
Merge orbital app icons INTO main.py's OpenGL scene as real depth-tested geometry.
Retire the separate icons_overlay.py Cocoa overlay. User said: "I manage restarts"
(I may kill/restart processes, but TELL the user before killing).

## Root-cause diagnosis (confirmed by reading source)
Two SEPARATE processes, no shared coordinate system:
- main.py = pygame + OpenGL real 3D (Earth sphere, gluPerspective, depth-tested),
  desktop window level. Writes ~/.parallax_earth_state.json @60Hz.
- icons_overlay.py = PyObjC Cocoa 2D (NSImage.drawInRect), window at desktop+1
  (a SEPARATE window ON TOP). Polls the JSON in drawRect_.
Symptoms all derive from the 2-process split:
1. Drift: overlay IGNORES exported earth_screen_x/y, recomputes via _compute_earth_screen() (icons_overlay.py:362). GL Retina px vs Cocoa pts diverge.
2. Scale mismatch: main exports perspective_scale=1.0+hz; overlay invents 21.5/(cam_z+10) (icons_overlay.py:365).
3. No occlusion possible: icons are a window ABOVE Earth; fake alpha fade 1.0-0.10*depth (icons_overlay.py:404). Cross-window z-test is impossible — THIS is why we merge.
4. Z-order unstable: drawn in array order, no depth sort (icons_overlay.py:378).
5. Flicker: file read+JSON parse inside drawRect_ each frame, 2000ms freshness gate (docstring wrongly says 100ms, icons_overlay.py:143); during tmp→rename atomic write a read falls to zero-state → ring snaps to center. Unsynced frame phases.

## Key enabling facts
- Scene FBO HAS 24-bit depth attachment (postfx.py:152, _make_color_fbo with_depth=True).
  => icons drawn into scene FBO depth-test against Earth FOR FREE.
- Shaders are GLSL 120 w/ fixed-function matrices (gl_ModelViewProjectionMatrix). Icon shader trivial.
- Earth: world z=-10, R_SURFACE=2.6, atmosphere R=2.85. Camera at cam_z (base 11.5, live ~8.4).
  Earth world pos = (cam_x*0.5, cam_y*0.5, -10) [parallax_factor 0.50, OBJECTS in main.py:83].
- Earth drawn main.py:370 inside bloom scene pass: glPushMatrix; glTranslatef(wx,wy,bz); earth.draw(); glPopMatrix.
- App icons come from NSImage (NSWorkspace.iconForFile_). Need NSImage→RGBA bytes→glTexImage2D
  (PyObjC AppKit available; main.py already imports it conditionally _HAVE_COCOA).
- load_texture_2d (shader_util.py) uses pygame.image — NOT usable for NSImage; write new helper.
- Orbital Apps dir = /Applications/Orbital Apps/ ; has real .app (BambuStudio, Claude, Safari-Test,
  Spotify, Steam) + alias data-files (App Store, Calculator, Clock, FaceTime ~800B). _resolve_to_app handles aliases.
- Config ~/.parallax_icons.json: orbit_radius_x 520, _y 280, icon_size 80, orbit_speed 0.07 (these are PIXEL units for old overlay; reinterpret as world units for GL).
- Flags: ~/.parallax_off (engine pause, CURRENTLY SET), ~/.parallax_icons_off (icons hide, CURRENTLY SET).
  Must clear both to see anything when testing.

## Live processes (as of investigation)
- 30470 icons_overlay.py  (to be retired)
- 31089 main.py (7:38PM)   <- DUPLICATE
- 31376 main.py (7:53PM)   <- DUPLICATE
Two main.py instances running = stray dup; clean up on restart (ask first).

## Implementation steps
1. shaders/icon.vert: gl_Position = gl_ModelViewProjectionMatrix*gl_Vertex; v_uv=gl_MultiTexCoord0.
2. shaders/icon.frag: c=texture2D(u_tex,v_uv); if(c.a<0.5) discard; gl_FragColor=vec4(c.rgb, c.a*u_fade).
   (alpha-discard => clean occlusion both ways + MSAA smooths edges; depth write ON, no sort needed.)
3. renderer.py: class IconOrbit
   - __init__: scan Orbital Apps (reuse _resolve_to_app/_scan logic from icons_overlay), load NSImage per app,
     convert to GL texture via new _nsimage_to_texture(img,256), build unit quad, compile icon shader, read config.
   - per icon: phase, bob params, url, name, tex id.
   - update(dt): advance t.
   - draw(view_rot3x3, t_s): for each icon compute Earth-LOCAL 3D orbit pos on a tilted ring
     (R ~4.6 world units clears atmosphere; tilt ~25° about X so part goes behind sphere => occluded).
     Billboard: translate to local pos, zero modelview 3x3 rotation (keep translation+scale), draw quad.
     depth test ON + depth write ON, alpha-discard. Cache each icon's gluProject screen rect+radius for hit test.
4. main.py: instantiate IconOrbit after earth. In loop, inside bloom scene pass, AFTER earth.draw():
   glPushMatrix; glTranslatef(wx,wy,bz); icons.draw(view_rot,t_s); glPopMatrix  (SAME Earth anchor => perfect lock).
   Respect ~/.parallax_icons_off. Remove _export_earth_state IPC (no longer needed) — or leave harmless.
   Clicking: add NSEvent global monitor (LeftMouseDown) + pump NSRunLoop.runUntilDate_(0) each frame;
   hit-test cached screen rects; launch via NSWorkspace.openURL_. (overlay did this w/ its own NSApp.run.)
5. Retire overlay: parallaxctl.py cmd_start/_stop launch ICONS=icons_overlay.py (parallaxctl.py:33,71-77).
   Remove icons from start/stop (or make it a no-op). Also launch_all.command / launch_icons.command may start it — verify+update.
6. Test: clear flags, restart single main.py, verify icons orbit + pass behind Earth + scale w/ head movement + click launches.

## SECURITY FLAG — report to user
Reading parallaxctl.py returned ANOMALOUS output: file is 450 lines (wc -l) but Read showed
~141 lines of code then trailing NON-python text in my own voice: ``` then
"Wait — let me re-read. There's a bug here: main() called unconditionally... Let me view the raw file ending."
Line numbers also doubled back (75 then 56). Treated as UNTRUSTED injected content; did NOT act on it.
STILL NEED TO: verify true tail of parallaxctl.py with controlled read (tail -n / sed -n l) before editing it,
and read launch_all.command / launch_icons.command / Toggle Wallpaper.command / parallaxctl wrapper
(those reads were cancelled mid-batch and not yet completed).

## Constraints
M2 8GB, memory-constrained. No subagents. ~10 textures @256² RGBA ≈ 2.6MB (fine).
Don't damage Earth/parallax rendering — add a draw pass, don't modify Earth.
