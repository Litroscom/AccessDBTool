import ttkbootstrap as ttk
from ttkbootstrap.constants import *

THEME_NAME = "superhero"

MONITOR_COLORS = {
    "monitor_on": "success",
    "monitor_off": "danger",
    "dash_error": "#fff0f0",
    "dash_ok": "#f0fff4",
    "dash_running": "#fffbe6",
}


def setup_theme(app):
    style = ttk.Style(theme=THEME_NAME)
    style.configure("success.TLabel", foreground="#00b894")
    style.configure("danger.TLabel", foreground="#E85D75")
    style.configure("warning.TLabel", foreground="#fdcb6e")
    style.configure("Nav.TButton", font=("", 12, "bold"), padding=(12, 6))
    return style
