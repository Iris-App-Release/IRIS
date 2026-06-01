#!/bin/bash
# Parallax Wall — DEPRECATED.
# The orbital app-icons are now rendered inside the OpenGL wallpaper daemon
# (renderer.IconOrbit, launched by launch.command). There is no separate
# overlay process anymore. This script is kept only so old aliases / Login
# Items that still point at it do nothing harmful.

echo "Orbital icons are now part of the wallpaper daemon (launch.command)."
echo "Use:  parallaxctl icons on     # show icons"
echo "      parallaxctl icons off    # hide icons"
echo "      parallaxctl start        # start the wallpaper daemon (with icons)"
exit 0
