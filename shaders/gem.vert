#version 120
// Faceted crystal gem — pass eye-space and world-space attributes for
// reflection + fresnel + emissive core.

varying vec3 v_eye_pos;
varying vec3 v_eye_normal;
varying vec3 v_object_pos;     // for procedural inner glow

void main() {
    vec4 eye = gl_ModelViewMatrix * gl_Vertex;
    v_eye_pos     = eye.xyz;
    v_eye_normal  = normalize(gl_NormalMatrix * gl_Normal);
    v_object_pos  = gl_Vertex.xyz;
    gl_Position   = gl_ProjectionMatrix * eye;
}
