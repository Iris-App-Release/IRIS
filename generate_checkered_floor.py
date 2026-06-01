#!/usr/bin/env python3
"""Generate a seamless white/pink checkered floor texture.
The resulting image is saved as `floor_checkered.png` in the project's assets folder.
"""
import numpy as np
from PIL import Image

# Parameters
size = 1024  # texture resolution
checker_size = 64  # size of each square in pixels

# Create a checkerboard pattern: 0 = white, 1 = pink
grid = np.indices((size, size)).sum(axis=0) // checker_size % 2
colors = np.array([[255, 255, 255], [255, 182, 193]], dtype=np.uint8)  # white and pink
texture = colors[grid]
img = Image.fromarray(texture, mode='RGB')
img.save('floor_checkered.png')
print('Generated floor texture: floor_checkered.png')
