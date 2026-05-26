import threading
import logging
from tkinter import messagebox

logger = logging.getLogger("AccessDBTool.ResultController")


class ResultController:
    def __init__(self, state):
        self.state = state
        self._on_results_callback = None

    def set_results_callback(self, callback):
        self._on_results_callback = callback

    def validate_active_builder(self):
        if self.state.active_builder and hasattr(self.state.active_builder, "validate"):
            ok, msg = self.state.active_builder.validate()
            if not ok:
                self.state.status.set(msg)
                messagebox.showwarning("Configurazione incompleta", msg)
                return False
        return True

    def run_current(self, display_cols=None):
        if not self.state.db.connected:
            return messagebox.showwarning("!", "Apri DB")
        ctype = self.state.active_ctype
        if not ctype:
            return messagebox.showwarning("!", "Seleziona tipo analisi")
        if not self.validate_active_builder():
            return
        cond = {
            "type": ctype,
            "name": "Analisi Manuale",
            "tables": self.state.sel_tables,
            "columns": display_cols or [],
            "display_columns": display_cols or [],
        }
        if self.state.active_builder:
            cond.update(self.state.active_builder.get_config())
        threading.Thread(target=self._execute_task, args=(cond,), daemon=True).start()

    def _execute_task(self, cond):
        self.state.status.set("Esecuzione in corso...")
        try:
            res = self.state.executor.run(cond)
            if isinstance(res, dict):
                res["_condition"] = cond
                res["_condition_type"] = cond.get("type")
            self._show_results(res)
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    def _show_results(self, res):
        self.state.current_result = res
        if self._on_results_callback:
            self._on_results_callback(res)
        self.state.status.set("Risultati caricati.")
