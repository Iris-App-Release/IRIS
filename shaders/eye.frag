#version 120
// The Watcher — eyeball fragment shader.
//
// Single textured sphere: bloodshot sclera + synthetic Eye-of-Cthulhu iris
// (black pupil, green inner ring, blue outer ring), tangent-space normal
// mapping, wet-glass cornea specular, and a supernatural blue-green iris
// emission that gives the pupil a living-void depth rather than dead black.
//
// Outputs alpha = 0 — excluded from the bloom bright-pass (same anti-bloom
// convention as the orbital icons; keeps the wet glint a crisp catchlight).

uniform sampler2D u_diffuse;
uniform sampler2D u_normal;
uniform sampler2D u_specular;
uniform vec3      u_sun_eye;   // key-light direction in eye space (normalized)
uniform float     u_time;      // seconds — used for subtle iris pulse

varying vec3 v_eye_pos;
varying vec3 v_eye_normal;
varying vec3 v_eye_tangent;
varying vec2 v_uv;

void main() {
    vec3 albedo = texture2D(u_diffuse, v_uv).rgb;
    // alpha = 0 → excluded from the bloom bright pass (anti-bloom).
    gl_FragColor = vec4(albedo, 0.0);
}
