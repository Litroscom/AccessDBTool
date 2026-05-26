import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import messagebox

from db_manager import DatabaseManager
from engines import ConditionExecutor

logger = logging.getLogger("AccessDBTool.BatchController")


class BatchController:
    def __init__(self, state, db_controller, result_controller):
        self.state = state
        self.db_ctrl = db_controller
        self.result_ctrl = result_controller
        self._on_log = None
        self._on_progress = None

    def set_log_callback(self, callback):
        self._on_log = callback

    def set_progress_callback(self, callback):
        self._on_progress = callback

    def _log(self, message):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{ts}] {message}"
        logger.info(log_line)
        if self._on_log:
            self._on_log(log_line)

    def _stored_database_label_for_condition(self, cond):
        return str(cond.get("database_label", "") or "").strip()

    def prepare_batch_database_paths(self, batch_items):
        db_paths = {}
        for cond in batch_items:
            label = self._stored_database_label_for_condition(cond)
            if not label:
                resolved_label, path = self.db_ctrl.resolve_database_path("", interactive=True)
                if not path:
                    return None
                cond["database_label"] = resolved_label
                label = resolved_label
            if label in db_paths:
                continue
            resolved_label, path = self.db_ctrl.resolve_database_path(label, interactive=True)
            if not path:
                return None
            if resolved_label and resolved_label != label:
                cond["database_label"] = resolved_label
                label = resolved_label
            db_paths[label] = path
        return db_paths

    def run_all_batch(self):
        if self.state.batch_running:
            return
        if not self.state.dash_items:
            return messagebox.showinfo("Info", "Nessuna condizione disponibile nel batch corrente.")
        db_paths = self.prepare_batch_database_paths(self.state.dash_items)
        if not db_paths:
            self.state.status.set("Batch annullato: risoluzione database interrotta.")
            return
        self.state.batch_running = True
        threading.Thread(target=self._batch_worker, args=(db_paths,), daemon=True).start()

    def _batch_worker(self, db_paths):
        batch_items = list(self.state.dash_items)
        grouped = {}
        for idx, cond in enumerate(batch_items):
            label = self._stored_database_label_for_condition(cond)
            grouped.setdefault(label, []).append((idx, dict(cond)))

        total = len(batch_items)
        completed = 0
        max_workers = max(1, min(4, len(grouped)))
        errors = []

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self._run_batch_for_database, label, db_paths.get(label, ""), items): label
                for label, items in grouped.items()
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    errors.append(str(e))
                completed += 1
                if self._on_progress:
                    self._on_progress(completed, total)

        self.state.batch_running = False
        if errors:
            self.state.status.set("Batch completato con errori.")
            logger.error("Batch multi-db completato con errori: %s", " | ".join(errors))
        else:
            self.state.status.set("Analisi batch multi-database finita.")

    def _run_batch_for_database(self, database_label, db_path, items):
        if not db_path:
            raise RuntimeError(f"Nessun percorso risolto per il database '{database_label}'.")
        db = DatabaseManager()
        db.connect(db_path)
        executor = ConditionExecutor(db)
        try:
            for idx, cond in items:
                if not self.state.batch_running:
                    break
                name = cond.get("name", "?")
                self._log(f"{name} su {database_label}...")
                try:
                    res = executor.run(cond)
                    if isinstance(res, dict):
                        res["_condition"] = dict(cond)
                        res["_condition_type"] = cond.get("type")
                    count = res["count"]
                    tag = "error" if count > 0 else "ok"
                    self._log(f"{name} -> {count} anomalie")
                except Exception as e:
                    logger.error(f"Errore batch su '{name}' [{database_label}]: {e}")
                    count = "ERR"
                    tag = "error"
                    res = None
                    self._log(f"{name} -> ERRORE: {e}")
        finally:
            db.disconnect()

    def cancel_batch(self):
        self.state.batch_running = False
        self._log("Batch annullato dall'utente.")
