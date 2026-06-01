#version 120
// Crystal gem fragment shader — hot-pink brilliant-cut gemstone.
//
// • Base   : saturated hot-pink diffuse
// • Spec   : sharp diamond-flash highlights from key + fill lights
// • Fresnel: blazing pink rim at grazing angles
// • Core   : pulsing pink emissive gradient toward the gem centre
// • Irid   : subtle blue-violet iridescence shift with view angle

uniform vec3  u_sun_eye;
uniform vec3  u_fill_eye;       // secondary fill light in eye space
uniform float u_time;           // seconds, for emissive pulse

varying vec3 v_eye_pos;
varying vec3 v_eye_normal;
varying vec3 v_object_pos;

void main() {
    vec3 N = normalize(v_eye_normal);
    vec3 V = normalize(-v_eye_pos);
    vec3 L = normalize(u_sun_eye);
    vec3 F = normalize(u_fill_eye);

    // ── Diffuse base (hot pink) ───────────────────────────────────────────────
    // Hot pink: strong red, very low green, mid magenta
    vec3 base  = vec3(1.00, 0.06, 0.48);
    float ndotl = max(0.0, dot(N, L));
    float ndotf = max(0.0, dot(N, F));
    // Low ambient so the unlit back-facets read as deep shadow (depth contrast)
    vec3 diffuse = base * (0.06 + 0.70 * ndotl + 0.28 * ndotf);

    // ── Sharp specular highlights (diamond-flash) ─────────────────────────────
    // Very high shininess = narrow, intense sparkle per facet as gem rotates.
    vec3 H1 = normalize(L + V);
    vec3 H2 = normalize(F + V);
    float s1 = pow(max(0.0, dot(N, H1)), 256.0);
    float s2 = pow(max(0.0, dot(N, H2)), 128.0);
    // Key spec: near-white with a hot-pink blush; fill: cooler blue-white tint
    vec3 spec = vec3(1.0, 0.80, 0.90) * s1 * 2.2
              + vec3(0.70, 0.60, 1.00) * s2 * 1.2;

    // ── Fresnel rim ───────────────────────────────────────────────────────────
    // Tight power for a vivid, saturated rim glow at silhouette edges
    float fres = pow(1.0 - max(0.0, dot(N, V)), 4.5);
    vec3 rim   = vec3(1.30, 0.15, 0.70) * fres;

    // ── Emissive inner glow (hot-pink core) ───────────────────────────────────
    float r     = length(v_object_pos);
    float core  = exp(-pow(r * 1.10, 2.0));
    float pulse = 0.82 + 0.18 * sin(u_time * 1.4);
    // Gradient: intense hot pink at centre, bleeds to a cooler pink-white at edge
    vec3 emissive = mix(vec3(1.0, 0.12, 0.55),
                        vec3(0.95, 0.50, 0.75),
                        smoothstep(0.0, 1.4, r)) * core * pulse * 1.3;

    // ── Iridescence: blue-violet hue shift at glancing view angles ────────────
    float irid_t = max(0.0, dot(N, V));
    vec3 irid = mix(vec3(0.35, 0.05, 0.80),
                    vec3(0.90, 0.75, 1.00),
                    irid_t) * fres * 0.35;

    vec3 color = diffuse + spec + rim + emissive + irid;
    gl_FragColor = vec4(color, 1.0);
}
