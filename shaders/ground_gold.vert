#version 120
/* ground_gold.vert — ground-plane ring + pathway (GLSL 120 / OpenGL 2.1)
   Passes world-space position to the fragment shader for distance-based shimmer. */

varying vec3 v_pos;

void main() {
    v_pos       = gl_Vertex.xyz;
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
