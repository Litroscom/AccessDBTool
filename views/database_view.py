import tkinter as tk
from tkinter import ttk
import os
import logging

import constants

logger = logging.getLogger("AccessDBTool.DatabaseView")


class DatabaseView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.current_insights = []
        self._build_ui()

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
        ttk.Button(btn_frame, text="Apri Database...", command=self.app._open_db,
                   bootstyle="primary").pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Chiudi", command=self.app._close_db,
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
        self.ins_tree.bind("<Double-1>", self.app._load_insight)

        ttk.Button(insight_frame, text="Genera Insight",
                   command=self.app._run_profiler,
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

        scroll = ttk.Scrollbar(tab_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.lst_tables = tk.Listbox(
            tab_frame, yscrollcommand=scroll.set,
            font=("Consolas", 10), selectmode=tk.MULTIPLE
        )
        self.lst_tables.pack(fill=tk.BOTH, expand=True)
        scroll.config(command=self.lst_tables.yview)
        self.lst_tables.bind("<<ListboxSelect>>", self.app._on_table_sel)

    def refresh(self):
        if self.app.db.connected:
            label = self.app.current_db_label or "DB connesso"
            self.lbl_db_name.config(text=label)
            self.lbl_db_path.config(text=str(self.app.db.db_path))
            self.lbl_db_tables.config(
                text=f"{len(self.app.db.tables)} tabelle trovate"
            )
        else:
            self.lbl_db_name.config(text="Nessun DB")
            self.lbl_db_path.config(text="")
            self.lbl_db_tables.config(text="")
        self._refresh_registry()
        self._refresh_tables()

    def _refresh_registry(self):
        self.db_registry_tree.delete(*self.db_registry_tree.get_children())
        current_path = str(getattr(self.app.db, "db_path", "") or "")
        for entry in self.app.db_registry.entries():
            label = entry.get("label", "")
            path = entry.get("path", "")
            path_exists = bool(path and os.path.exists(path))
            if self.app.db.connected and current_path and os.path.normcase(path) == os.path.normcase(current_path):
                state = "APERTO"
            elif path_exists:
                state = "PRONTO"
            else:
                state = "DA RICOLLEGARE"
            self.db_registry_tree.insert("", tk.END, iid=label, values=(label, state))

    def _refresh_tables(self):
        self.lst_tables.delete(0, tk.END)
        if self.app.db.connected:
            for table in self.app.db.tables:
                self.lst_tables.insert(tk.END, table)

    def _on_registry_select(self, _evt=None):
        sel = self.db_registry_tree.selection()
        if not sel:
            return
        label = sel[0]
        path = self.app.db_registry.get_path(label)
        self.lbl_registry_path.config(text=path or "Percorso non associato.")
