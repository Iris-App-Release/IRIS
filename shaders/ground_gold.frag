#version 120
/* ground_gold.frag — gold shimmer for ring + pathway (GLSL 120 / OpenGL 2.1)
   Slow outward-radiating wave simulates light catching a polished stone surface.
   No texture samples; 2 float ops per fragment — negligible GPU cost. */

uniform float u_time;
uniform float u_alpha;
varying vec3  v_pos;

void main() {
    vec3  gold    = vec3(0.91, 0.72, 0.11);
    float dist    = length(v_pos.xz);
    /* Slow radial wave: period ≈ 4.5 s; amplitude ±15% around a 0.85 baseline.
       The dist term phases adjacent "stones" apart — they don't all peak at once. */
    float shimmer = 0.85 + 0.15 * sin(u_time * 1.4 - dist * 0.50);
    gl_FragColor  = vec4(gold * shimmer, u_alpha);
}
