#version 120
// Cloud layer — sample cloud texture luminance as alpha, modulated by
// sun illumination so clouds dim sharply on the night side.

uniform sampler2D u_clouds;
uniform vec3      u_sun_eye;

varying vec3 v_eye_normal;
varying vec3 v_eye_pos;
varying vec2 v_uv;

void main() {
    vec3 N = normalize(v_eye_normal);
    vec3 V = normalize(-v_eye_pos);
    vec3 L = normalize(u_sun_eye);

    float ndotl = max(0.0, dot(N, L));
    float day   = smoothstep(-0.05, 0.25, dot(N, L));

    // Cloud opacity from texture luminance
    float opacity = texture2D(u_clouds, v_uv).r;
    opacity = smoothstep(0.06, 0.95, opacity);

    // Fade clouds at the silhouette so they don't look pasted on
    float rim = pow(max(0.0, dot(N, V)), 0.5);
    float alpha = opacity * rim * (0.18 + 0.82 * day);

    // Sun side: bright white; night side: very faint blue tint
    vec3 day_color   = vec3(1.00, 0.99, 0.96) * (0.55 + 0.55 * ndotl);
    vec3 night_color = vec3(0.10, 0.13, 0.20);
    vec3 color = mix(night_color, day_color, day);

    gl_FragColor = vec4(color, alpha);
}
