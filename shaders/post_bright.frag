#version 120
// Bright-pass extraction: isolate pixels brighter than the threshold,
// soft-knee so bloom doesn't pop on/off.

uniform sampler2D u_scene;
uniform float u_threshold;     // ~0.85
uniform float u_softness;      // ~0.5

varying vec2 v_uv;

void main() {
    vec4 s = texture2D(u_scene, v_uv);
    vec3 c = s.rgb;
    // Orbital icons write alpha = 0 into the scene buffer as an anti-bloom mask
    // (see IconOrbit.draw's glBlendFuncSeparate). Earth, stars, nebula and the
    // cleared background all keep alpha >= ~1, so ONLY icon-body pixels are
    // pulled out of the bright pass. Icons then render opaque and crisp instead
    // of glowing, while the Earth/star bloom is left completely unchanged.
    float bloom_mask = step(0.004, s.a);
    float lum = dot(c, vec3(0.2126, 0.7152, 0.0722));
    // Soft knee around threshold
    float k = clamp((lum - u_threshold) / max(u_softness, 0.001), 0.0, 1.0);
    k = k * k * (3.0 - 2.0 * k);
    gl_FragColor = vec4(c * k * bloom_mask, 1.0);
}
