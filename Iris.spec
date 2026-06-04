# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('assets', 'assets'), ('worlds', 'worlds'), ('shaders', 'shaders'), ('models', 'models')]
binaries = []
hiddenimports = ['UI.demo_overlay', 'UI.world_builder_api', 'Worlds.world_runtime', 'Worlds.world_loader', 'Worlds.placeable', 'mediapipe', 'mediapipe.python.solutions', 'mediapipe.tasks.python', 'mediapipe.tasks.python.vision', 'OpenGL', 'OpenGL.GL', 'OpenGL.GLU', 'pygame', 'cv2', 'objc', 'Foundation', 'AVFoundation']
tmp_ret = collect_all('mediapipe')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pygame')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# pyobjc: the camera-permission path (Tracking/face_tracker.py
# _request_camera_permission) imports AVFoundation/Foundation LAZILY inside a
# try/except, so PyInstaller's static analysis never sees them and its pyobjc
# hooks never run — only the compiled .so cores get pulled in transitively,
# WITHOUT each package's pure-Python __init__.py. That makes
# `from AVFoundation import AVCaptureDevice` raise ImportError in the frozen
# app, so _request_camera_permission() silently returns False, the TCC dialog
# never appears, and head tracking never starts. collect_all grabs the full
# packages (pure-Python modules + bridgesupport datas) so the import succeeds.
# objc (pyobjc-core) is the base; Foundation + AVFoundation are the frameworks
# the helper actually imports. Do NOT remove — without these the runtime
# permission request is inert even though the call-site code is correct.
for _pyobjc_pkg in ('objc', 'Foundation', 'AVFoundation'):
    tmp_ret = collect_all(_pyobjc_pkg)
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# World Builder Claude call. The anthropic SDK is imported LAZILY inside
# UI/world_builder_api.generate_world_objects (try/except ImportError → []), so
# PyInstaller's static analysis never sees it. Without collect_all the frozen app
# would silently fall back to "no objects generated" even with a valid API key.
# Optional dependency: guarded so a source tree without it still builds.
try:
    tmp_ret = collect_all('anthropic')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
except Exception:
    pass


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Iris',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon/Iris.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Iris',
)
app = BUNDLE(
    coll,
    name='Iris.app',
    icon='assets/icon/Iris.icns',
    # Stable bundle id so macOS TCC remembers the camera grant across rebuilds
    # (a missing/changing id makes the OS forget the grant → camera stays
    # unauthorized → Desktop Mode "freezes" with no head tracking).
    bundle_identifier='com.iris.parallaxwall',
    info_plist={
        # REQUIRED for the main-thread camera-permission prompt to appear. Without
        # this key macOS silently denies camera access, the tracker never opens
        # the device, and Desktop Mode renders but never responds to the head.
        'NSCameraUsageDescription':
            'Iris uses your camera to track head position for the spatial '
            'desktop illusion. No video is stored or transmitted.',
    },
)
