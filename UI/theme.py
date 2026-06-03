"""
Shadcn-inspired design tokens for IRIS UI.
Colors in oklch converted to RGB hex for rendering.
"""

def oklch_to_rgb(L: float, C: float, H: float) -> tuple[int, int, int]:
    """Convert oklch(L C H) to RGB(0-255)."""
    import math

    H_rad = math.radians(H)

    # oklch to lch
    l = L
    c = C
    h = H_rad

    # lch to lab
    a = c * math.cos(h)
    b = c * math.sin(h)

    # lab to xyz (using D65 illuminant)
    fy = (l + 0.3) / 1.29
    fx = a / 5.0 + fy
    fz = fy - b / 2.0

    xr = fx ** 3 if fx ** 3 > 0.008856 else (fx - 16 / 116) / 7.787
    yr = 1.0 if l > 0.008856 * 903.3 else (l / 903.3)
    zr = fz ** 3 if fz ** 3 > 0.008856 else (fz - 16 / 116) / 7.787

    x = xr * 0.95047
    y = yr * 1.0
    z = zr * 1.08883

    # xyz to rgb
    r = x * 3.2406 + y * -1.5372 + z * -0.4986
    g = x * -0.9689 + y * 1.8758 + z * 0.0415
    b_val = x * 0.0557 + y * -0.204 + z * 1.057

    # gamma correction (sRGB)
    def gamma(c_val):
        if c_val <= 0.0031308:
            return c_val * 12.92
        return 1.055 * (c_val ** (1 / 2.4)) - 0.055

    r = max(0, min(1, gamma(r)))
    g = max(0, min(1, gamma(g)))
    b_val = max(0, min(1, gamma(b_val)))

    return (int(r * 255), int(g * 255), int(b_val * 255))


def oklch_to_hex(L: float, C: float, H: float) -> str:
    """Convert oklch(L C H) to hex color string."""
    r, g, b = oklch_to_rgb(L, C, H)
    return f"#{r:02x}{g:02x}{b:02x}"


# Light theme
LIGHT = {
    "background": oklch_to_hex(1, 0, 0),
    "foreground": oklch_to_hex(0.147, 0.004, 49.3),
    "card": oklch_to_hex(1, 0, 0),
    "card_foreground": oklch_to_hex(0.147, 0.004, 49.3),
    "popover": oklch_to_hex(1, 0, 0),
    "popover_foreground": oklch_to_hex(0.147, 0.004, 49.3),
    "primary": oklch_to_hex(0.214, 0.009, 43.1),
    "primary_foreground": oklch_to_hex(0.986, 0.002, 67.8),
    "secondary": oklch_to_hex(0.96, 0.002, 17.2),
    "secondary_foreground": oklch_to_hex(0.214, 0.009, 43.1),
    "muted": oklch_to_hex(0.96, 0.002, 17.2),
    "muted_foreground": oklch_to_hex(0.547, 0.021, 43.1),
    "accent": oklch_to_hex(0.214, 0.009, 43.1),
    "accent_foreground": oklch_to_hex(0.986, 0.002, 67.8),
    "destructive": oklch_to_hex(0.577, 0.245, 27.325),
    "border": oklch_to_hex(0.922, 0.005, 34.3),
    "input": oklch_to_hex(0.922, 0.005, 34.3),
    "ring": oklch_to_hex(0.714, 0.014, 41.2),
}

# Dark theme
DARK = {
    "background": oklch_to_hex(0.147, 0.004, 49.3),
    "foreground": oklch_to_hex(0.986, 0.002, 67.8),
    "card": oklch_to_hex(0.214, 0.009, 43.1),
    "card_foreground": oklch_to_hex(0.986, 0.002, 67.8),
    "popover": oklch_to_hex(0.214, 0.009, 43.1),
    "popover_foreground": oklch_to_hex(0.986, 0.002, 67.8),
    "primary": oklch_to_hex(0.922, 0.005, 34.3),
    "primary_foreground": oklch_to_hex(0.214, 0.009, 43.1),
    "secondary": oklch_to_hex(0.268, 0.011, 36.5),
    "secondary_foreground": oklch_to_hex(0.986, 0.002, 67.8),
    "muted": oklch_to_hex(0.268, 0.011, 36.5),
    "muted_foreground": oklch_to_hex(0.714, 0.014, 41.2),
    "accent": oklch_to_hex(0.922, 0.005, 34.3),
    "accent_foreground": oklch_to_hex(0.214, 0.009, 43.1),
    "destructive": oklch_to_hex(0.704, 0.191, 22.216),
    "border": oklch_to_hex(1, 0, 0),  # oklch(1 0 0 / 10%) mapped
    "input": oklch_to_hex(1, 0, 0),  # oklch(1 0 0 / 15%) mapped
    "ring": oklch_to_hex(0.547, 0.021, 43.1),
}

# Design tokens
RADIUS = 0.625  # rem, ~10px at 16px base
SHADOW_SM = "0 1px 2px rgba(0, 0, 0, 0.05)"
SHADOW_MD = "0 4px 6px rgba(0, 0, 0, 0.1)"
SHADOW_LG = "0 10px 15px rgba(0, 0, 0, 0.1)"

# Transitions
TRANSITION_FAST = 0.15  # seconds
TRANSITION_BASE = 0.3   # seconds


class Theme:
    """Theme manager with light/dark support."""

    def __init__(self, dark: bool = False):
        self.dark = dark
        self.tokens = DARK if dark else LIGHT

    def get_color(self, token: str) -> str:
        """Get hex color by token name."""
        return self.tokens.get(token, "#000000")

    def switch(self):
        """Toggle between light and dark."""
        self.dark = not self.dark
        self.tokens = DARK if self.dark else LIGHT

    def rgb(self, token: str) -> tuple[int, int, int]:
        """Get RGB tuple from hex color token."""
        hex_color = self.get_color(token)
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def rgba(self, token: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
        """Get RGBA tuple from hex color token."""
        r, g, b = self.rgb(token)
        return (r, g, b, int(alpha * 255))
