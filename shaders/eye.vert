#version 120
// The Watcher — eyeball surface vertex shader.
//
// Passes eye-space position/normal + an analytic UV-sphere longitude tangent so
// the fragment shader can build a TBN frame for tangent-space normal mapping
// WITHOUT precomputed tangent attributes or fragment derivatives (maximally
// compatible with macOS OpenGL 2.1 / GLSL 1.20).

varying vec3 v_eye_pos;
varying vec3 v_eye_normal;
varying vec3 v_eye_tangent;
varying vec2 v_uv;

void main() {
    vec4 eye = gl_ModelViewMatrix * gl_Vertex;
    v_eye_pos    = eye.xyz;
    v_eye_normal = normalize(gl_NormalMatrix * gl_Normal);

    // UV-sphere longitude tangent (d/dtheta of the surface point) in object
    // space is proportional to (-z, 0, x). Guard the pole degeneracy.
    vec3 t_obj = vec3(-gl_Vertex.z, 0.0, gl_Vertex.x);
    if (length(t_obj) < 1e-4) t_obj = vec3(1.0, 0.0, 0.0);
    v_eye_tangent = normalize(gl_NormalMatrix * t_obj);

    v_uv        = gl_MultiTexCoord0.xy;
    gl_Position = gl_ProjectionMatrix * eye;
}
