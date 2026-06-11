import tkinter as tk
from tkinter import ttk
import logging

logger = logging.getLogger("AccessDBTool.MonitorView")


class MonitorView(ttk.Frame):
    """Tab che mostra l'esito dei controlli del monitor periodico."""

    COLS = ["time", "check", "status", "count"]

    def __init__(self, parent, state, app_controller):
        super().__init__(parent, padding=10)
        self.state = state
        self.app_ctrl = app_controller
        self._build_ui()
        self._repopulate()

    def _build_ui(self):
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(header, text="Monitor periodico", font=("", 12, "bold")).pack(side=tk.LEFT)
        self.lbl_state = ttk.Label(header, text="OFF", bootstyle="inverse-danger", padding=(8, 2))
        self.lbl_state.pack(side=tk.RIGHT)

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.mon_tree = ttk.Treeview(tree_frame, show="headings", columns=self.COLS)
        widths = {"time": 90, "check": 320, "status": 110, "count": 80}
        for c in self.COLS:
            self.mon_tree.heading(c, text=c.capitalize())
            self.mon_tree.column(c, width=widths.get(c, 120))
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.mon_tree.yview)
        self.mon_tree.configure(yscrollcommand=vsb.set)
        self.mon_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.mon_tree.tag_configure("hit", foreground="#ffb3b3")
        self.mon_tree.tag_configure("ok", foreground="#b3ffcc")
        self.mon_tree.tag_configure("err", foreground="#ffd27f")

        bb = ttk.Frame(self, padding=(0, 10))
        bb.pack(fill=tk.X)
        ttk.Button(bb, text="AVVIA MONITOR", command=self._start, bootstyle="success").pack(side=tk.LEFT, padx=4)
        ttk.Button(bb, text="FERMA", command=self._stop, bootstyle="danger-outline").pack(side=tk.LEFT, padx=4)
        ttk.Button(bb, text="PULISCI LOG", command=self._clear, bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=4)
        self._refresh_state_label()

    def _start(self):
        self.app_ctrl.start_monitor()
        self._refresh_state_label()

    def _stop(self):
        self.app_ctrl.stop_monitor()
        self._refresh_state_label()

    def _refresh_state_label(self):
        running = bool(getattr(self.state, "monitor", None) and getattr(self.state.monitor, "is_running", False))
        if running:
            self.lbl_state.config(text="ON", bootstyle="inverse-success")
        else:
            self.lbl_state.config(text="OFF", bootstyle="inverse-danger")

    def add_row(self, row):
        """row = (time, check, status, count). Called by AppController on each monitor result."""
        try:
            if not self.mon_tree.winfo_exists():
                return
        except Exception:
            return
        status = str(row[2]) if len(row) > 2 else ""
        count = row[3] if len(row) > 3 else 0
        if status == "Errore":
            tag = "err"
        elif isinstance(count, (int, float)) and count > 0:
            tag = "hit"
        else:
            tag = "ok"
        self.mon_tree.insert("", 0, values=row, tags=(tag,))

    def _repopulate(self):
        log = getattr(self.state, "mon_log", None)
        for entry in getattr(log, "entries", []) if log else []:
            name = entry.get("name") or entry.get("check") or "?"
            count = entry.get("count", 0)
            if entry.get("type") == "check_error":
                status = "Errore"
            elif count and count > 0:
                status = "Trovati"
            else:
                status = "OK"
            self.add_row(("", name, status, count))

    def _clear(self):
        self.mon_tree.delete(*self.mon_tree.get_children())
        if getattr(self.state, "mon_log", None):
            self.state.mon_log.clear()
        self.state.status.set("Log monitor pulito.")
