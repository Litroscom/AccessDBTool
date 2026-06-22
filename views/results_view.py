import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import logging

logger = logging.getLogger("AccessDBTool.ResultsView")


class ResultsView(ttk.Frame):
    def __init__(self, parent, state, result_controller, enable_fullscreen=True):
        super().__init__(parent)
        self.state = state
        self.result_ctrl = result_controller
        self._current_title = ""
        self._on_context_menu = None
        self._on_open_in_builder = None
        self._enable_fullscreen = enable_fullscreen
        self._build_ui()

    def set_context_menu_callback(self, callback):
        self._on_context_menu = callback

    def set_open_in_builder_callback(self, callback):
        self._on_open_in_builder = callback

    def _build_ui(self):
        self._build_action_bar()

        filter_frame = ttk.Frame(self, padding=6)
        filter_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.res_lbl = ttk.Label(filter_frame, text="Nessun risultato", font=("", 10, "bold"))
        self.res_lbl.pack(side=tk.LEFT)

        ttk.Label(filter_frame, text="Filtra:").pack(side=tk.RIGHT, padx=(0, 4))
        self.var_filter = tk.StringVar()
        self.entry_filter = ttk.Entry(filter_frame, textvariable=self.var_filter, width=25)
        self.entry_filter.pack(side=tk.RIGHT, padx=4)
        self.entry_filter.bind("<KeyRelease>", self._apply_filter)

        tree_frame = ttk.Frame(self, padding=4)
        tree_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        self.res_tree = ttk.Treeview(tree_frame, show="headings", selectmode="extended")
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.res_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.res_tree.xview)
        self.res_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.res_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.res_tree.tag_configure("error", foreground="#ffb3b3")
        self.res_tree.tag_configure("ok", foreground="#b3ffcc")

        self.res_tree.bind("<Button-3>", self._on_right_click)

    def _build_action_bar(self):
        action_frame = ttk.Frame(self, padding=4)
        action_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(action_frame, text="Esporta CSV",
                   command=self._export_csv,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        ttk.Button(action_frame, text="Modifica record",
                   command=self._edit_record,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        ttk.Button(action_frame, text="Sost. massiva",
                   command=self._bulk_replace,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        ttk.Button(action_frame, text="Aggiungi a esclusioni",
                   command=self._add_to_exclusions,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        ttk.Button(action_frame, text="Apri nel builder",
                   command=self._open_in_builder,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        if self._enable_fullscreen:
            ttk.Button(action_frame, text="Apri a tutta pagina",
                       command=self._open_fullscreen,
                       bootstyle="info-outline").pack(side=tk.LEFT, padx=2)

    def _on_right_click(self, event):
        iid = self.res_tree.identify_row(event.y)
        if iid and iid not in self.res_tree.selection():
            self.res_tree.selection_add(iid)
            self.res_tree.focus(iid)
        if self._on_context_menu:
            self._on_context_menu(event)
        else:
            self._show_res_menu(event)

    def _selected_rows(self):
        return [self.res_tree.item(iid, "values") for iid in self.res_tree.selection()]

    def _selected_indices(self):
        out = []
        for iid in self.res_tree.selection():
            try:
                out.append(int(iid))
            except (TypeError, ValueError):
                continue
        return out

    def _column_from_event(self, event):
        res = self.state.current_result
        if not res:
            return ""
        col_id = self.res_tree.identify_column(event.x)
        if not col_id or col_id == "#0":
            return ""
        try:
            idx = int(str(col_id).lstrip("#")) - 1
        except ValueError:
            return ""
        cols = res.get("columns", [])
        return cols[idx] if 0 <= idx < len(cols) else ""

    def _show_res_menu(self, event):
        res = self.state.current_result
        if not res:
            return
        builder = self.state.active_builder
        m = tk.Menu(self, tearoff=0)
        edit_state = tk.NORMAL if self.result_ctrl.result_supports_direct_update() else tk.DISABLED
        m.add_command(label="Modifica record...", command=self._edit_record, state=edit_state)
        m.add_separator()
        m.add_command(label="Sostituzione Massiva...", command=self._bulk_replace, state=edit_state)
        # Le esclusioni non richiedono un builder vivo: se manca, i gestori
        # aprono la condizione nel builder portando la selezione.
        if res.get("_condition") or (builder and hasattr(builder, "add_exceptions")):
            ctype = self.result_ctrl._current_result_condition_type()
            if ctype != "concat_similarity":
                m.add_separator()
                if ctype == "similarity_check":
                    sim = tk.Menu(m, tearoff=0)
                    sim.add_command(label="Escludi coppia per sempre (valori)",
                                    command=lambda: self._add_similarity("pair_values"))
                    sim.add_command(label="Escludi coppia specifica di record",
                                    command=lambda: self._add_similarity("pair_records"))
                    sim.add_separator()
                    sim.add_command(label="Escludi record sinistri selezionati",
                                    command=lambda: self._add_similarity("left_records"))
                    sim.add_command(label="Escludi record destri selezionati",
                                    command=lambda: self._add_similarity("right_records"))
                    m.add_cascade(label="Esclusioni Somiglianze", menu=sim)
                else:
                    clicked = self._column_from_event(event)
                    target = self.result_ctrl.resolve_non_fuzzy_exception_target(clicked)
                    label = f"Aggiungi '{target}' selezionati a Esclusioni" if target else "Aggiungi Selezionati a Esclusioni"
                    m.add_command(label=label, command=lambda col=target: self._add_nonfuzzy(col))
        m.post(event.x_root, event.y_root)

    def _apply_filter(self, _evt=None):
        query = self.var_filter.get().lower()
        res = self.state.current_result
        if not res:
            return
        rows = res.get("rows", [])
        self.res_tree.delete(*self.res_tree.get_children())
        count = 0
        for i, r in enumerate(rows):
            if not query:
                self.res_tree.insert("", tk.END, iid=str(i), values=r)
                count += 1
            else:
                for val in r:
                    if query in str(val).lower():
                        self.res_tree.insert("", tk.END, iid=str(i), values=r)
                        count += 1
                        break

        self.res_lbl.config(
            text=f"{res.get('title', '?')} ({count} filtrati su {len(rows)})"
        )

    def show_results(self, res):
        if not res:
            return
        count = res.get("count", 0)
        self.res_lbl.config(text=f"{res.get('title', '?')} ({count} record)")
        self.res_tree.delete(*self.res_tree.get_children())
        self.res_tree["columns"] = res.get("columns", [])
        for c in res.get("columns", []):
            self.res_tree.heading(c, text=c)
            self.res_tree.column(c, width=150)

        row_tag = "error" if isinstance(count, (int, float)) and count > 0 else "ok"
        for i, r in enumerate(res.get("rows", [])):
            self.res_tree.insert("", tk.END, iid=str(i), values=r, tags=(row_tag,))

        self._current_title = res.get("title", "")

    def _export_csv(self):
        self.result_ctrl.export_csv()

    def _edit_record(self):
        if not self.result_ctrl.result_supports_direct_update():
            return messagebox.showwarning(
                "Operazione non disponibile",
                "La modifica diretta è disponibile solo per risultati mappabili a una singola tabella.",
            )
        res = self.state.current_result
        sel = self._selected_indices()
        if not sel:
            return messagebox.showwarning("Attenzione", "Seleziona una riga.")
        rows = res.get("rows", [])
        cols = res.get("columns", [])
        if sel[0] >= len(rows):
            return
        table = res.get("source_table")
        if not table:
            return messagebox.showerror("Errore", "Tabella sorgente non identificata.")
        data = dict(zip(cols, rows[sel[0]]))
        from ui_components import RecordEditorDialog
        dlg = RecordEditorDialog(self.winfo_toplevel(), self.state.db, table, data)
        self.wait_window(dlg)
        self.state.status.set("Record modificato. Riesegui il controllo per aggiornare la vista.")

    def _bulk_replace(self):
        if not self.result_ctrl.result_supports_direct_update():
            return messagebox.showwarning(
                "Operazione non disponibile",
                "La sostituzione massiva è disponibile solo per risultati che mappano in modo univoco a una singola tabella.",
            )
        res = self.state.current_result
        rows = res.get("rows", []) if res else []
        if not rows:
            return messagebox.showwarning("!", "Nessun record presente nei risultati.")
        import ui_components
        dlg = ui_components.BulkReplaceDialog(self.winfo_toplevel(), res.get("columns", []), len(rows))
        self.wait_window(dlg)
        if not dlg.result:
            return
        visible = []
        for iid in self.res_tree.get_children():
            try:
                visible.append(int(iid))
            except (TypeError, ValueError):
                continue
        updated = self.result_ctrl.apply_bulk_replace(dlg.result, visible)
        if updated == -1:
            return messagebox.showwarning(
                "Operazione annullata",
                "Impossibile identificare con certezza la colonna chiave (PK) del risultato.\n"
                "La sostituzione massiva è stata annullata per evitare modifiche su righe errate.",
            )
        messagebox.showinfo("Successo", f"Aggiornamento completato.\n{updated} record modificati su {len(visible)} filtrati.")
        self.state.status.set(f"Ultima operazione: Sostituzione massiva ({updated} record).")
        self._apply_filter()

    def _builder_live(self):
        """True solo se esiste un builder ancora valido (widget non distrutto).
        Sulla dashboard il builder viene distrutto al cambio tab, quindi qui
        risulta quasi sempre falso e le esclusioni passano per l'apertura nel
        builder."""
        builder = self.state.active_builder
        try:
            return bool(builder) and builder.winfo_exists()
        except Exception:
            return False

    def _route_exclusion_to_builder(self, pending):
        """Senza builder vivo: apre la condizione nel builder portando con sé
        la selezione, così l'utente la gestisce nel tab Controlli."""
        res = self.state.current_result
        cond = res.get("_condition") if res else None
        if cond and self._on_open_in_builder:
            self._on_open_in_builder(cond, pending)
        else:
            messagebox.showwarning(
                "!", "Apri il controllo nel builder per gestire le esclusioni.",
            )

    def _add_similarity(self, mode):
        res = self.state.current_result
        if not res:
            return
        rows = self._selected_rows()
        if not rows:
            return messagebox.showwarning("Attenzione", "Seleziona almeno una riga.")
        cols = res.get("columns", [])
        if self._builder_live():
            builder = self.state.active_builder
            key_col = builder.get_exception_column() if hasattr(builder, "get_exception_column") else ""
            # Per le modalita' 'record' (sinistro/destro) serve la colonna
            # chiave (ID) del builder, non la colonna confrontata (nome):
            # se key_column non e' impostata, l'ID verrebbe scritto come
            # esclusione sulla colonna nome, che e' semantically errato.
            if mode in ("left_records", "right_records") and hasattr(builder, "var_key"):
                key_col = builder.var_key.get().strip() or key_col
                if not builder.var_key.get().strip():
                    messagebox.showwarning(
                        "Colonna chiave mancante",
                        "Per escludere record per ID (modalita' sinistro/destro) "
                        "imposta la 'Colonna chiave (ID)' nel builder, oppure "
                        "usa 'Escludi coppia per sempre (valori)'.",
                    )
                    return
            cnt = self.result_ctrl.add_similarity_exceptions(mode, cols, rows, key_col, builder)
            return self._notify_exclusions(cnt)
        self._route_exclusion_to_builder({
            "kind": "similarity", "mode": mode, "cols": cols, "rows": rows, "key_col": "",
        })

    def _add_nonfuzzy(self, target_column=""):
        res = self.state.current_result
        if not res:
            return
        rows = self._selected_rows()
        if not rows:
            return messagebox.showwarning("Attenzione", "Seleziona almeno una riga.")
        cols = res.get("columns", [])
        if self._builder_live():
            cnt = self.result_ctrl.add_exceptions_from_rows(
                cols, rows, self.state.active_builder, target_column,
            )
            return self._notify_exclusions(cnt)
        self._route_exclusion_to_builder({
            "kind": "nonfuzzy", "cols": cols, "rows": rows, "target": target_column,
        })

    def _notify_exclusions(self, cnt):
        if cnt > 0:
            messagebox.showinfo("OK", f"Aggiunte {cnt} esclusioni al costruttore.\n"
                                     "Premi 'Aggiorna Salvata' per renderle permanenti.")
        else:
            messagebox.showinfo(
                "Nessuna esclusione aggiunta",
                "Tutti i valori selezionati erano gia' presenti tra le esclusioni, "
                "oppure nessun valore valido e' stato estratto dalla selezione.\n\n"
                "Suggerimenti:\n"
                "- per i record (sinistro/destro): imposta la 'Colonna chiave (ID)' nel builder;\n"
                "- per le coppie (valori/record): seleziona righe che mostrino entrambi i lati;\n"
                "- controlla il file app.log per il dettaglio tecnico della modalita' usata.",
            )

    def _add_to_exclusions(self):
        res = self.state.current_result
        if not res:
            return
        if self.result_ctrl._current_result_condition_type() == "similarity_check":
            return messagebox.showinfo(
                "Esclusioni",
                "Per i controlli di similarità usa il tasto destro sui risultati per scegliere la modalità di esclusione.",
            )
        self._add_nonfuzzy("")

    def _open_in_builder(self):
        if self.state.current_result:
            cond = self.state.current_result.get("_condition")
            if cond and self._on_open_in_builder:
                self._on_open_in_builder(cond)
            elif not cond:
                messagebox.showinfo("Info", "Risultato senza condizione collegata: impossibile aprirlo nel builder.")

    def _open_fullscreen(self):
        res = self.state.current_result
        if not res:
            return messagebox.showinfo("Info", "Nessun risultato da visualizzare.")
        top = tk.Toplevel(self.winfo_toplevel())
        top.title(res.get("title", "Report"))
        try:
            top.state("zoomed")
        except Exception:
            top.geometry("1280x800")
        fs = ResultsView(top, self.state, self.result_ctrl, enable_fullscreen=False)
        fs.pack(fill=tk.BOTH, expand=True)
        # Propaga il callback 'apri nel builder' anche alla finestra fullscreen.
        fs._on_open_in_builder = self._on_open_in_builder
        fs.show_results(res)
        top.bind("<Escape>", lambda _e: top.destroy())
