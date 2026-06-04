import os, sys, time
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT","1")
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import psutil
proc = psutil.Process()
def rss(): return proc.memory_info().rss/1048576.0
def mark(label, base):
    now=rss(); print(f"{now-base:+8.1f} MB   (RSS {now:7.1f})   {label}"); return now

b0=rss(); print(f"{'baseline':>40}   RSS {b0:7.1f} MB")
import numpy as np; b=mark("import numpy", b0)
import pygame; b=mark("import pygame", b)
from pygame.locals import DOUBLEBUF, OPENGL, HIDDEN
import OpenGL.GL as gl; b=mark("import OpenGL", b)
import cv2; b=mark("import cv2", b)
import mediapipe; b=mark("import mediapipe (+matplotlib+sounddevice)", b)

pygame.init()
pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION,2)
pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION,1)
pygame.display.set_mode((2940,1912), DOUBLEBUF|OPENGL|HIDDEN)
from OpenGL.GL import *
glViewport(0,0,2940,1912)
b=mark("GL context @2940x1912", b)

from Engine.renderer import Earth, Stars, Nebula, IconOrbit, Gem, GridRoom
b=mark("import Engine.renderer", b)
neb=Nebula(); b=mark("Nebula() [4096x2048 bg]", b)
st=Stars();   b=mark("Stars() [4600 pts]", b)
ea=Earth();   b=mark("Earth() [4x 8192x4096 textures]", b)
ic=IconOrbit(debug=False); b=mark("IconOrbit() [10 app icons]", b)
gem=Gem();    b=mark("Gem()", b)
room=GridRoom(); b=mark("GridRoom()", b)
print(f"\n{'TOTAL RESIDENT':>40}   RSS {rss():7.1f} MB")
pygame.quit()
