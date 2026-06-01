#version 120
// Transparent icon corners are DISCARDED (not just blended) so they never write
// the depth buffer. Combined with depth-test + depth-write ON this gives correct
// two-way occlusion against the Earth with no per-icon sorting:
//   • icon behind Earth  -> its fragments fail the depth test -> hidden.
//   • icon in front       -> it writes depth + colour over the Earth.
uniform sampler2D u_tex;
uniform float     u_fade;     // global multiplier (fade-in / debug dim), 1.0 = normal
uniform float     u_alpha_cut;
varying vec2      v_uv;

void main() {
    vec4 c = texture2D(u_tex, v_uv);
    if (c.a < u_alpha_cut) discard;
    gl_FragColor = vec4(c.rgb, c.a * u_fade);
}
