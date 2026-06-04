"""Measure RSS for the LAZY load path: only the assets each world needs."""
import os, sys, time, json, tempfile
from pathlib import Path
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT","1")
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import psutil
proc = psutil.Process()
def rss(): return proc.memory_info().rss/1048576.0
def mark(label, base):
    now=rss(); delta=now-base; print(f"{delta:+8.1f} MB   (RSS {now:7.1f})   {label}"); return now

# Set ERROR_CHECKING=False as app_engine now does
import OpenGL as _ogl; _ogl.ERROR_CHECKING=False; _ogl.ERROR_LOGGING=False

b0=rss(); print(f"{'baseline':>40}   RSS {b0:7.1f} MB")
import numpy as np; b=mark("import numpy", b0)
import pygame; b=mark("import pygame", b)
from pygame.locals import DOUBLEBUF,OPENGL,HIDDEN
import OpenGL.GL as _gl; b=mark("import OpenGL", b)
import cv2; b=mark("import cv2", b)
# mediapipe is now deferred — import only face_tracker (which no longer imports mp)
import Tracking.face_tracker; b=mark("import face_tracker (no mediapipe)", b)
pygame.init()
pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION,2)
pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION,1)
pygame.display.set_mode((2940,1912),DOUBLEBUF|OPENGL|HIDDEN)
from OpenGL.GL import *; b=mark("GL context @2940x1912", b)
from Engine.renderer import IconOrbit, GridRoom
b=mark("import Engine.renderer", b)
icons=IconOrbit(debug=False); b=mark("IconOrbit() [eager, multi-world]", b)
room=GridRoom();               b=mark("GridRoom() [lazy world asset]", b)
print(f"\n{'TOTAL RESIDENT (grid_room world, lazy)':>40}   RSS {rss():7.1f} MB")
print(f"\nSavings vs baseline: {1133.2 - rss():.0f} MB (baseline was 1133 MB)")
