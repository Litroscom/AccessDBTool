import tkinter as tk
from tkinter import ttk
import json
import logging

logger = logging.getLogger("AccessDBTool.DashboardView")


class DashboardView(ttk.Frame):
    def __init__(self, parent, state, db_controller, library_controller=None, batch_controller=None, result_controller=None):
        super().__init__(parent)
        self.state = state
        self.db_ctrl = db_controller
        self.library_ctrl = library_controller
        self.batch_ctrl = batch_controller
        self.result_ctrl = result_controller
        self._on_open_in_builder = None
        self._build_ui()

    def set_open_in_builder_callback(self, callback):
        """Registra la callback per aprire una condizione nel tab Controlli.

        Usata dal doppio click sulla riga della dashboard. Se non cablata,
        il doppio click ricade sul comportamento legacy (riesecuzione)."""
        self._on_open_in_builder = callback

    def _build_ui(self):
        filter_bar = ttk.Frame(self, padding=6)
        filter_bar.pack(fill=tk.X)

        ttk.Label(filter_bar, text="Tag:").pack(side=tk.LEFT)
        self.var_tag_filter = tk.StringVar(value="Tutti")
        self.cmb_tag = ttk.Combobox(
            filter_bar, textvariable=self.var_tag_filter,
            values=["Tutti"], state="readonly", width=14
        )
        self.cmb_tag.pack(side=tk.LEFT, padx=4)
        self.cmb_tag.bind("<<ComboboxSelected>>", lambda _: self._refresh())

        ttk.Label(filter_bar, text="DB:").pack(side=tk.LEFT, padx=(12, 4))
        self.var_db_filter = tk.StringVar(value="Tutti")
        self.cmb_db = ttk.Combobox(
            filter_bar, textvariable=self.var_db_filter,
            values=["Tutti"], state="readonly", width=14
        )
        self.cmb_db.pack(side=tk.LEFT, padx=4)
        self.cmb_db.bind("<<ComboboxSelected>>", lambda _: self._refresh())

        self.var_anomalies_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_bar, text="Solo anomalie",
                        variable=self.var_anomalies_only,
                        command=self._refresh).pack(side=tk.LEFT, padx=(12, 4))

        self.var_search = tk.StringVar()
        self.entry_search = ttk.Entry(filter_bar, textvariable=self.var_search, width=18)
        self.entry_search.pack(side=tk.LEFT, padx=4)
        self.entry_search.bind("<KeyRelease>", lambda _: self._refresh())

        ttk.Button(filter_bar, text="Esegui Selezionato",
                   command=self._run_selected,
                   bootstyle="warning-outline").pack(side=tk.RIGHT, padx=2)
        ttk.Button(filter_bar, text="Esegui Tutti",
                   command=self._run_all,
                   bootstyle="danger").pack(side=tk.RIGHT, padx=2)

        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        left_frame = ttk.Frame(paned, padding=4)
        paned.add(left_frame, weight=1)

        self.dash_tree = ttk.Treeview(
            left_frame,
            columns=["id", "name", "db", "count", "status"],
            show="headings",
        )
        self.dash_tree.heading("id", text="#")
        self.dash_tree.column("id", width=30, anchor=tk.CENTER)
        self.dash_tree.heading("name", text="Controllo")
        self.dash_tree.column("name", width=200)
        self.dash_tree.heading("db", text="DB")
        self.dash_tree.column("db", width=100)
        self.dash_tree.heading("count", text="Ris.")
        self.dash_tree.column("count", width=50, anchor=tk.CENTER)
        self.dash_tree.heading("status", text="Stato")
        self.dash_tree.column("status", width=100)

        vsb = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.dash_tree.yview)
        self.dash_tree.configure(yscrollcommand=vsb.set)
        self.dash_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.dash_tree.tag_configure("error", background="#5c1a1a", foreground="#ffb3b3")
        self.dash_tree.tag_configure("ok", background="#1a4c2a", foreground="#b3ffcc")
        self.dash_tree.tag_configure("running", background="#4a3d0a", foreground="#ffe68a")
        self.dash_tree.tag_configure("idle", foreground="gray")

        self.dash_tree.bind("<<TreeviewSelect>>", self._on_select)
        self.dash_tree.bind("<Double-1>", self._on_double_click)

        from views.results_view import ResultsView
        self.results_view = ResultsView(paned, self.state, self.result_ctrl)
        paned.add(self.results_view, weight=2)

        bottom_frame = ttk.Frame(self, padding=4)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.progress = ttk.Progressbar(
            bottom_frame, mode="determinate", bootstyle="success-striped"
        )
        self.progress.pack(fill=tk.X)
        self.lbl_progress = ttk.Label(bottom_frame, text="", font=("", 8))
        self.lbl_progress.pack(anchor=tk.W)

        self.log_text = tk.Text(
            bottom_frame, height=4, font=("Consolas", 8),
            bg="#1a1a2e", fg="#a0a0b0", state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.X, pady=(4, 0))

        if self.batch_ctrl:
            # Marshalling sul main thread: le callback partono da thread worker.
            self.batch_ctrl.set_log_callback(
                lambda line: self.after(0, self._append_log, line))
            self.batch_ctrl.set_progress_callback(
                lambda cur, tot: self.after(0, self._update_progress, cur, tot))
            self.batch_ctrl.set_dash_update_callback(
                lambda: self.after(0, self._refresh))

        if self.result_ctrl:
            self.result_ctrl.set_results_callback(
                lambda res: self.after(0, self.show_results, res))

    def _refresh(self):
        self.dash_tree.delete(*self.dash_tree.get_children())
        tag_filter = self.var_tag_filter.get().strip()
        items = self.library_ctrl.get_dashboard_items(tag_filter) if self.library_ctrl else []
        search = self.var_search.get().strip().lower()
        if search:
            items = [c for c in items if search in c.get("name", "").lower()]
        anomalies_only = self.var_anomalies_only.get()
        self.state.dash_items = items
        for i, c in enumerate(items):
            state_data = self.batch_ctrl.dashboard_state_for_condition(c) if self.batch_ctrl else {}
            tag = state_data.get("tag", "idle")
            count_val = state_data.get("count", "-")
            status_val = state_data.get("status", "Mai eseguito")
            # "Solo anomalie": mostra solo i controlli con tag "error"
            # (precedente: teneva anche i controlli OK già eseguiti perché
            # il filtro scattava solo su count_val == "-").
            if anomalies_only and tag != "error":
                continue
            self.dash_tree.insert("", tk.END, iid=str(i),
                                   values=(i + 1, c.get("name", ""),
                                           c.get("database_label", ""),
                                           count_val, status_val),
                                   tags=(tag,))

        all_tags = self.library_ctrl.all_condition_tags() if self.library_ctrl else []
        self.cmb_tag["values"] = ["Tutti"] + all_tags
        db_labels = sorted(set(
            c.get("database_label", "") for c in items if c.get("database_label")
        ))
        self.cmb_db["values"] = ["Tutti"] + db_labels

    def _on_select(self, evt):
        sel = self.dash_tree.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
            if 0 <= idx < len(self.state.dash_items):
                cond = self.state.dash_items[idx]
                state_data = self.batch_ctrl.dashboard_state_for_condition(cond) if self.batch_ctrl else {}
                result = state_data.get("result")
                if result:
                    # Collega la condizione al risultato: porta con sé il
                    # database_label, così la modifica diretta di un record
                    # scrive sul DB giusto (la dashboard è multi-DB).
                    if isinstance(result, dict) and "_condition" not in result:
                        result["_condition"] = cond
                    self.state.current_result = result
                    self.results_view.show_results(result)
        except Exception:
            pass

    def _on_double_click(self, evt):
        sel = self.dash_tree.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
            if 0 <= idx < len(self.state.dash_items):
                cond = self.state.dash_items[idx]
                # Apri la condizione nel tab Controlli (builder) se la callback
                # e' stata cablata dall'App; altrimenti fallback: riesegue il
                # controllo, per mantenere un comportamento utile in isolamento.
                if self._on_open_in_builder:
                    self._on_open_in_builder(cond)
                elif self.batch_ctrl:
                    self.batch_ctrl.run_selected_dashboard_check(cond)
        except Exception:
            logger.exception("double click dashboard fallito")

    def _run_selected(self):
        sel = self.dash_tree.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
            if 0 <= idx < len(self.state.dash_items):
                cond = self.state.dash_items[idx]
                if self.batch_ctrl:
                    self.batch_ctrl.run_selected_dashboard_check(cond)
        except Exception:
            pass

    def _run_all(self):
        if self.batch_ctrl:
            self.batch_ctrl.run_all_batch()

    def _append_log(self, line):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _update_progress(self, current, total):
        if total > 0:
            self.progress["maximum"] = total
            self.progress["value"] = current
        self.lbl_progress.config(text=f"{current}/{total} controlli")

    def show_results(self, res):
        self.results_view.show_results(res)

    def show_progress(self, current, total, text=""):
        if total > 0:
            self.progress["maximum"] = total
            self.progress["value"] = current
        self.lbl_progress.config(text=text)
