#version 120
// Star point sprites with soft circular falloff + bright core.

varying vec3  v_color;
varying float v_twinkle;
varying float v_bright;

void main() {
    // gl_PointCoord is 0..1 across the point sprite quad
    vec2 p = gl_PointCoord - vec2(0.5);
    float d = length(p) * 2.0;          // 0 at centre, 1 at rim
    if (d > 1.0) discard;

    // Crisp stellar core (diamond-like point) with only a faint surrounding
    // halo — most stars read as sharp astronomical points, not glowing spheres.
    float core = exp(-d * 14.0);
    float halo = exp(-d * 4.0) * 0.32;

    // Subtle diffraction spikes — a faint 4-point cross that only the brightest
    // stars show (scaled by brightness²), fading toward the rim. Reads as lens
    // diffraction in astrophotography, not an arcade sparkle.
    vec2  ap     = abs(p);
    float cross  = exp(-ap.x * 40.0) + exp(-ap.y * 40.0);
    float spikes = cross * (1.0 - d) * v_bright * v_bright * 0.45;

    float a = clamp(core + halo + spikes, 0.0, 1.0);

    vec3 c = v_color * v_twinkle;
    gl_FragColor = vec4(c, a);
}
