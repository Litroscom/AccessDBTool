import tkinter as tk
import ttkbootstrap as ttk
import os
import logging

import constants

logger = logging.getLogger("AccessDBTool.DatabaseView")


class DatabaseView(ttk.Frame):
    def __init__(self, parent, state, db_controller):
        super().__init__(parent)
        self.state = state
        self.db_ctrl = db_controller
        self.current_insights = []
        self._on_load_insight = None
        self._on_profiler_done = None
        self._on_db_changed = None
        self._build_ui()

    def set_db_changed_callback(self, callback):
        """Chiamato dopo apertura/chiusura DB per aggiornare l'header dell'App."""
        self._on_db_changed = callback

    def set_load_insight_callback(self, callback):
        self._on_load_insight = callback

    def set_profiler_done_callback(self, callback):
        self._on_profiler_done = callback

    def _build_ui(self):
        left = ttk.Frame(self)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        right = ttk.Frame(self, width=300)
        right.pack(side=tk.RIGHT, fill=tk.BOTH)
        right.pack_propagate(False)

        db_frame = ttk.LabelFrame(left, text="Database Connesso", padding=8, bootstyle="info")
        db_frame.pack(fill=tk.X, pady=(0, 8))

        self.lbl_db_name = ttk.Label(db_frame, text="Nessun DB", font=("", 12, "bold"))
        self.lbl_db_name.pack(anchor=tk.W)
        self.lbl_db_path = ttk.Label(db_frame, text="", font=("", 9))
        self.lbl_db_path.pack(anchor=tk.W)
        self.lbl_db_tables = ttk.Label(db_frame, text="")
        self.lbl_db_tables.pack(anchor=tk.W)

        btn_frame = ttk.Frame(db_frame)
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_frame, text="Apri Database...", command=self._open_db,
                   bootstyle="primary").pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Chiudi", command=self._close_db,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=2)

        insight_frame = ttk.LabelFrame(left, text="Insight Automatici", padding=8)
        insight_frame.pack(fill=tk.BOTH, expand=True)

        self.ins_tree = ttk.Treeview(
            insight_frame, show="headings",
            columns=["title", "desc", "action"], height=8
        )
        self.ins_tree.heading("title", text="Suggerimento")
        self.ins_tree.heading("desc", text="Descrizione")
        self.ins_tree.heading("action", text="Tipo")
        self.ins_tree.column("title", width=200)
        self.ins_tree.column("desc", width=400)
        self.ins_tree.column("action", width=120)
        self.ins_tree.pack(fill=tk.BOTH, expand=True)
        self.ins_tree.bind("<Double-1>", self._load_insight)

        ttk.Button(insight_frame, text="Genera Insight",
                   command=self._run_profiler,
                   bootstyle="info-outline").pack(anchor=tk.W, pady=(4, 0))

        reg_frame = ttk.LabelFrame(right, text="Database Collegati", padding=8)
        reg_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.db_registry_tree = ttk.Treeview(
            reg_frame, columns=("label", "state"), show="headings", height=5
        )
        self.db_registry_tree.heading("label", text="Database")
        self.db_registry_tree.heading("state", text="Stato")
        self.db_registry_tree.column("label", width=160)
        self.db_registry_tree.column("state", width=90, anchor=tk.CENTER)
        self.db_registry_tree.pack(fill=tk.BOTH, expand=True)
        self.db_registry_tree.bind("<<TreeviewSelect>>", self._on_registry_select)
        self.lbl_registry_path = ttk.Label(reg_frame, text="", font=("", 8))
        self.lbl_registry_path.pack(fill=tk.X, pady=(4, 0))

        tab_frame = ttk.LabelFrame(right, text="Tabelle", padding=8)
        tab_frame.pack(fill=tk.BOTH, expand=True)

        self.tables_tree = ttk.Treeview(
            tab_frame, columns=("name",), show="headings", selectmode="extended"
        )
        self.tables_tree.heading("name", text="Nome Tabella")
        self.tables_tree.column("name", width=200)
        vsb = ttk.Scrollbar(tab_frame, orient=tk.VERTICAL, command=self.tables_tree.yview)
        self.tables_tree.configure(yscrollcommand=vsb.set)
        self.tables_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tables_tree.bind("<<TreeviewSelect>>", self._on_table_sel)

    def _open_db(self):
        self.db_ctrl.open_db()
        self.refresh()
        if self._on_db_changed:
            self._on_db_changed()

    def _close_db(self):
        self.db_ctrl.close_db()
        self.refresh()
        if self._on_db_changed:
            self._on_db_changed()

    def _run_profiler(self):
        self.db_ctrl.run_profiler()
        self.refresh_insights()
        if self._on_profiler_done:
            self._on_profiler_done()

    def _load_insight(self, event=None):
        if self._on_load_insight:
            self._on_load_insight(event)

    def refresh(self):
        if self.state.db.connected:
            label = self.state.current_db_label or "DB connesso"
            self.lbl_db_name.config(text=label)
            self.lbl_db_path.config(text=str(self.state.db.db_path))
            self.lbl_db_tables.config(
                text=f"{len(self.state.db.tables)} tabelle trovate"
            )
        else:
            self.lbl_db_name.config(text="Nessun DB")
            self.lbl_db_path.config(text="")
            self.lbl_db_tables.config(text="")
        self._refresh_registry()
        self._refresh_tables()
        self.refresh_insights()

    def refresh_insights(self):
        self.ins_tree.delete(*self.ins_tree.get_children())
        for ins in self.state.current_insights:
            self.ins_tree.insert("", tk.END, values=(
                ins.get("title", ""),
                ins.get("desc", ""),
                ins.get("action", ""),
            ))

    def _refresh_registry(self):
        self.db_registry_tree.delete(*self.db_registry_tree.get_children())
        current_path = str(getattr(self.state.db, "db_path", "") or "")
        for entry in self.state.db_registry.entries():
            label = entry.get("label", "")
            path = entry.get("path", "")
            path_exists = bool(path and os.path.exists(path))
            if self.state.db.connected and current_path and os.path.normcase(path) == os.path.normcase(current_path):
                state = "APERTO"
            elif path_exists:
                state = "PRONTO"
            else:
                state = "DA RICOLLEGARE"
            self.db_registry_tree.insert("", tk.END, iid=label, values=(label, state))

    def _refresh_tables(self):
        self.tables_tree.delete(*self.tables_tree.get_children())
        if self.state.db.connected:
            for table in self.state.db.tables:
                self.tables_tree.insert("", tk.END, values=(table,))

    def _on_registry_select(self, _evt=None):
        sel = self.db_registry_tree.selection()
        if not sel:
            return
        label = sel[0]
        path = self.state.db_registry.get_path(label)
        self.lbl_registry_path.config(text=path or "Percorso non associato.")

    def _on_table_sel(self, _evt=None):
        self.state.sel_tables = [
            self.tables_tree.item(iid, "values")[0]
            for iid in self.tables_tree.selection()
        ]
