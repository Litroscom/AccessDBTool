import tkinter as tk
import ttkbootstrap as ttk
import logging

import constants
from ui_components import (
    ColumnSelector, MultiConditionBuilder, PERIODIC_REVIEW_CYCLE_CHOICES,
)
from views.results_view import ResultsView

logger = logging.getLogger("AccessDBTool.BuilderView")


class BuilderView(ttk.Frame):
    def __init__(self, parent, state, db_controller, library_controller=None, result_controller=None):
        super().__init__(parent)
        self.state = state
        self.db_ctrl = db_controller
        self.library_ctrl = library_controller
        self.result_ctrl = result_controller or getattr(state, "result_ctrl", None)
        self._sections = {}
        self._filtro_widget = None
        self._periodicita_data = None
        self._build_ui()

    def _build_ui(self):
        # ============================================================
        # Barra superiore: tipo di analisi + stato database
        # ============================================================
        top = ttk.Frame(self)
        top.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(top, text="Tipo Analisi:", font=("", 9, "bold")).pack(side=tk.LEFT)
        self.cmb_ctype = ttk.Combobox(
            top, values=list(constants.CONDITION_TYPES.values()),
            state="readonly", width=38
        )
        self.cmb_ctype.pack(side=tk.LEFT, padx=8)
        self.cmb_ctype.bind("<<ComboboxSelected>>", self._on_ctype_change)

        self.lbl_db_hint = ttk.Label(top, text="", font=("", 8))
        self.lbl_db_hint.pack(side=tk.RIGHT, padx=4)

        # ============================================================
        # Area principale: modulo di configurazione (sopra) + risultati (sotto).
        # Il flusso è lineare: configura -> esegui -> vedi i risultati qui sotto.
        # ============================================================
        paned = ttk.Panedwindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        form_container = ttk.Frame(paned)
        paned.add(form_container, weight=3)

        # Canvas scrollabile: le sezioni sono SEMPRE visibili (niente accordion
        # collassabile che nascondeva la configurazione essenziale).
        self.form_canvas = tk.Canvas(form_container, borderwidth=0, highlightthickness=0)
        self.form_scrollbar = ttk.Scrollbar(form_container, orient=tk.VERTICAL, command=self.form_canvas.yview)
        self.form_frame = ttk.Frame(self.form_canvas)
        self.form_frame.bind("<Configure>", lambda _e: self._update_scrollregion())
        self.form_canvas.create_window((0, 0), window=self.form_frame, anchor="nw", tags="form_frame")
        self.form_canvas.configure(yscrollcommand=self.form_scrollbar.set)
        self.form_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.form_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.form_canvas.bind("<Configure>", lambda _e: self._update_scrollregion(), add="+")
        self.form_canvas.bind("<Enter>", lambda _e: self._bind_mousewheel())
        self.form_canvas.bind("<Leave>", lambda _e: self._unbind_mousewheel())

        # Sezioni in ordine di flusso, numerate per chiarezza
        self._create_section("base",        "1 \u00b7 Configurazione del controllo")
        self._create_section("filtri",      "2 \u00b7 Filtri aggiuntivi (facoltativi)")
        self._create_section("report",      "3 \u00b7 Colonne da mostrare nel report")
        self._create_section("periodicita", "4 \u00b7 Promemoria di aggiornamento (facoltativo)")
        for section_id in ("base", "filtri", "report", "periodicita"):
            self._build_section_content(section_id)
            self._sections[section_id]["built"] = True

        # Risultati incorporati: esegui un controllo e li vedi qui sotto
        results_container = ttk.Frame(paned)
        paned.add(results_container, weight=2)
        self.results_view = ResultsView(
            results_container, self.state, self.result_ctrl,
            enable_fullscreen=False,
        )
        self.results_view.pack(fill=tk.BOTH, expand=True)

        # ============================================================
        # Libreria: condizioni salvate
        # ============================================================
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

        # ============================================================
        # Barra azioni
        # ============================================================
        action_bar = ttk.Frame(self)
        action_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(
            action_bar,
            text="1) Scegli il tipo \u00b7 2) Configura \u00b7 3) Esegui (Alt+R) — i risultati compaiono qui sotto",
            foreground="gray", font=("", 8),
        ).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_bar, text="Pulisci",
                   command=self._clear_builder,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="Salva in Libreria",
                   command=self._save_to_lib,
                   bootstyle="success").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="Aggiorna Salvata",
                   command=self._update_to_lib,
                   bootstyle="warning").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="\u25b6 Esegui Controllo (Alt+R)",
                   command=self._run_current,
                   bootstyle="danger").pack(side=tk.RIGHT, padx=2)

    def _create_section(self, section_id, label):
        """Crea una sezione sempre visibile (titolo + corpo). La struttura
        interna (dict _sections) resta compatibile con i metodi di
        sincronizzazione esistenti."""
        header = ttk.Label(
            self.form_frame, text=label, font=("", 9, "bold"),
            bootstyle="primary", padding=(6, 4),
        )
        header.pack(fill=tk.X, pady=(4, 0))

        body = ttk.Frame(self.form_frame, padding=(8, 2, 8, 8))
        body.pack(fill=tk.BOTH, expand=True)

        self._sections[section_id] = {
            "header": header,
            "body": body,
            "label": label,
            "expanded": True,
            "built": False,
        }

    def _bind_mousewheel(self):
        self.form_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self):
        self.form_canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.form_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _update_scrollregion(self):
        """Aggiorna la scrollregion del canvas in base al contenuto attuale."""
        try:
            if self.form_canvas.winfo_exists():
                width = self.form_canvas.winfo_width()
                if width > 1:
                    self.form_canvas.itemconfig("form_frame", width=width)
                self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all"))
        except Exception as e:
            logger.debug("_update_scrollregion errore: %s", e)

    def _sync_accordion_from_builder(self):
        """Dopo set_config(), aggiorna i widget accordion Filtri/Esclusioni
        con i dati correnti del builder attivo. Se i widget non esistono ancora
        (es. prima apertura), forza la costruzione della sezione."""
        if not self.state.active_builder:
            return
        config = self.state.active_builder.get_config()
        table = config.get("table", "")
        # Filtri
        if self._filtro_widget is not None:
            try:
                self._filtro_widget.set_config({
                    "table": table,
                    "conditions": config.get("conditions", []),
                })
            except Exception:
                pass
        elif self._sections.get("filtri", {}).get("expanded"):
            # Sezione espansa ma widget perso: ricostruisci
            section = self._sections["filtri"]
            for w in section["body"].winfo_children():
                w.destroy()
            section["built"] = False
            self._build_section_content("filtri")
            section["built"] = True
        # Nota: le esclusioni sono gestite inline da ogni builder (pulsante
        # "+ Esclusione" contestuale), quindi non esiste piu' una sezione
        # accordion dedicata che duplicava quell'UI.

    def _toggle_accordion(self, section_id):
        """Compat: le sezioni sono sempre visibili in Beta, niente da fare."""
        self._update_scrollregion()

    def _build_section_content(self, section_id):
        body = self._sections[section_id]["body"]
        if section_id == "base":
            self._build_section_base(body)
        elif section_id == "filtri":
            self._build_section_filtri(body)
        elif section_id == "report":
            self._build_section_report(body)
        elif section_id == "periodicita":
            self._build_section_periodicita(body)

    def _build_section_base(self, body):
        if self.state.active_builder:
            # Il builder è stato creato con parent=body (vedi _update_builder_fields):
            # pack normale, MAI pack(in_=...) su un widget creato altrove (TclError).
            self.state.active_builder.pack(fill=tk.BOTH, expand=True)
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

        # Questi controlli definiscono la propria logica (formula / SE...ALLORA):
        # mostrare un builder di filtri vuoto sarebbe fuorviante.
        if self.state.active_ctype in ("formula_condition", "dependent_condition_check"):
            ttk.Label(
                body,
                text="Questo controllo definisce la propria logica (formula SQL / SE...ALLORA):\n"
                     "non sono necessari filtri aggiuntivi.",
                foreground="gray", justify=tk.LEFT,
            ).pack(pady=16, padx=4)
            return

        table = config.get("table", "")
        conditions = config.get("conditions", [])

        filtro = MultiConditionBuilder(
            body, self.state.db,
            on_table_change=self._on_builder_table_change,
            title="Filtri (AND/OR)",
            show_table=False,
        )
        filtro.pack(fill=tk.BOTH, expand=True)
        filtro.set_config({
            "table": table,
            "conditions": conditions,
        })
        self._filtro_widget = filtro

    def _build_section_report(self, body):
        # Il ColumnSelector va creato nel parent finale (body): pack(in_=...)
        # su un widget creato con altro parent solleva TclError (skill imparata).
        sel = getattr(self, "col_selector", None)
        if sel is None or not sel.winfo_exists():
            self.col_selector = ColumnSelector(body)
            sel = self.col_selector
        try:
            sel.pack(fill=tk.X, pady=5)
        except Exception:
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

        # Le esclusioni sono gestite inline da ogni builder (pulsante
        # "+ Esclusione" contestuale): niente da sincronizzare qui.

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
        # Ordine corretto: si distrugge il builder precedente e si crea il
        # nuovo con parent=body (riparentarlo con pack(in_=...) è TclError).
        self.state.active_builder = None
        self._update_builder_fields()
        self._invalidate_accordion_sections()

    def _on_builder_table_change(self, table):
        self.state.sel_tables = [table]
        # I filtri dell'accordion ereditano la tabella dal builder principale.
        # Senza questo allineamento si potevano selezionare colonne di una
        # tabella e applicarle poi alla precedente al momento dell'esecuzione.
        if self._filtro_widget is not None:
            try:
                if self._filtro_widget.var_table.get() != table:
                    self._filtro_widget.set_table(table)
            except Exception as e:
                logger.debug("sincronizzazione tabella filtri fallita: %s", e)
        if hasattr(self, "col_selector") and self.col_selector and self.state.db:
            # Preserva le selezioni correnti: set_columns distrugge e ricrea
            # tutte le checkbox, ma vogliamo mantenere le scelte dell'utente.
            old_selected = self.col_selector.get_selected()
            self.col_selector.set_columns(self.state.db.columns(table))
            if old_selected:
                self.col_selector.set_selected(old_selected)

    def _update_builder_fields(self):
        # Il builder viene creato DIRETTAMENTE nel body della sezione "base"
        # (parent finale): niente pack(in_=...) che fallirebbe con TclError.
        self.state.active_builder = None
        if not self.state.active_ctype:
            return

        ctype = self.state.active_ctype
        db = self.state.db
        import ui_components

        base_section = self._sections.get("base")
        parent = base_section["body"] if base_section else self
        # Rimuove placeholder/vecchi widget dal body prima di inserire il
        # builder (es. il placeholder "Seleziona un tipo analisi...").
        for w in parent.winfo_children():
            w.destroy()

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
        elif ctype == "aggregate_multi_table_threshold":
            try:
                self.state.active_builder = ui_components.AggregateMultiTableBuilder(parent, db, self._on_builder_table_change)
            except Exception as _e:
                logger.error(f"AggregateMultiTableBuilder init error: {_e}")
                self.state.status.set(f"Errore builder: {_e}")

        # Il builder è già figlio del body della sezione "base": pack normale.
        if self.state.active_builder is not None:
            try:
                self.state.active_builder.pack(fill=tk.BOTH, expand=True)
            except Exception as _e:
                logger.error("pack del builder fallito: %s", _e)
        self._update_scrollregion()

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
        self._update_scrollregion()

    def load_condition(self, cond):
        """Carica una condizione (dict) nel builder: costruisce il widget del
        tipo corretto e ne applica la configurazione. Usato sia dal pulsante
        'Carica' della libreria sia dall'apertura nel builder dalla dashboard."""
        if not cond:
            return
        # Tabella della condizione: deve restare collegata al builder, altrimenti
        # le modifiche (es. aggiungere un filtro) partono senza tabella.
        table = cond.get("table") or cond.get("source_table") or (cond.get("tables", [""])[0] if cond.get("tables") else "")
        if table:
            self.state.sel_tables = [table]
        if self.library_ctrl:
            self.library_ctrl.load_cond_into_builder(cond)
        self.sync_ctype()
        self._invalidate_accordion_sections()
        self._on_ctype_change()
        if self.state.active_builder and hasattr(self.state.active_builder, "set_config"):
            # 'table' e 'display_columns' RESTANO nel config: i builder leggono
            # c.get("table")/c.get("tables") per ripristinare la tabella.
            config = {k: v for k, v in cond.items()
                      if k not in ("name", "description", "tag", "type",
                                    "saved_at", "updated_at",
                                    "database_label", "_group_name")}
            logger.info("load_condition: tipo=%s, table=%s, has exceptions=%s, has exclude_conditions=%s",
                        cond.get("type"), table, bool(config.get("exceptions")), bool(config.get("exclude_conditions")))
            try:
                self.state.active_builder.set_config(config)
                cfg_after = self.state.active_builder.get_config()
                logger.info("load_condition: dopo set_config, exclude_conditions=%s, exceptions=%s",
                            cfg_after.get("exclude_conditions"), cfg_after.get("exceptions", [])[:5])
            except Exception as e:
                logger.warning("set_config in load_condition fallita: %s", e)
        # Dopo set_config, sincronizza i widget accordion (Filtri/Esclusioni)
        # con i dati appena caricati nel builder
        self._sync_accordion_from_builder()
        # Allinea il selettore colonne report alla tabella ripristinata.
        if table and getattr(self, "col_selector", None) and self.state.db:
            try:
                self.col_selector.set_columns(self.state.db.columns(table))
                disp = cond.get("display_columns") or []
                if disp:
                    self.col_selector.set_selected(disp)
            except Exception as e:
                logger.warning("aggiornamento col_selector in load_condition fallito: %s", e)
        # Auto-espandi le sezioni accordion che contengono dati
        self._auto_expand_sections(cond)
        # Forza aggiornamento scrollregion dopo aver caricato tutto
        self.after(100, self._update_scrollregion)

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
        if self.state.active_builder:
            self.state.active_builder.destroy()
        self.state.active_builder = None
        self.state.active_ctype = None
        self.cmb_ctype.set("")
        self.state.var_saved.set("")
        self.state.var_ctype.set("")
        self.state.loaded_condition_idx = None
        # Ricostruisci subito le sezioni con il placeholder (sezioni sempre
        # visibili: non restano vuote dopo "Pulisci").
        self._filtro_widget = None
        for section_id in list(self._sections.keys()):
            section = self._sections[section_id]
            for w in section["body"].winfo_children():
                w.destroy()
            self._build_section_content(section_id)
            section["built"] = True
        self._update_scrollregion()

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
        # display_cols = None se il selettore colonne non è stato inizializzato
        # (es. nessuna tabella caricata), così update_to_lib non cancella le
        # display_columns esistenti.
        if hasattr(self, "col_selector") and self.col_selector.col_vars:
            display_cols = self.col_selector.get_selected()
        else:
            display_cols = None
        self.library_ctrl.update_to_lib(ctype, config, display_cols)
        self.refresh_lib()

    def _run_current(self):
        if not self.result_ctrl:
            return
        self._sync_builder_from_sections()
        display_cols = self.col_selector.get_selected() if hasattr(self, "col_selector") else []
        self.result_ctrl.run_current(display_cols)

    def show_results(self, res):
        """Delega al pannello risultati incorporato (chiamato dal controller)."""
        if hasattr(self, "results_view") and self.results_view is not None:
            self.results_view.show_results(res)

    def refresh(self):
        """Aggiorna gli stati dipendenti dal DB aperto (chiamato dall'App)."""
        self._refresh_db_hint()

    def _refresh_db_hint(self):
        if not hasattr(self, "lbl_db_hint"):
            return
        db = getattr(self.state, "db", None)
        if db is not None and getattr(db, "connected", False):
            self.lbl_db_hint.config(
                text=f"Database: {self.state.current_db_label or db.db_path}",
                foreground="#2E7D32",
            )
        else:
            self.lbl_db_hint.config(
                text="Nessun database aperto — vai nel tab Database e apri il file",
                foreground="#B71C1C",
            )

    def refresh_lib(self):
        names = self.state.store.names()
        self.cmb_lib["values"] = names
        if self.state.var_saved.get() not in names:
            self.state.var_saved.set("")

    def _invalidate_accordion_sections(self):
        """Ricostruisce SUBITO le sezioni dipendenti dal builder attivo
        (filtri, periodicità). In Beta le sezioni sono sempre visibili:
        niente costruzione lazy al toggle, quindi si ricostruisce qui."""
        self._filtro_widget = None
        for section_id in ("filtri", "periodicita"):
            section = self._sections.get(section_id)
            if section is None:
                continue
            for w in section["body"].winfo_children():
                w.destroy()
            self._build_section_content(section_id)
            section["built"] = True
        self._update_scrollregion()

    def _auto_expand_sections(self, cond):
        """Compat: in Beta le sezioni sono sempre visibili; assicura solo che
        il contenuto sia costruito (utile al primo caricamento di una
        condizione salvata)."""
        for section_id in ("filtri", "periodicita"):
            section = self._sections.get(section_id)
            if section is None:
                continue
            if not section["built"]:
                self._build_section_content(section_id)
                section["built"] = True
        self._update_scrollregion()

    def sync_ctype(self):
        if self.state.active_ctype:
            ctype_label = constants.CONDITION_TYPES.get(self.state.active_ctype, "")
            if ctype_label:
                self.cmb_ctype.set(ctype_label)
