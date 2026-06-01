#version 120
// Orbital app-icon billboard. Uses the fixed-function MVP so it shares the
// exact camera + projection as the Earth (the host sets the modelview to an
// Earth-anchored, rotation-zeroed billboard frame before drawing the quad).
varying vec2 v_uv;

void main() {
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
    v_uv        = gl_MultiTexCoord0.xy;
}
