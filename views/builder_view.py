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
        self._sync_builder_from_sections()

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
        if not self.app.active_builder:
            ttk.Label(self.section_content, text="Configura prima la sezione Base.").pack(pady=20)
            return
        try:
            config = self.app.active_builder.get_config()
        except Exception:
            ttk.Label(self.section_content, text="Questo tipo di controllo non supporta filtri aggiuntivi.").pack(pady=20)
            return

        table = config.get("table", "")
        conditions = config.get("conditions", [])

        from ui_components import MultiConditionBuilder
        filtro = MultiConditionBuilder(
            self.section_content, self.app.db,
            on_table_change=self.app._on_builder_table_change,
            title="Filtri (AND/OR)"
        )
        filtro.pack(fill=tk.BOTH, expand=True)
        filtro.set_config({
            "table": table,
            "conditions": conditions,
        })
        self._filtro_widget = filtro

    def _build_section_esclusioni(self):
        if not self.app.active_builder:
            ttk.Label(self.section_content, text="Configura prima la sezione Base.").pack(pady=20)
            return
        try:
            config = self.app.active_builder.get_config()
        except Exception:
            ttk.Label(self.section_content, text="Questo tipo di controllo non supporta esclusioni.").pack(pady=20)
            return

        table = config.get("table", "")
        exclude_conditions = config.get("exclude_conditions", [])

        from ui_components import MultiConditionBuilder
        excl = MultiConditionBuilder(
            self.section_content, self.app.db,
            on_table_change=self.app._on_builder_table_change,
            title="Esclusioni (opzionale)"
        )
        excl.pack(fill=tk.BOTH, expand=True)
        excl.set_config({
            "table": table,
            "conditions": exclude_conditions,
        })
        self._esclusioni_widget = excl

    def _build_section_report(self):
        if hasattr(self, "col_selector"):
            self.col_selector.pack(in_=self.section_content, fill=tk.X, pady=5)
        else:
            ttk.Label(self.section_content, text="Nessun selettore colonne disponibile.").pack()

    def _build_section_periodicita(self):
        if not self.app.active_builder:
            ttk.Label(self.section_content, text="Configura prima la sezione Base.").pack(pady=20)
            return
        try:
            config = self.app.active_builder.get_config()
        except Exception:
            config = {}

        import ui_components
        from ui_components import PERIODIC_REVIEW_CYCLE_CHOICES

        frame = ttk.LabelFrame(self.section_content, text="Promemoria Aggiornamento Periodo", padding=12)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._var_periodic_enabled = tk.BooleanVar(
            value=bool(config.get("periodic_review_enabled", False))
        )
        self._var_periodic_cycle = tk.StringVar(
            value=self._cycle_display_from_key(config.get("periodic_review_cycle", "monthly"))
        )
        self._var_periodic_note = tk.StringVar(
            value=config.get("periodic_review_note", "")
        )
        self._var_periodic_last_ack = tk.StringVar(
            value=config.get("periodic_review_last_ack", "")
        )

        chk = ttk.Checkbutton(
            frame,
            text="Richiede aggiornamento periodico dei filtri",
            variable=self._var_periodic_enabled,
            command=self._toggle_periodic_fields,
        )
        chk.pack(anchor=tk.W, pady=(0, 10))

        cycle_row = ttk.Frame(frame)
        cycle_row.pack(fill=tk.X, pady=4)
        ttk.Label(cycle_row, text="Frequenza:").pack(side=tk.LEFT)
        self._cmb_periodic_cycle = ttk.Combobox(
            cycle_row,
            textvariable=self._var_periodic_cycle,
            state="readonly" if self._var_periodic_enabled.get() else tk.DISABLED,
            width=18,
            values=[label for label, _key in PERIODIC_REVIEW_CYCLE_CHOICES],
        )
        self._cmb_periodic_cycle.pack(side=tk.LEFT, padx=(8, 0))

        note_row = ttk.Frame(frame)
        note_row.pack(fill=tk.X, pady=(8, 4))
        ttk.Label(note_row, text="Nota promemoria:").pack(anchor=tk.W)
        self._ent_periodic_note = ttk.Entry(
            frame, textvariable=self._var_periodic_note,
            state=tk.NORMAL if self._var_periodic_enabled.get() else tk.DISABLED,
        )
        self._ent_periodic_note.pack(fill=tk.X, pady=(2, 0))

        last_ack_raw = self._var_periodic_last_ack.get()
        if last_ack_raw:
            try:
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(last_ack_raw)
                last_ack_text = dt.strftime("%d/%m/%Y %H:%M")
            except Exception:
                last_ack_text = last_ack_raw[:19]
        else:
            last_ack_text = "Mai"

        self._lbl_last_ack = ttk.Label(
            frame, text=f"Ultimo aggiornamento: {last_ack_text}",
            foreground="gray", font=("", 8, "italic"),
        )
        self._lbl_last_ack.pack(anchor=tk.W, pady=(10, 4))

        btn_mark = ttk.Button(
            frame, text="Segna come aggiornato ora",
            command=self._mark_periodic_ack,
            bootstyle="info-outline",
        )
        btn_mark.pack(anchor=tk.W, pady=4)

        ttk.Label(
            frame,
            text="Esempio: aggiornare il mese corrente prima di eseguire il batch.",
            foreground="gray", font=("", 8),
        ).pack(anchor=tk.W, pady=(4, 0))

        self._periodicita_data = {}

    def _sync_builder_from_sections(self):
        if not self.app.active_builder:
            return
        try:
            config = self.app.active_builder.get_config()
        except Exception:
            return

        if hasattr(self, "_filtro_widget"):
            filtri = self._filtro_widget.get_conditions()
            config["conditions"] = filtri

        if hasattr(self, "_esclusioni_widget"):
            esclusioni = self._esclusioni_widget.get_conditions()
            if esclusioni:
                config["exclude_conditions"] = esclusioni
            elif "exclude_conditions" in config:
                del config["exclude_conditions"]

        if hasattr(self, "_var_periodic_enabled"):
            enabled = self._var_periodic_enabled.get()
            periodic = {
                "periodic_review_enabled": enabled,
                "periodic_review_cycle": self._cycle_key_from_display() if enabled else "",
                "periodic_review_note": self._var_periodic_note.get().strip() if enabled else "",
                "periodic_review_last_ack": self._var_periodic_last_ack.get() if enabled else "",
            }
            self._periodicita_data = periodic
            config.update(periodic)

        try:
            self.app.active_builder.set_config(config)
        except Exception:
            pass

    def _cycle_display_from_key(self, cycle):
        import ui_components
        normalized = str(cycle or "").strip().lower()
        for label, key in ui_components.PERIODIC_REVIEW_CYCLE_CHOICES:
            if key == normalized:
                return label
        return ui_components.PERIODIC_REVIEW_CYCLE_CHOICES[-1][0]

    def _cycle_key_from_display(self):
        current = self._var_periodic_cycle.get().strip()
        for label, key in ui_components.PERIODIC_REVIEW_CYCLE_CHOICES:
            if label == current:
                return key
        return "monthly"

    def _toggle_periodic_fields(self):
        enabled = self._var_periodic_enabled.get()
        self._cmb_periodic_cycle.configure(
            state="readonly" if enabled else tk.DISABLED
        )
        self._ent_periodic_note.configure(
            state=tk.NORMAL if enabled else tk.DISABLED
        )

    def _mark_periodic_ack(self):
        from datetime import datetime
        now = datetime.now().isoformat()
        self._var_periodic_last_ack.set(now)
        self._lbl_last_ack.config(
            text=f"Ultimo aggiornamento: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        self.app.status.set("Aggiornamento periodico segnato come completato.")

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
