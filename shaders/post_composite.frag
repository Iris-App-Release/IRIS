#version 120
// Final composite pass: scene + bloom + tonemap + vignette.
// Uses Reinhard tonemapping with slight gamma correction.

uniform sampler2D u_scene;
uniform sampler2D u_bloom;
uniform float     u_bloom_strength;   // ~0.85
uniform float     u_exposure;          // ~1.10
uniform float     u_vignette;          // 0..1, 0 = no vignette
uniform float     u_aberration;        // chromatic aberration amount (~0.003)

varying vec2 v_uv;

void main() {
    // Subtle chromatic aberration toward the edges (lens look)
    vec2 c_off = (v_uv - 0.5) * u_aberration;
    float r = texture2D(u_scene, v_uv + c_off).r;
    float g = texture2D(u_scene, v_uv).g;
    float b = texture2D(u_scene, v_uv - c_off).b;
    vec3 scene = vec3(r, g, b);

    vec3 bloom = texture2D(u_bloom, v_uv).rgb;

    vec3 hdr = scene + bloom * u_bloom_strength;

    // Exposure + Reinhard
    hdr *= u_exposure;
    vec3 mapped = hdr / (1.0 + hdr);

    // Gamma (output is sRGB-ish)
    mapped = pow(mapped, vec3(1.0 / 2.2));

    // Vignette
    float vig = 1.0 - u_vignette * smoothstep(0.45, 1.05, length(v_uv - 0.5) * 1.4);
    mapped *= vig;

    gl_FragColor = vec4(mapped, 1.0);
}
