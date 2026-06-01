#version 120
// Cloud sphere — same vertex format as Earth but cloud-only sphere is
// rendered slightly larger and rotates independently (offset UV).

varying vec3 v_eye_normal;
varying vec3 v_eye_pos;
varying vec2 v_uv;

uniform float u_uv_offset;   // longitudinal scroll for slow cloud drift

void main() {
    vec4 eye = gl_ModelViewMatrix * gl_Vertex;
    v_eye_pos    = eye.xyz;
    v_eye_normal = normalize(gl_NormalMatrix * gl_Normal);
    v_uv         = vec2(gl_MultiTexCoord0.x + u_uv_offset, gl_MultiTexCoord0.y);
    gl_Position  = gl_ProjectionMatrix * eye;
}
