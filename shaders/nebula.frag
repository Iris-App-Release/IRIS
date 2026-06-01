#version 120
// Milky Way background with colour grading + subtle nebula tinting.
// Sampled from inside the sphere — UVs are already correct for that.

uniform sampler2D u_nebula;
uniform float u_brightness;     // ~0.6 default
uniform float u_time;            // for very subtle twinkle modulation

varying vec2 v_uv;
varying vec3 v_dir;

// Hash for cheap noise
float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void main() {
    vec3 base = texture2D(u_nebula, v_uv).rgb;

    // Slight colour grade — push toward blue-violet, deepen blacks. The crush is
    // now gentle (1.08) so the generated backdrop's nebula + Milky-Way band
    // survive instead of being flattened to black (the old 1.25 was tuned to
    // hide JPEG noise in a near-black astrophoto).
    vec3 grade = vec3(
        base.r * 0.94,
        base.g * 0.97,
        base.b * 1.08 + 0.010
    );
    grade = pow(grade, vec3(1.08));   // gently deepen blacks
    grade *= u_brightness;

    // Add a faint per-pixel twinkle on the brightest stars
    float lum  = dot(grade, vec3(0.30, 0.59, 0.11));
    float spark = step(0.42, lum) *
                  (0.65 + 0.35 * sin(u_time * 2.0 + hash(v_uv * 4096.0) * 100.0));
    grade += vec3(0.18, 0.20, 0.32) * spark * 0.18;

    gl_FragColor = vec4(grade, 1.0);
}
