#version 120
// Point-sprite star vertex shader. Each vertex carries position + colour.
// gl_PointSize is set per-vertex so we get a varied star size distribution.

attribute float a_size;
attribute float a_twinkle_seed;

varying vec3  v_color;
varying float v_twinkle;
varying float v_bright;        // intrinsic star brightness (drives spikes)

uniform float u_time;
uniform float u_size_scale;   // scales for HiDPI

void main() {
    gl_Position   = gl_ModelViewProjectionMatrix * gl_Vertex;
    gl_PointSize  = a_size * u_size_scale;
    v_color       = gl_Color.rgb;
    v_bright      = gl_Color.a;   // intrinsic brightness stored in vertex alpha
    // Per-star twinkle phase
    v_twinkle = 0.78 + 0.22 * sin(u_time * (1.6 + a_twinkle_seed * 2.7)
                                  + a_twinkle_seed * 6.28);
}
