import tkinter as tk
from tkinter import ttk
import threading
import logging

logger = logging.getLogger("AccessDBTool.DashboardView")


class DashboardView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        filters = ttk.Frame(self, padding=6)
        filters.pack(fill=tk.X)

        ttk.Label(filters, text="📂 DB:").pack(side=tk.LEFT)
        self.var_db_filter = tk.StringVar(value="Tutti")
        self.cmb_db = ttk.Combobox(
            filters, textvariable=self.var_db_filter,
            values=["Tutti"], state="readonly", width=18
        )
        self.cmb_db.pack(side=tk.LEFT, padx=4)
        self.cmb_db.bind("<<ComboboxSelected>>", lambda _: self._refresh())

        ttk.Label(filters, text="🏷 Tag:").pack(side=tk.LEFT, padx=(12, 4))
        self.var_tag_filter = tk.StringVar(value="Tutti")
        self.cmb_macro = ttk.Combobox(
            filters, textvariable=self.var_tag_filter,
            values=["Tutti"], state="readonly", width=18
        )
        self.cmb_macro.pack(side=tk.LEFT, padx=4)
        self.cmb_macro.bind("<<ComboboxSelected>>", lambda _: self._refresh())

        self.var_anomalies_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(filters, text="Solo anomalie",
                        variable=self.var_anomalies_only,
                        command=self._refresh).pack(side=tk.LEFT, padx=(12, 4))

        self.var_search_text = tk.StringVar()
        self.entry_search = ttk.Entry(filters, textvariable=self.var_search_text, width=20)
        self.entry_search.pack(side=tk.LEFT, padx=4)
        self.entry_search.bind("<KeyRelease>", lambda _: self._refresh())

        ttk.Button(filters, text="▶ Esegui Selezionato",
                   command=self._run_selected,
                   bootstyle="warning-outline").pack(side=tk.RIGHT, padx=2)
        ttk.Button(filters, text="▶ Esegui Tutti",
                   command=self._run_all,
                   bootstyle="danger").pack(side=tk.RIGHT, padx=2)

        tree_frame = ttk.Frame(self, padding=4)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.dash_tree = ttk.Treeview(
            tree_frame,
            columns=["id", "group", "db", "name", "period", "tag", "type", "count", "status"],
            show="headings", height=10,
        )
        self.dash_tree.heading("id", text="#")
        self.dash_tree.column("id", width=30, anchor=tk.CENTER)
        self.dash_tree.heading("group", text="Gruppo")
        self.dash_tree.column("group", width=120)
        self.dash_tree.heading("db", text="DB")
        self.dash_tree.column("db", width=120)
        self.dash_tree.heading("name", text="Controllo")
        self.dash_tree.column("name", width=250)
        self.dash_tree.heading("period", text="Periodo")
        self.dash_tree.column("period", width=160)
        self.dash_tree.heading("tag", text="Tag")
        self.dash_tree.column("tag", width=120)
        self.dash_tree.heading("type", text="Tipo")
        self.dash_tree.column("type", width=120)
        self.dash_tree.heading("count", text="Ris.")
        self.dash_tree.column("count", width=60, anchor=tk.CENTER)
        self.dash_tree.heading("status", text="Stato")
        self.dash_tree.column("status", width=120)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.dash_tree.yview)
        self.dash_tree.configure(yscrollcommand=vsb.set)
        self.dash_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.dash_tree.tag_configure("error", background="#fff0f0")
        self.dash_tree.tag_configure("ok", background="#f0fff4")
        self.dash_tree.tag_configure("running", background="#fffbe6")
        self.dash_tree.bind("<Double-1>", self._on_double_click)

        result_frame = ttk.LabelFrame(self, text="Risultati", padding=4)
        result_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.res_lbl = ttk.Label(result_frame, text="Nessun risultato", font=("", 9))
        self.res_lbl.pack(anchor=tk.W)

        self.res_tree = ttk.Treeview(result_frame, show="headings", height=5)
        self.res_tree.pack(fill=tk.BOTH, expand=True)

        self.progress_frame = ttk.Frame(result_frame)
        self.progress_frame.pack(fill=tk.X, pady=(4, 0))
        self.progress = ttk.Progressbar(
            self.progress_frame, mode="determinate",
            bootstyle="success-striped"
        )
        self.progress.pack(fill=tk.X)
        self.lbl_progress = ttk.Label(self.progress_frame, text="", font=("", 8))
        self.lbl_progress.pack(anchor=tk.W)

    def _refresh(self):
        self.app._refresh_dash()

    def _run_selected(self):
        self.app._run_selected_dashboard_check()

    def _run_all(self):
        self.app._run_all_batch()

    def _on_double_click(self, evt):
        self.app._on_dash_double_click(evt)

    def show_results(self, res):
        if not res:
            return
        self.res_lbl.config(text=f"{res.get('title', '?')} ({res.get('count', 0)} record)")
        self.res_tree.delete(*self.res_tree.get_children())
        self.res_tree["columns"] = res.get("columns", [])
        for c in res.get("columns", []):
            self.res_tree.heading(c, text=c)
            self.res_tree.column(c, width=120)
        for i, r in enumerate(res.get("rows", [])):
            self.res_tree.insert("", tk.END, iid=str(i), values=r)

    def show_progress(self, current, total, text=""):
        if total > 0:
            self.progress["maximum"] = total
            self.progress["value"] = current
        self.lbl_progress.config(text=text)
