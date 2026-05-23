import tkinter as tk
from tkinter import ttk
import logging

logger = logging.getLogger("AccessDBTool.BuilderView")


class BuilderView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        f = ttk.Frame(self, padding=20)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Controlli View (placeholder)", font=("", 16, "bold")).pack()
        ttk.Label(f, text="Verrà implementata nel Task 5").pack()

    def refresh_lib(self):
        pass
