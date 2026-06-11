import tkinter as tk
from tkinter import ttk
import logging

import constants
from ui_components import (
    ColumnSelector, MultiConditionBuilder, PERIODIC_REVIEW_CYCLE_CHOICES,
)

logger = logging.getLogger("AccessDBTool.BuilderView")


class BuilderView(ttk.Frame):
    def __init__(self, parent, state, db_controller, library_controller=None, result_controller=None):
        super().__init__(parent)
        self.state = state
        self.db_ctrl = db_controller
        self.library_ctrl = library_controller
        self.result_ctrl = result_controller
        self._sections = {}
        self._filtro_widget = None
        self._esclusioni_widget = None
        self._periodicita_data = None
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

        self.accordion_frame = ttk.Frame(self)
        self.accordion_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self._create_accordion_section("base", "Base", expanded=True)
        self._create_accordion_section("filtri", "Filtri", expanded=False)
        self._create_accordion_section("esclusioni", "Esclusioni", expanded=False)
        self._create_accordion_section("report", "Colonne Report", expanded=False)
        self._create_accordion_section("periodicita", "Periodicit\u00e0", expanded=False)

        lib_frame = ttk.LabelFrame(self, text="Libreria", padding=6)
        lib_frame.pack(fill=tk.X)

        self.cmb_lib = ttk.Combobox(lib_frame, state="readonly", width=40)
        self.cmb_lib.pack(side=tk.LEFT, padx=4)
        ttk.Button(lib_frame, text="Carica",
                   command=self._load_from_lib,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)
        ttk.Button(lib_frame, text="Gestisci...",
                   command=self._open_manager,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)
        ttk.Button(lib_frame, text="Gruppi...",
                   command=self._open_groups,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        action_bar = ttk.Frame(self)
        action_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(action_bar, text="Pulisci",
                   command=self._clear_builder,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="Salva in Libreria",
                   command=self._save_to_lib,
                   bootstyle="success").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="Aggiorna Salvata",
                   command=self._update_to_lib,
                   bootstyle="warning").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="Esegui Controllo",
                   command=self._run_current,
                   bootstyle="danger").pack(side=tk.RIGHT, padx=2)

        self.frm_dyn = ttk.Frame(self)

        self.col_selector = ColumnSelector(self)
        self.col_selector.pack_forget()

    def _create_accordion_section(self, section_id, label, expanded=False):
        header = ttk.Button(
            self.accordion_frame, text=label,
            command=lambda: self._toggle_accordion(section_id),
            bootstyle="secondary-outline",
        )
        header.pack(fill=tk.X, pady=(2, 0))

        body = ttk.Frame(self.accordion_frame, padding=8)
        if expanded:
            body.pack(fill=tk.BOTH, expand=True)
        else:
            body.pack_forget()

        self._sections[section_id] = {
            "header": header,
            "body": body,
            "label": label,
            "expanded": expanded,
            "built": False,
        }

    def _toggle_accordion(self, section_id):
        section = self._sections[section_id]
        if section["expanded"]:
            self._sync_builder_from_sections()
            section["body"].pack_forget()
            section["expanded"] = False
            section["header"].configure(bootstyle="secondary-outline")
        else:
            if not section["built"]:
                self._build_section_content(section_id)
                section["built"] = True
            section["body"].pack(fill=tk.BOTH, expand=True)
            section["expanded"] = True
            section["header"].configure(bootstyle="primary")

    def _build_section_content(self, section_id):
        body = self._sections[section_id]["body"]
        if section_id == "base":
            self._build_section_base(body)
        elif section_id == "filtri":
            self._build_section_filtri(body)
        elif section_id == "esclusioni":
            self._build_section_esclusioni(body)
        elif section_id == "report":
            self._build_section_report(body)
        elif section_id == "periodicita":
            self._build_section_periodicita(body)

    def _build_section_base(self, body):
        if self.state.active_builder:
            try:
                self.state.active_builder.pack(in_=body, fill=tk.BOTH, expand=True)
            except Exception:
                ttk.Label(body, text="Seleziona un tipo analisi per iniziare.").pack()
        else:
            ttk.Label(body, text="Seleziona un tipo analisi per iniziare.").pack()

    def _build_section_filtri(self, body):
        if not self.state.active_builder:
            ttk.Label(body, text="Configura prima la sezione Base.").pack(pady=20)
            return
        try:
            config = self.state.active_builder.get_config()
        except Exception:
            ttk.Label(body, text="Questo tipo di controllo non supporta filtri aggiuntivi.").pack(pady=20)
            return

        table = config.get("table", "")
        conditions = config.get("conditions", [])

        filtro = MultiConditionBuilder(
            body, self.state.db,
            on_table_change=self._on_builder_table_change,
            title="Filtri (AND/OR)"
        )
        filtro.pack(fill=tk.BOTH, expand=True)
        filtro.set_config({
            "table": table,
            "conditions": conditions,
        })
        self._filtro_widget = filtro

    def _build_section_esclusioni(self, body):
        if not self.state.active_builder:
            ttk.Label(body, text="Configura prima la sezione Base.").pack(pady=20)
            return
        try:
            config = self.state.active_builder.get_config()
        except Exception:
            ttk.Label(body, text="Questo tipo di controllo non supporta esclusioni.").pack(pady=20)
            return

        table = config.get("table", "")
        exclude_conditions = config.get("exclude_conditions", [])

        excl = MultiConditionBuilder(
            body, self.state.db,
            on_table_change=self._on_builder_table_change,
            title="Esclusioni (opzionale)"
        )
        excl.pack(fill=tk.BOTH, expand=True)
        excl.set_config({
            "table": table,
            "conditions": exclude_conditions,
        })
        self._esclusioni_widget = excl

    def _build_section_report(self, body):
        if hasattr(self, "col_selector"):
            try:
                self.col_selector.pack(in_=body, fill=tk.X, pady=5)
            except Exception:
                ttk.Label(body, text="Nessun selettore colonne disponibile.").pack()
        else:
            ttk.Label(body, text="Nessun selettore colonne disponibile.").pack()

    def _build_section_periodicita(self, body):
        if not self.state.active_builder:
            ttk.Label(body, text="Configura prima la sezione Base.").pack(pady=20)
            return
        try:
            config = self.state.active_builder.get_config()
        except Exception:
            config = {}

        frame = ttk.LabelFrame(body, text="Promemoria Aggiornamento Periodo", padding=12)
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
        if not self.state.active_builder:
            return
        try:
            config = self.state.active_builder.get_config()
        except Exception:
            return

        if self._filtro_widget is not None:
            try:
                filtri = self._filtro_widget.get_conditions()
                config["conditions"] = filtri
            except Exception:
                pass

        if self._esclusioni_widget is not None:
            try:
                esclusioni = self._esclusioni_widget.get_conditions()
                if esclusioni:
                    config["exclude_conditions"] = esclusioni
                elif "exclude_conditions" in config:
                    del config["exclude_conditions"]
            except Exception:
                pass

        if hasattr(self, "_var_periodic_enabled"):
            try:
                enabled = self._var_periodic_enabled.get()
                periodic = {
                    "periodic_review_enabled": enabled,
                    "periodic_review_cycle": self._cycle_key_from_display() if enabled else "",
                    "periodic_review_note": self._var_periodic_note.get().strip() if enabled else "",
                    "periodic_review_last_ack": self._var_periodic_last_ack.get() if enabled else "",
                }
                self._periodicita_data = periodic
                config.update(periodic)
            except Exception:
                pass

        try:
            self.state.active_builder.set_config(config)
        except Exception:
            pass

    def _cycle_display_from_key(self, cycle):
        normalized = str(cycle or "").strip().lower()
        for label, key in PERIODIC_REVIEW_CYCLE_CHOICES:
            if key == normalized:
                return label
        return PERIODIC_REVIEW_CYCLE_CHOICES[-1][0]

    def _cycle_key_from_display(self):
        current = self._var_periodic_cycle.get().strip()
        for label, key in PERIODIC_REVIEW_CYCLE_CHOICES:
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
        self.state.status.set("Aggiornamento periodico segnato come completato.")

    def _on_ctype_change(self, _evt=None):
        ctype_name = self.cmb_ctype.get()
        rev = {v: k for k, v in constants.CONDITION_TYPES.items()}
        self.state.active_ctype = rev.get(ctype_name)
        self._update_builder_fields()
        self._show_base()

    def _on_builder_table_change(self, table):
        self.state.sel_tables = [table]
        if hasattr(self, "col_selector") and self.col_selector:
            self.col_selector.set_columns(self.state.db.columns(table))

    def _update_builder_fields(self):
        parent = self.frm_dyn
        if parent is None:
            return
        for w in parent.winfo_children():
            w.destroy()
        self.state.active_builder = None
        if not self.state.active_ctype:
            return

        ctype = self.state.active_ctype
        db = self.state.db
        import ui_components

        if ctype == "value_comparison":
            self.state.active_builder = ui_components.ValueComparisonBuilder(parent, db, self._on_builder_table_change)
        elif ctype == "duplicate_check":
            self.state.active_builder = ui_components.DuplicateBuilder(parent, db, self._on_builder_table_change)
        elif ctype == "similarity_check":
            self.state.active_builder = ui_components.SimilarityBuilder(parent, db, self._on_builder_table_change)
        elif ctype == "cross_table_existence":
            self.state.active_builder = ui_components.CrossTableBuilder(parent, db, self._on_builder_table_change)
        elif ctype == "formula_condition":
            self.state.active_builder = ui_components.FormulaBuilder(parent, db, self._on_builder_table_change)
        elif ctype == "concat_similarity":
            self.state.active_builder = ui_components.ConcatSimilarityBuilder(parent, db, self._on_builder_table_change)
        elif ctype == "linked_table_intersection":
            self.state.active_builder = ui_components.LinkedTableBuilder(parent, db, self._on_builder_table_change)
            if self.state.sel_tables:
                self.state.active_builder.sec1.set_table(self.state.sel_tables[0])
            if len(self.state.sel_tables) > 1:
                self.state.active_builder.sec2.set_table(self.state.sel_tables[1])
        elif ctype == "format_validation":
            try:
                self.state.active_builder = ui_components.FormatValidationBuilder(parent, db, self._on_builder_table_change)
            except Exception as _e:
                logger.error(f"FormatValidationBuilder init error: {_e}")
                self.state.status.set(f"Errore builder: {_e}")
        elif ctype == "daily_coverage_check":
            try:
                self.state.active_builder = ui_components.DailyCoverageBuilder(parent, db, self._on_builder_table_change)
            except Exception as _e:
                logger.error(f"DailyCoverageBuilder init error: {_e}")
                self.state.status.set(f"Errore builder: {_e}")
        elif ctype == "mandatory_record_check":
            try:
                self.state.active_builder = ui_components.MandatoryRecordBuilder(parent, db, self._on_builder_table_change)
            except Exception as _e:
                logger.error(f"MandatoryRecordBuilder init error: {_e}")
                self.state.status.set(f"Errore builder: {_e}")
        elif ctype == "dependent_condition_check":
            try:
                self.state.active_builder = ui_components.DependentConditionBuilder(parent, db, self._on_builder_table_change)
            except Exception as _e:
                logger.error(f"DependentConditionBuilder init error: {_e}")
                self.state.status.set(f"Errore builder: {_e}")
        elif ctype == "row_cross_column_check":
            try:
                self.state.active_builder = ui_components.RowCrossColumnBuilder(parent, db, self._on_builder_table_change)
            except Exception as _e:
                logger.error(f"RowCrossColumnBuilder init error: {_e}")
                self.state.status.set(f"Errore builder: {_e}")
        elif ctype == "lookup_validation":
            try:
                self.state.active_builder = ui_components.LookupValidationBuilder(parent, db, self._on_builder_table_change)
            except Exception as _e:
                logger.error(f"LookupValidationBuilder init error: {_e}")
                self.state.status.set(f"Errore builder: {_e}")
        elif ctype == "aggregate_threshold_check":
            try:
                self.state.active_builder = ui_components.AggregateThresholdBuilder(parent, db, self._on_builder_table_change)
            except Exception as _e:
                logger.error(f"AggregateThresholdBuilder init error: {_e}")
                self.state.status.set(f"Errore builder: {_e}")

        if self.state.active_builder:
            self.state.active_builder.pack(fill=tk.BOTH, expand=True)
        elif parent.winfo_ismapped():
            ttk.Label(parent, text=f"Configurazione standard per: {self.cmb_ctype.get()}").pack()

    def _show_base(self):
        base = self._sections["base"]
        for w in base["body"].winfo_children():
            w.destroy()
        base["built"] = False
        if not base["expanded"]:
            base["body"].pack(fill=tk.BOTH, expand=True)
            base["expanded"] = True
            base["header"].configure(bootstyle="primary")
        self._build_section_base(base["body"])
        base["built"] = True

    def load_condition(self, cond):
        """Carica una condizione (dict) nel builder: costruisce il widget del
        tipo corretto e ne applica la configurazione. Usato sia dal pulsante
        'Carica' della libreria sia dall'apertura nel builder dalla dashboard."""
        if not cond:
            return
        # Tabella della condizione: deve restare collegata al builder, altrimenti
        # le modifiche (es. aggiungere un filtro) partono senza tabella.
        table = cond.get("table") or (cond.get("tables", [""])[0] if cond.get("tables") else "")
        if table:
            self.state.sel_tables = [table]
        if self.library_ctrl:
            self.library_ctrl.load_cond_into_builder(cond)
        self.sync_ctype()
        self._on_ctype_change()
        if self.state.active_builder and hasattr(self.state.active_builder, "set_config"):
            # 'table' e 'display_columns' RESTANO nel config: i builder leggono
            # c.get("table")/c.get("tables") per ripristinare la tabella.
            config = {k: v for k, v in cond.items()
                      if k not in ("name", "description", "tag", "type",
                                    "saved_at", "updated_at",
                                    "database_label", "_group_name")}
            try:
                self.state.active_builder.set_config(config)
            except Exception as e:
                logger.warning("set_config in load_condition fallita: %s", e)
        # Allinea il selettore colonne report alla tabella ripristinata.
        if table and getattr(self, "col_selector", None) and self.state.db:
            try:
                self.col_selector.set_columns(self.state.db.columns(table))
                disp = cond.get("display_columns") or []
                if disp:
                    self.col_selector.set_selected(disp)
            except Exception as e:
                logger.warning("aggiornamento col_selector in load_condition fallito: %s", e)

    def _load_from_lib(self):
        if not self.library_ctrl:
            return
        sel = self.cmb_lib.get()
        if not sel:
            return
        for cond in self.state.store.items:
            if cond.get("name") == sel:
                self.load_condition(cond)
                break

    def _clear_builder(self):
        for w in self.frm_dyn.winfo_children():
            w.destroy()
        self.state.active_builder = None
        self.state.active_ctype = None
        self.cmb_ctype.set("")
        self.state.var_saved.set("")
        self.state.var_ctype.set("")
        self.state.loaded_condition_idx = None
        for section_id in list(self._sections.keys()):
            section = self._sections[section_id]
            for w in section["body"].winfo_children():
                w.destroy()
            section["built"] = False

    def _open_manager(self):
        if self.library_ctrl:
            self.library_ctrl.open_manager()

    def _open_groups(self):
        if self.library_ctrl:
            self.library_ctrl.open_groups()

    def _save_to_lib(self):
        if not self.library_ctrl:
            return
        ctype = self.state.active_ctype
        if not ctype:
            from tkinter import messagebox
            return messagebox.showwarning("!", "Seleziona tipo analisi")
        self._sync_builder_from_sections()
        config = self.state.active_builder.get_config() if self.state.active_builder else {}
        display_cols = self.col_selector.get_selected() if hasattr(self, "col_selector") else []
        from ui_components import ConditionSaveDialog
        dialog = ConditionSaveDialog(
            None, self.state.store,
            default_name=self.state.var_saved.get(),
            force_new=False,
        )
        if not dialog.result:
            return
        self.library_ctrl.save_to_lib(
            dialog.result["name"],
            dialog.result.get("description", ""),
            dialog.result.get("tag", "").strip(),
            ctype, config, display_cols,
            self._periodicita_data or {},
        )
        self.refresh_lib()

    def _update_to_lib(self):
        if not self.library_ctrl:
            return
        self._sync_builder_from_sections()
        ctype = self.state.active_ctype
        config = self.state.active_builder.get_config() if self.state.active_builder else {}
        display_cols = self.col_selector.get_selected() if hasattr(self, "col_selector") else []
        self.library_ctrl.update_to_lib(ctype, config, display_cols)
        self.refresh_lib()

    def _run_current(self):
        if not self.result_ctrl:
            return
        display_cols = self.col_selector.get_selected() if hasattr(self, "col_selector") else []
        self.result_ctrl.run_current(display_cols)

    def refresh_lib(self):
        names = self.state.store.names()
        self.cmb_lib["values"] = names
        if self.state.var_saved.get() not in names:
            self.state.var_saved.set("")

    def sync_ctype(self):
        if self.state.active_ctype:
            ctype_label = constants.CONDITION_TYPES.get(self.state.active_ctype, "")
            if ctype_label:
                self.cmb_ctype.set(ctype_label)
