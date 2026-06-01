#version 120
// Photorealistic Earth fragment shader.
//
// Day side  : sample day texture, modulate by Lambert (N·L) + ambient
// Night side: sample night texture (city lights), boosted, mixed via 1-N·L
// Oceans    : Phong specular highlight only where specular mask is bright
// Atmosphere: blue fresnel rim, brightest where the sun is grazing-incident

uniform sampler2D u_day;
uniform sampler2D u_night;
uniform sampler2D u_specular;
uniform vec3      u_sun_eye;   // sun direction in eye space (normalized)

varying vec3 v_eye_pos;
varying vec3 v_eye_normal;
varying vec2 v_uv;

void main() {
    vec3 N = normalize(v_eye_normal);
    vec3 V = normalize(-v_eye_pos);
    vec3 L = normalize(u_sun_eye);

    float ndotl = dot(N, L);

    // Smooth twilight transition centred on the terminator
    float day_factor = smoothstep(-0.18, 0.22, ndotl);
    float night_factor = 1.0 - day_factor;

    vec3 day_color   = texture2D(u_day,   v_uv).rgb;
    vec3 night_color = texture2D(u_night, v_uv).rgb;

    // Day side: gentle ambient + Lambert
    vec3 lit_day = day_color * (0.10 + 0.95 * max(0.0, ndotl));

    // Night side: city lights, brightened
    vec3 city = night_color * 1.6;

    // Mix
    vec3 surface = mix(city * night_factor, lit_day, day_factor);

    // ── Ocean: rough, deep water — not plastic ────────────────────────────────
    // spec_mask.r ≈ 1 over water, 0 over land. The old single hard Phong
    // highlight (bright cyan, no Fresnel) read as wet plastic / chrome. Replace
    // it with a Fresnel-gated, dual-lobe, roughness-varied sun glint plus a
    // subtle deep-water body so the sea reads as deep, naturally reflective.
    float ocean = texture2D(u_specular, v_uv).r;
    vec3  H     = normalize(L + V);
    float ndoth = max(0.0, dot(N, H));
    float ndotv = max(0.0, dot(N, V));

    // Schlick Fresnel (water F0≈0.02): matte head-on, reflective toward grazing.
    float fres  = 0.02 + 0.98 * pow(1.0 - ndotv, 5.0);

    // Low-frequency roughness variation (alias-safe — no sparkle/jitter) so the
    // sea catches light unevenly across regions instead of as a uniform sheet.
    float rough = 0.5 + 0.5 * sin(v_uv.x * 18.0) * sin(v_uv.y * 12.0);

    // Two lobes: a broad rough sheen + a soft sun glint (never a chrome dot).
    float broad = pow(ndoth, 14.0) * 0.22;
    float tight = pow(ndoth, mix(70.0, 150.0, rough)) * 0.60;
    float glint = (broad + tight) * ocean * fres * max(0.0, ndotl);
    surface += vec3(1.00, 0.96, 0.86) * glint * 1.25;

    // Deep-water body: slightly cooler + darker on the lit side so oceans show
    // real light rolloff instead of flat synthetic blue. Land (ocean≈0) is
    // untouched, preserving continental contrast.
    surface = mix(surface, surface * vec3(0.86, 0.92, 1.04),
                  ocean * 0.16 * max(0.0, ndotl));

    // Atmospheric rim — adds a faint blue halo near the limb
    float rim = pow(1.0 - max(0.0, dot(N, V)), 2.4);
    float sun_glow = pow(max(0.0, ndotl), 0.6);
    surface += vec3(0.18, 0.42, 0.85) * rim * sun_glow * 0.55;

    // Desaturate — real Earth from space is vivid but not plastic-vivid
    float luma = dot(surface, vec3(0.299, 0.587, 0.114));
    surface = mix(vec3(luma), surface, 0.60);

    gl_FragColor = vec4(surface, 1.0);
}
