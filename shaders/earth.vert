#version 120
// Earth surface — passes eye-space position/normal + texture coords
// to the fragment shader for day/night/specular lighting.

varying vec3 v_eye_pos;
varying vec3 v_eye_normal;
varying vec2 v_uv;

void main() {
    vec4 eye = gl_ModelViewMatrix * gl_Vertex;
    v_eye_pos    = eye.xyz;
    v_eye_normal = normalize(gl_NormalMatrix * gl_Normal);
    v_uv         = gl_MultiTexCoord0.xy;
    gl_Position  = gl_ProjectionMatrix * eye;
}
