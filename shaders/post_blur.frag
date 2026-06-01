#version 120
// Separable 9-tap Gaussian blur. Direction is passed as a uniform —
// run this shader twice per blur pass: once with (1/w, 0) then (0, 1/h).

uniform sampler2D u_tex;
uniform vec2 u_dir;        // (1/w, 0) or (0, 1/h)
uniform float u_radius;    // multiplied into u_dir to widen / tighten the blur

varying vec2 v_uv;

void main() {
    vec2 d = u_dir * u_radius;

    // Symmetric weights — Pascal-row-ish with a flatter centre
    float w0 = 0.227027;
    float w1 = 0.194594;
    float w2 = 0.121622;
    float w3 = 0.054054;
    float w4 = 0.016216;

    vec3 c = texture2D(u_tex, v_uv).rgb * w0;
    c += texture2D(u_tex, v_uv + d * 1.0).rgb * w1;
    c += texture2D(u_tex, v_uv - d * 1.0).rgb * w1;
    c += texture2D(u_tex, v_uv + d * 2.0).rgb * w2;
    c += texture2D(u_tex, v_uv - d * 2.0).rgb * w2;
    c += texture2D(u_tex, v_uv + d * 3.0).rgb * w3;
    c += texture2D(u_tex, v_uv - d * 3.0).rgb * w3;
    c += texture2D(u_tex, v_uv + d * 4.0).rgb * w4;
    c += texture2D(u_tex, v_uv - d * 4.0).rgb * w4;

    gl_FragColor = vec4(c, 1.0);
}
