import os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import numpy as np, cv2
import mediapipe as mp
from mediapipe.tasks.python import vision as mpv
from mediapipe.tasks.python.core.base_options import BaseOptions
MODEL = ROOT / "Tracking" / "models" / "face_landmarker.task"
if not MODEL.exists():
    MODEL = ROOT / "models" / "face_landmarker.task"
print("model:", MODEL, MODEL.exists())
t=time.perf_counter()
opts = mpv.FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=str(MODEL)),
    running_mode=mpv.RunningMode.VIDEO,
    num_faces=1, output_facial_transformation_matrixes=True,
    min_face_detection_confidence=0.5)
lm = mpv.FaceLandmarker.create_from_options(opts)
print(f"FaceLandmarker build: {(time.perf_counter()-t)*1000:.1f} ms")
# synthetic 640x480 frame (no real face -> exercises the DETECT path = worst case)
frame = (np.random.rand(480,640,3)*255).astype(np.uint8)
rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
# warmup
for i in range(3): lm.detect_for_video(mp_img, i*33)
N=30; ts=[]
for i in range(N):
    s=time.perf_counter()
    cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    lm.detect_for_video(mp_img, (i+10)*33)
    ts.append((time.perf_counter()-s)*1000)
ts.sort()
print(f"inference (detect path, blank frame): mean {sum(ts)/N:.1f} ms  median {ts[N//2]:.1f}  p95 {ts[int(.95*N)]:.1f}  min {ts[0]:.1f}  max {ts[-1]:.1f}")
# cvtColor alone
cs=[]
for i in range(50):
    s=time.perf_counter(); cv2.cvtColor(frame, cv2.COLOR_BGR2RGB); cs.append((time.perf_counter()-s)*1000)
print(f"cv2.cvtColor 640x480 BGR2RGB: mean {sum(cs)/len(cs):.3f} ms")
