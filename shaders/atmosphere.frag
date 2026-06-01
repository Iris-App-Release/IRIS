#version 120
// Atmospheric scattering shell — renders the outer halo around Earth.
// Drawn additively. Brightest at the day-side limb, falling off into
// the night and away from the silhouette.

uniform vec3 u_sun_eye;
uniform float u_intensity;   // overall halo strength (~1.0)

varying vec3 v_eye_pos;
varying vec3 v_eye_normal;

void main() {
    vec3 N = normalize(v_eye_normal);
    vec3 V = normalize(-v_eye_pos);
    vec3 L = normalize(u_sun_eye);

    float ndotv = max(0.0, dot(N, V));
    float fres  = 1.0 - ndotv;

    // Thin limb band: a steep Fresnel concentrates the glow at the horizon, and
    // the (1 - smoothstep) term fades it back out right at the silhouette so the
    // shell's geometry edge is never visible — light scattering, not a shell.
    // A steeper power (5.5) + an earlier, wider outer fade (0.74→1.0) makes the
    // band thinner and lets it dissolve into space more gradually instead of
    // reading as a solid blue rim.
    float limb = pow(fres, 5.5) * (1.0 - smoothstep(0.74, 1.0, fres));

    // Day-side concentration: glow lives on the lit hemisphere, fading through
    // the terminator so the night limb stays dark (no full blue ring).
    float ndotl   = dot(N, L);
    float sun_lit = smoothstep(-0.35, 0.40, ndotl);

    // Forward Mie scatter — brightest looking toward the sun through the limb.
    float mie = pow(max(0.0, dot(V, L)), 8.0);

    // Rayleigh blue, warming to sunset orange right at the terminator.
    vec3  rayleigh = vec3(0.28, 0.50, 1.05);
    vec3  sunset   = vec3(1.05, 0.55, 0.30);
    float warm     = clamp(pow(max(0.0, ndotl), 3.0) * mie, 0.0, 1.0);
    vec3  atm      = mix(rayleigh, sunset, warm);

    // Additive glow (alpha = 1 → src.rgb adds onto the scene). All falloff is in
    // the colour so brightness is linear and easy to keep restrained. Weights and
    // the master multiplier are pulled down (1.7→1.05) so the halo is softer and
    // settles to roughly two-thirds of its former peak — present, not dominant.
    float glow = limb * (0.52 * sun_lit + 0.22 * mie);
    gl_FragColor = vec4(atm * glow * 1.05 * u_intensity, 1.0);
}
