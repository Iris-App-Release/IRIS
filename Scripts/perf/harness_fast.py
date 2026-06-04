# Same harness but with PyOpenGL's per-call error checking + pointer storing
# DISABLED before importing OpenGL. Quantifies the marshaling overhead.
import OpenGL
OpenGL.ERROR_CHECKING = False
OpenGL.STORE_POINTERS = False
OpenGL.ERROR_LOGGING = False
import runpy, sys
sys.argv = ["harness.py"] + sys.argv[1:]
runpy.run_path(__file__.replace("harness_fast.py", "harness.py"), run_name="__main__")
