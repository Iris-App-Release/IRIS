#version 120
// Atmosphere shell — a slightly-larger sphere rendered with additive blending.
// Pass eye-space position/normal for fresnel + sun scattering in fragment.

varying vec3 v_eye_pos;
varying vec3 v_eye_normal;

void main() {
    vec4 eye      = gl_ModelViewMatrix * gl_Vertex;
    v_eye_pos     = eye.xyz;
    v_eye_normal  = normalize(gl_NormalMatrix * gl_Normal);
    gl_Position   = gl_ProjectionMatrix * eye;
}
