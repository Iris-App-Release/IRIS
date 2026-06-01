# The Watcher — asset credits

## Textures

`eye_diffuse.png`, `eye_normal.png`, `eye_specular.png` are **fully synthetic** —
generated procedurally by `Scripts/tools/gen_eye_textures.py` with no external
photo source. They are original work, © this project, and carry no third-party
license obligations.

The iris (pupil + collarette ring + radial-fiber green/blue gradient + limbal ring),
sclera, vein network, artery trunks, hemorrhage blotches, normal map, and specular
mask are all computed from mathematical noise and geometry only.

## Removed photo dependency (2026-05-31)

An earlier version composited a Wikimedia Commons photograph (*Human eye close up,
anterior view* by Rapidreflex, CC BY-SA 4.0) for the iris. That photograph is
retained in `source/eye_anterior_cc-by-sa-4.0_rapidreflex.jpg` for reference but
is **no longer used** by the texture generator. The current Eye-of-Cthulhu style
iris is fully synthetic.
