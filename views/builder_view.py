import tkinter as tk
from tkinter import ttk
import logging

import constants
from ui_components import ColumnSelector

logger = logging.getLogger("AccessDBTool.BuilderView")


class BuilderView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._sections = {}
        self._active_section = None
        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(top, text="Tipo Analisi:", font=("", 9, "bold")).pack(side=tk.LEFT)
        self.cmb_ctype = ttk.Combobox(
            top, values=list(constants.CONDITION_TYPES.values()),
            state="readonly", width=35
        )
        self.cmb_ctype.pack(side=tk.LEFT, padx=8)
        self.cmb_ctype.bind("<<ComboboxSelected>>", self._on_ctype_change)

        ttk.Label(top, text="Tag:", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(20, 4))
        self.var_tag = tk.StringVar(value="Tutti")
        self.cmb_tag = ttk.Combobox(
            top, textvariable=self.var_tag, state="readonly", width=18
        )
        self.cmb_tag.pack(side=tk.LEFT, padx=4)

        ttk.Label(top, text="DB:", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(20, 4))
        self.var_db = tk.StringVar()
        self.cmb_db = ttk.Combobox(
            top, textvariable=self.var_db, state="readonly", width=20
        )
        self.cmb_db.pack(side=tk.LEFT, padx=4)

        self.nav_sections = ttk.Frame(self)
        self.nav_sections.pack(fill=tk.X, pady=(0, 6))

        self.pill_buttons = {}
        for sid, slabel in [
            ("base", "Base"),
            ("filtri", "Filtri"),
            ("esclusioni", "Esclusioni"),
            ("report", "Colonne Report"),
            ("periodicita", "Periodicità"),
        ]:
            btn = ttk.Button(
                self.nav_sections, text=slabel,
                command=lambda s=sid: self._show_section(s),
                bootstyle="secondary-outline",
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.pill_buttons[sid] = btn

        self.section_content = ttk.Frame(self, relief=tk.SUNKEN, borderwidth=1)
        self.section_content.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        lib_frame = ttk.LabelFrame(self, text="Libreria", padding=6)
        lib_frame.pack(fill=tk.X)

        self.cmb_lib = ttk.Combobox(lib_frame, state="readonly", width=40)
        self.cmb_lib.pack(side=tk.LEFT, padx=4)
        ttk.Button(lib_frame, text="Carica",
                   command=self._load_from_lib,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)
        ttk.Button(lib_frame, text="Gestisci...",
                   command=self.app._open_manager,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)
        ttk.Button(lib_frame, text="Gruppi...",
                   command=self._open_groups,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        action_bar = ttk.Frame(self)
        action_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(action_bar, text="Pulisci",
                   command=self.app._clear_builder,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="💾 Salva in Libreria",
                   command=self.app._save_to_lib,
                   bootstyle="success").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="♻ Aggiorna Salvata",
                   command=self.app._update_to_lib,
                   bootstyle="warning").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="▶ Esegui Controllo",
                   command=self.app._run_current,
                   bootstyle="danger").pack(side=tk.RIGHT, padx=2)

        # Crea il builder frame di riserva e col_selector
        self.frm_dyn = ttk.Frame(self)

        import ui_components
        self.col_selector = ColumnSelector(self)
        self.col_selector.pack_forget()

    def _on_ctype_change(self, _evt=None):
        ctype_name = self.cmb_ctype.get()
        rev = {v: k for k, v in constants.CONDITION_TYPES.items()}
        self.app._active_ctype = rev.get(ctype_name)
        self.app._update_builder_fields()
        self._show_section("base")

    def _show_section(self, section_id):
        for sid, btn in self.pill_buttons.items():
            btn.configure(bootstyle="secondary-outline")
        self.pill_buttons[section_id].configure(bootstyle="primary")
        self._active_section = section_id

        for w in self.section_content.winfo_children():
            w.destroy()

        if section_id == "base":
            self._build_section_base()
        elif section_id == "filtri":
            self._build_section_filtri()
        elif section_id == "esclusioni":
            self._build_section_esclusioni()
        elif section_id == "report":
            self._build_section_report()
        elif section_id == "periodicita":
            self._build_section_periodicita()

    def _build_section_base(self):
        if self.app.active_builder:
            self.app.active_builder.pack(in_=self.section_content, fill=tk.BOTH, expand=True)
        elif hasattr(self.app, "frm_dyn"):
            for w in self.app.frm_dyn.winfo_children():
                w.pack(in_=self.section_content)
        else:
            ttk.Label(self.section_content, text="Seleziona un tipo analisi per iniziare.").pack()

    def _build_section_filtri(self):
        ttk.Label(self.section_content, text="Filtri condizioni (in arrivo)").pack()

    def _build_section_esclusioni(self):
        ttk.Label(self.section_content, text="Esclusioni (in arrivo)").pack()

    def _build_section_report(self):
        if hasattr(self, "col_selector"):
            self.col_selector.pack(in_=self.section_content, fill=tk.X, pady=5)
        else:
            ttk.Label(self.section_content, text="Nessun selettore colonne disponibile.").pack()

    def _build_section_periodicita(self):
        ttk.Label(self.section_content, text="Configurazione periodicità (in arrivo)").pack()

    def _load_from_lib(self):
        self.app._load_from_lib()

    def _open_groups(self):
        if hasattr(self.app, "group_sel"):
            self.app.group_sel.open_dialog()

    def refresh_lib(self):
        names = self.app.store.names()
        self.cmb_lib["values"] = names
        if self.app.var_saved.get() not in names:
            self.app.var_saved.set("")

    def sync_ctype(self):
        if self.app._active_ctype:
            ctype_label = constants.CONDITION_TYPES.get(self.app._active_ctype, "")
            if ctype_label:
                self.cmb_ctype.set(ctype_label)
