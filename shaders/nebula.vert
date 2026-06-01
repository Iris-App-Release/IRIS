#version 120
// Background nebula sphere — drawn from inside.  Passes only UV.

varying vec2 v_uv;
varying vec3 v_dir;

void main() {
    v_dir       = normalize(gl_Vertex.xyz);
    v_uv        = gl_MultiTexCoord0.xy;
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
