"""Design tokens — dark-first, single azure-blue accent."""
import flet as ft

# ── Palette ──────────────────────────────────────────────────────────────────
DARK_BG = "#0d1117"
DARK_SURFACE = "#161b22"
DARK_SURFACE2 = "#21262d"
DARK_BORDER = "#30363d"
DARK_TEXT = "#e6edf3"
DARK_TEXT_MUTED = "#8b949e"

LIGHT_BG = "#f6f8fa"
LIGHT_SURFACE = "#ffffff"
LIGHT_SURFACE2 = "#f0f2f5"
LIGHT_BORDER = "#d0d7de"
LIGHT_TEXT = "#1f2328"
LIGHT_TEXT_MUTED = "#57606a"

ACCENT = "#3b82f6"        # azure blue
ACCENT_HOVER = "#2563eb"
SUCCESS = "#22c55e"       # green — Activate / Active
WARN = "#f59e0b"          # amber — Pending
ERROR = "#ef4444"         # red — Denied / Failed
INFO = "#60a5fa"          # light blue — info chips

# ── Spacing grid (8 px base) ─────────────────────────────────────────────────
S1 = 4
S2 = 8
S3 = 12
S4 = 16
S5 = 24
S6 = 32
S7 = 48
S8 = 64

# ── Typography ────────────────────────────────────────────────────────────────
FONT_FAMILY = "Inter"
SIZE_XS = 11
SIZE_SM = 12
SIZE_TABLE = 13
SIZE_BODY = 14
SIZE_TITLE = 20
SIZE_HERO = 28

# ── Radius ────────────────────────────────────────────────────────────────────
RADIUS_SM = 4
RADIUS_MD = 8
RADIUS_LG = 12
RADIUS_PILL = 99


def build_theme(dark: bool) -> ft.Theme:
    bg = DARK_BG if dark else LIGHT_BG
    surface = DARK_SURFACE if dark else LIGHT_SURFACE

    color_scheme = ft.ColorScheme(
        primary=ACCENT,
        primary_container=ACCENT_HOVER,
        secondary=INFO,
        background=bg,
        surface=surface,
        error=ERROR,
        on_primary="#ffffff",
        on_secondary="#ffffff",
        on_background=DARK_TEXT if dark else LIGHT_TEXT,
        on_surface=DARK_TEXT if dark else LIGHT_TEXT,
        on_error="#ffffff",
        brightness=ft.Brightness.DARK if dark else ft.Brightness.LIGHT,
    )

    return ft.Theme(
        color_scheme=color_scheme,
        color_scheme_seed=ACCENT,
        font_family=FONT_FAMILY,
        visual_density=ft.ThemeVisualDensity.COMPACT,
        use_material3=True,
    )


DARK_THEME = build_theme(dark=True)
LIGHT_THEME = build_theme(dark=False)
