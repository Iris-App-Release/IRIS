import time, sys
def t(label, fn):
    s=time.perf_counter(); fn(); return (label, (time.perf_counter()-s)*1000)
def imp(name):
    import importlib; importlib.import_module(name)
results=[]
# Measure cumulative wall-clock cost of each first-party + heavy dep, fresh process semantics
order=[("numpy",lambda:imp("numpy")),
       ("cv2",lambda:imp("cv2")),
       ("mediapipe",lambda:imp("mediapipe")),
       ("matplotlib.pyplot (already via mp?)",lambda:imp("matplotlib.pyplot")),
       ("sounddevice (already via mp?)",lambda:imp("sounddevice")),
       ("pygame",lambda:imp("pygame")),
       ("OpenGL.GL",lambda:imp("OpenGL.GL")),
       ("Engine.renderer",lambda:imp("Engine.renderer")),
       ("Engine.camera_math",lambda:imp("Engine.camera_math")),
       ("Worlds.world_runtime",lambda:imp("Worlds.world_runtime")),
       ("UI.demo_overlay",lambda:imp("UI.demo_overlay")),
       ("Tracking.face_tracker",lambda:imp("Tracking.face_tracker"))]
total0=time.perf_counter()
for label,fn in order:
    s=time.perf_counter(); fn(); dt=(time.perf_counter()-s)*1000
    print(f"{dt:8.1f} ms   {label}")
print("-"*40)
print(f"{(time.perf_counter()-total0)*1000:8.1f} ms   TOTAL (sequential, deps shared)")
# Is matplotlib already loaded right after mediapipe?
print()
print("matplotlib in sys.modules:", "matplotlib" in sys.modules)
print("sounddevice in sys.modules:", "sounddevice" in sys.modules)
