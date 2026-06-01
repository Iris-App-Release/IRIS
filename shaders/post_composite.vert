#version 120
// Full-screen quad — used for every post-processing pass.
// We rely on gl_MultiTexCoord0 already being set by the host program.

varying vec2 v_uv;

void main() {
    v_uv        = gl_MultiTexCoord0.xy;
    gl_Position = vec4(gl_Vertex.xy, 0.0, 1.0);
}
