"""
gui/theme.py
────────────
Carga única del tema UI desde config/ui_theme.yml.
Si el fichero no existe o es inválido usa los valores por defecto embebidos.

Uso en cualquier fichero GUI:
    from gui import theme

    ctk.CTkButton(parent, text="Start", **theme.btn_style("start"))
    ctk.CTkLabel(parent, font=theme.font("base"), text_color=theme.C.text_primary)
    ctk.CTkComboBox(parent, **theme.combo_style())
"""

from __future__ import annotations

import os
import types
from typing import Optional

# ── Defaults embebidos (igual que ui_theme.yml) ───────────────────────────────
_DEFAULTS: dict = {
    "fonts": {
        "family": "Segoe UI",
        "mono": "Consolas",
        "sizes": {
            "xs": 9, "sm": 10, "md": 11, "base": 12,
            "lg": 13, "xl": 14, "xxl": 15, "h2": 16, "h1": 22,
        },
    },
    "geometry": {
        "corner_btn": 6, "corner_card": 10, "corner_panel": 8,
        "corner_badge": 4, "corner_combo": 6, "corner_tooltip": 6,
        "border_width": 1,
        "btn_height_sm": 24, "btn_height_md": 28, "btn_height_lg": 34,
        "topbar_height": 56,
        "checkbox_size": 18, "checkbox_size_sm": 16, "checkbox_corner": 4,
    },
    "backgrounds": {
        "app": "#0f0e26", "card": "#16132e", "card_hover": "#1c1940",
        "expand_panel": "#120f28", "section": "#1e1b4b",
        "section_alt": "#0f172a", "divider": "#312e81",
    },
    "borders": {
        "card": "#3b3768", "default": "#4338ca",
        "settings": "#312e81", "subtle": "#334155",
    },
    "text": {
        "primary": "#e0e7ff", "secondary": "#c7d2fe",
        "muted": "#94a3b8", "faint": "#6b7280",
        "placeholder": "#888888", "accent": "#6366f1",
        "accent_bright": "#818cf8", "warning_badge": "#facc15",
        "white": "#ffffff",
        "file_btn_light": "#333333", "file_btn_dark": "#dddddd",
        "file_btn_hover_light": "#E3F2FD", "file_btn_hover_dark": "#1a2332",
    },
    "status": {
        "running": "#22c55e", "starting": "#eab308",
        "stopped": "#6b7280", "error": "#ef4444", "logging": "#f97316",
    },
    "buttons": {
        "success":       {"fg": "#064e3b", "hover": "#047857", "border": "#10b981"},
        "start":         {"fg": "#144d28", "hover": "#16a34a", "border": "#22c55e"},
        "danger":        {"fg": "#4c1616", "hover": "#dc2626", "border": "#ef4444"},
        "danger_alt":    {"fg": "#7f1d1d", "hover": "#991b1b", "border": "#b91c1c"},
        "danger_deep":   {"fg": "#450a0a", "hover": "#dc2626", "border": "#ef4444"},
        "warning":       {"fg": "#4a3310", "hover": "#d97706", "border": "#f59e0b"},
        "blue":          {"fg": "#172554", "hover": "#2563eb", "border": "#3b82f6"},
        "blue_active":   {"fg": "#1d4ed8", "hover": "#2563eb", "border": "#3b82f6"},
        "neutral":       {"fg": "#1e293b", "hover": "#475569", "border": "#64748b"},
        "neutral_alt":   {"fg": "#334155", "hover": "#475569", "border": "#64748b"},
        "purple":        {"fg": "#2e1065", "hover": "#6d28d9", "border": "#7c3aed"},
        "purple_alt":    {"fg": "#4c1d95", "hover": "#6d28d9", "border": "#7c3aed"},
        "purple_global": {"fg": "#2e1065", "hover": "#9333ea", "border": "#a855f7"},
        "log_action":    {"fg": "#1e1b4b", "hover": "#312e81", "border": "#4338ca"},
        "toggle_expand": {"fg": "transparent", "hover": "#312e81", "border": "#4338ca"},
        "profile_accent":{"fg": "#7c3aed", "hover": "#6d28d9", "border": "#7c3aed"},
    },
    "docker": {
        "btn_stopped_fg": "#1e293b", "btn_active_fg": "#0f172a",
        "border_running": "#10b981", "border_active": "#3b82f6",
        "border_stopped": "#334155",
    },
    "tooltip": {
        "bg_dark": "#2a2a3e", "text_dark": "#e0e0e0", "border_dark": "#444466",
        "bg_light": "#333344", "text_light": "#f5f5f5", "border_light": "#555577",
        "delay_ms": 500, "wrap_px": 250,
    },
}

