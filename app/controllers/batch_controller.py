import threading
import logging
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
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
        self._on_dash_update = None

    def set_log_callback(self, callback):
        self._on_log = callback

    def set_progress_callback(self, callback):
        self._on_progress = callback

    def set_dash_update_callback(self, callback):
        self._on_dash_update = callback

    def _safe(self, callback, *args):
        """Invoca un callback UI senza mai propagare eccezioni nel thread worker.

        Le callback aggiornano Tkinter da thread di lavoro: un loro errore
        (es. update cross-thread) NON deve interrompere l'esecuzione dei
        controlli rimanenti del batch."""
        if not callback:
            return
        try:
            callback(*args)
        except Exception as e:
            logger.warning("Callback UI batch ignorata per errore: %s", e)

    def _log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{ts}] {message}"
        logger.info(log_line)
        self._safe(self._on_log, log_line)

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

    def condition_cache_key(self, cond):
        payload = {}
        for key, value in dict(cond or {}).items():
            if key in ("saved_at", "updated_at", "_group_name"):
                continue
            payload[key] = value
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)

    def dashboard_state_for_condition(self, cond):
        return self.state.get_dash_state(self.condition_cache_key(cond), {})

    def set_dashboard_state(self, cond, count, status, tag, result=None):
        state = {
            "count": count,
            "status": status,
            "tag": tag,
            "result": result,
            "updated_at": datetime.now().isoformat(),
        }
        self.state.set_dash_state(self.condition_cache_key(cond), state)
        return state

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

        # Progresso contato per CONDIZIONE (non per gruppo-database): con un solo
        # database tutte le condizioni stanno in un gruppo, quindi contare i
        # future darebbe sempre 1/totale. Contatore condiviso protetto da lock.
        self._batch_total = len(batch_items)
        self._batch_done = 0
        self._batch_progress_lock = threading.Lock()
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
                    count = res.get("count", 0)
                    tag = "error" if count > 0 else "ok"
                    state = {"count": count, "status": "Completato", "tag": tag, "result": res}
                    self.state.set_dash_state(self.condition_cache_key(cond), state)
                    self._log(f"{name} -> {count} anomalie")
                except Exception as e:
                    logger.error(f"Errore batch su '{name}' [{database_label}]: {e}")
                    tag = "error"
                    state = {"count": "ERR", "status": "Errore", "tag": "error", "result": None}
                    self.state.set_dash_state(self.condition_cache_key(cond), state)
                    self._log(f"{name} -> ERRORE: {e}")
                with self._batch_progress_lock:
                    self._batch_done += 1
                    done = self._batch_done
                self._safe(self._on_progress, done, self._batch_total)
                self._safe(self._on_dash_update)
        finally:
            db.disconnect()

    def cancel_batch(self):
        self.state.batch_running = False
        self._log("Batch annullato dall'utente.")

    def run_selected_dashboard_check(self, cond):
        # Esecuzione singola: NON tocca batch_running, altrimenti il flag
        # resterebbe bloccato su True e "Esegui Tutti" (run_all_batch) 
        # diventerebbe un no-op silenzioso finché l'utente non cancella
        # manualmente il batch. Il flag serve solo al batch multi-DB.
        threading.Thread(target=self._execute_dashboard_task, args=(dict(cond),), daemon=True).start()

    def _execute_dashboard_task(self, cond):
        name = cond.get("name", "")
        self._log(f"Esecuzione: {name}")
        try:
            db_label = str(cond.get("database_label", "") or "").strip()
            if db_label:
                self.db_ctrl.ensure_active_database_for_label(db_label, interactive=True)
            res = self.state.executor.run(cond)
            if isinstance(res, dict):
                res["_condition"] = cond
                res["_condition_type"] = cond.get("type")
            count = res.get("count", 0)
            tag = "error" if count > 0 else "ok"
            self.set_dashboard_state(cond, count, "Completato", tag, result=res)
            self._log(f"{name} -> {count} anomalie")
            self._safe(self._on_results_callback, res)
        except Exception as e:
            logger.error(f"Errore esecuzione '{name}': {e}")
            self.set_dashboard_state(cond, "ERR", "Errore", "error")
            self._log(f"{name} -> ERRORE: {e}")
        finally:
            self._safe(self._on_dash_update)

    @property
    def _on_results_callback(self):
        return self.result_ctrl._on_results_callback