# ── Carga del YAML ─────────────────────────────────────────────────────────────
def _load_yaml_theme() -> dict:
    yaml_path = os.path.join(os.path.dirname(__file__), "..", "config", "ui_theme.yml")
    try:
        import yaml  # PyYAML ya está en requirements.txt
        with open(yaml_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Mezcla override sobre base recursivamente."""
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


_raw: dict = _deep_merge(_DEFAULTS, _load_yaml_theme())

# ── Fuentes ───────────────────────────────────────────────────────────────────
FONT_FAMILY: str = _raw["fonts"]["family"]
FONT_MONO: str = _raw["fonts"]["mono"]
_SIZES: dict = _raw["fonts"]["sizes"]


def font(size_key: str, bold: bool = False, mono: bool = False) -> tuple:
    """
    Devuelve una tupla de fuente para el argumento ``font=`` de customtkinter.

    Ejemplos::

        theme.font("base")           -> ("Segoe UI", 12)
        theme.font("h1", bold=True)  -> ("Segoe UI", 22, "bold")
        theme.font("sm", mono=True)  -> ("Consolas", 10)
    """
    family = FONT_MONO if mono else FONT_FAMILY
    size = _SIZES.get(size_key, 12)
    return (family, size, "bold") if bold else (family, size)


# ── Colores (C) ───────────────────────────────────────────────────────────────
def _build_colors(raw: dict) -> types.SimpleNamespace:
    bg = raw["backgrounds"]
    brd = raw["borders"]
    tx = raw["text"]
    st = raw["status"]
    dk = raw["docker"]
    ns = types.SimpleNamespace(
        # Fondos
        app=bg["app"],
        card=bg["card"],
        card_hover=bg["card_hover"],
        expand_panel=bg["expand_panel"],
        section=bg["section"],
        section_alt=bg["section_alt"],
        divider=bg["divider"],
        # Bordes
        card_border=brd["card"],
        default_border=brd["default"],
        settings_border=brd["settings"],
        subtle_border=brd["subtle"],
        # Texto
        text_primary=tx["primary"],
        text_secondary=tx["secondary"],
        text_muted=tx["muted"],
        text_faint=tx["faint"],
        text_placeholder=tx["placeholder"],
        text_accent=tx["accent"],
        text_accent_bright=tx["accent_bright"],
        text_warning_badge=tx["warning_badge"],
        text_white=tx["white"],
        # Selector de ficheros (tuples light/dark)
        file_btn_light=tx["file_btn_light"],
        file_btn_dark=tx["file_btn_dark"],
        file_btn_hover_light=tx["file_btn_hover_light"],
        file_btn_hover_dark=tx["file_btn_hover_dark"],
        # Status
        status_running=st["running"],
        status_starting=st["starting"],
        status_stopped=st["stopped"],
        status_error=st["error"],
        status_logging=st["logging"],
        # Docker
        docker_stopped_fg=dk["btn_stopped_fg"],
        docker_active_fg=dk["btn_active_fg"],
        docker_border_running=dk["border_running"],
        docker_border_active=dk["border_active"],
        docker_border_stopped=dk["border_stopped"],
        # Acento del combo de perfil
        profile_accent=raw["buttons"]["profile_accent"]["fg"],
    )
    return ns


C: types.SimpleNamespace = _build_colors(_raw)

# ── Geometría (G) ─────────────────────────────────────────────────────────────
def _build_geometry(raw: dict) -> types.SimpleNamespace:
    g = raw["geometry"]
    return types.SimpleNamespace(**g)


G: types.SimpleNamespace = _build_geometry(_raw)

# ── Dicts de estado (compatibilidad con repo_card.py) ─────────────────────────
STATUS_ICONS: dict[str, str] = {
    "running": C.status_running,
    "starting": C.status_starting,
    "stopped":  C.status_stopped,
    "error":    C.status_error,
    "logging":  C.status_logging,
}

COLORS: dict[str, str] = {
    "running": C.status_running,
    "starting": C.status_starting,
    "stopped":  C.status_stopped,
    "error":    C.status_error,
}

# ── Helpers de estilos de widgets ─────────────────────────────────────────────

def btn_style(
    variant: str,
    height: str = "md",
    width: Optional[int] = None,
    font_size: str = "base",
) -> dict:
    """
    Devuelve un dict de kwargs para ``ctk.CTkButton``.

    Incluye: ``fg_color``, ``hover_color``, ``border_color``,
    ``border_width``, ``corner_radius``, ``height``, ``font``.

    Uso::

        ctk.CTkButton(parent, text="Start", width=80,
                      **theme.btn_style("start"))
        ctk.CTkButton(parent, text="X", **theme.btn_style("danger", height="sm"))
    """
    bdef = _raw["buttons"].get(variant, _raw["buttons"]["neutral"])
    height_map = {
        "sm": G.btn_height_sm,
        "md": G.btn_height_md,
        "lg": G.btn_height_lg,
    }
    h = height_map.get(height, G.btn_height_md)
    result = {
        "fg_color":     bdef["fg"],
        "hover_color":  bdef["hover"],
        "border_color": bdef["border"],
        "border_width": G.border_width,
        "corner_radius": G.corner_btn,
        "height":       h,
        "font":         font(font_size),
    }
    if width is not None:
        result["width"] = width
    return result


def combo_style(height: str = "md") -> dict:
    """
    Devuelve un dict de kwargs para ``ctk.CTkComboBox`` con el estilo por defecto.

    Incluye: ``fg_color``, ``border_color``, ``button_color``,
    ``corner_radius``, ``height``, ``font``.
    """
    height_map = {"sm": G.btn_height_sm, "md": G.btn_height_md, "lg": G.btn_height_lg}
    return {
        "fg_color":     C.section,
        "border_color": C.default_border,
        "button_color": C.default_border,
        "corner_radius": G.corner_combo,
        "height":       height_map.get(height, G.btn_height_md),
        "font":         font("base"),
    }


def log_textbox_style(detached: bool = False) -> dict:
    """
    Devuelve kwargs para ``ctk.CTkTextbox`` de log.

    ``detached=True`` devuelve el estilo sin bordes para ventanas flotantes.
    """
    if detached:
        return {
            "corner_radius": 0,
            "border_width":  0,
            "fg_color":      C.app,
            "text_color":    C.text_primary,
            "font":          font("sm", mono=True),
        }
    return {
        "corner_radius": G.corner_btn,
        "border_width":  G.border_width,
        "border_color":  C.card_border,
        "fg_color":      C.app,
        "text_color":    C.text_primary,
        "font":          font("sm", mono=True),
    }


def tooltip_colors(mode: str) -> tuple[str, str, str]:
    """
    Devuelve ``(bg, text, border)`` según el modo de apariencia CTk.

    ``mode`` es el string que devuelve ``ctk.get_appearance_mode()``.
    """
    t = _raw["tooltip"]
    if mode.lower() == "dark":
        return t["bg_dark"], t["text_dark"], t["border_dark"]
    return t["bg_light"], t["text_light"], t["border_light"]


def tooltip_delay() -> int:
    """Milisegundos de retraso antes de mostrar el tooltip."""
    return int(_raw["tooltip"]["delay_ms"])


def tooltip_wrap() -> int:
    """Anchura de envuelto del texto del tooltip en píxeles."""
    return int(_raw["tooltip"]["wrap_px"])
