import os
import logging
from tkinter import filedialog, messagebox

logger = logging.getLogger("AccessDBTool.DBController")


class DBController:
    def __init__(self, state):
        self.state = state
        self._on_active_db_switched = None

    def set_active_db_switched_callback(self, callback):
        """Chiamato quando il database attivo CAMBIA (es. aperto un altro file)."""
        self._on_active_db_switched = callback

    def suggest_database_label(self, path):
        return os.path.basename(str(path or "").strip())

    def register_database_reference(self, label, path=""):
        normalized_label = str(label or "").strip()
        if not normalized_label and path:
            normalized_label = self.suggest_database_label(path)
        if normalized_label:
            if path:
                self.state.db_registry.set_path(normalized_label, path)
            else:
                self.state.db_registry.remember(normalized_label)
        return normalized_label

    def sync_open_database_ui(self, view_refresh=None):
        if view_refresh:
            view_refresh()

    def connect_active_database(self, path, database_label=""):
        switched = self.state.db.connected and self.state.db.db_path != path
        if switched:
            # Cambio database a monitor attivo: le condizioni salvate girerebbero
            # sul file sbagliato -> ferma il monitor (il chiamante lo notifica).
            self.state.db.disconnect()
            if self._on_active_db_switched:
                try:
                    self._on_active_db_switched()
                except Exception:
                    pass
        self.state.db.connect(path)
        label = self.register_database_reference(database_label, path)
        self.state.current_db_label = label
        self.state.status.set(f"DB aperto: {label or os.path.basename(path)}")
        logger.info(f"Database aperto: {path} [{label}]")
        return label

    def resolve_database_path(self, database_label="", interactive=False):
        label = str(database_label or "").strip()
        if not label and self.state.current_db_label:
            label = self.state.current_db_label
        if label and self.state.db.connected and self.state.current_db_label == label and os.path.exists(self.state.db.db_path):
            return label, self.state.db.db_path
        stored_path = self.state.db_registry.get_path(label) if label else ""
        if stored_path and os.path.exists(stored_path):
            return label, stored_path
        if not interactive:
            return label, ""
        title = "Seleziona database Access"
        if label:
            title = f"Seleziona il file per il database '{label}'"
        path = filedialog.askopenfilename(
            title=title,
            filetypes=[("Access DB", "*.mdb *.accdb")],
        )
        if not path:
            return label, ""
        resolved_label = label or self.suggest_database_label(path)
        self.register_database_reference(resolved_label, path)
        return resolved_label, path

    def ensure_active_database_for_label(self, database_label="", interactive=False):
        label, path = self.resolve_database_path(database_label, interactive=interactive)
        if not path:
            return False
        if self.state.db.connected and self.state.db.db_path == path:
            if label:
                self.state.current_db_label = self.register_database_reference(label, path)
            return True
        try:
            self.connect_active_database(path, label)
            return True
        except Exception as e:
            messagebox.showerror("Errore", str(e))
            logger.error(f"Errore apertura DB '{label}': {e}")
            return False

    def open_db(self):
        p = filedialog.askopenfilename(filetypes=[("Access DB", "*.mdb *.accdb")])
        if not p:
            return
        try:
            self.connect_active_database(p, self.suggest_database_label(p))
        except Exception as e:
            messagebox.showerror("Errore", str(e))
            logger.error(f"Errore apertura DB: {e}")

    def close_db(self, stop_monitor_fn=None):
        if stop_monitor_fn:
            stop_monitor_fn()
        self.state.db.disconnect()
        self.state.current_db_label = ""
        self.state.status.set("DB chiuso")

    def database_label_for_condition(self, cond):
        label = str(cond.get("database_label", "") or "").strip()
        if label:
            return label
        if self.state.current_db_label:
            return self.state.current_db_label
        if self.state.db.connected and self.state.db.db_path:
            return self.register_database_reference("", self.state.db.db_path)
        return ""

    def guess_database_label_for_tag(self, tag):
        normalized_tag = str(tag or "").strip().lower()
        if not normalized_tag:
            return ""
        matches = []
        for label in self.state.db_registry.names():
            label_norm = label.lower()
            stem_norm = os.path.splitext(label_norm)[0]
            if normalized_tag == label_norm or normalized_tag == stem_norm:
                return label
            if normalized_tag in label_norm or normalized_tag in stem_norm:
                matches.append(label)
        return matches[0] if len(matches) == 1 else ""

    def group_database_label(self, conditions):
        for cond in conditions or []:
            label = str(cond.get("database_label", "") or "").strip()
            if label:
                return label
        return self.state.current_db_label

    def database_registry_rows(self):
        rows = []
        current_path = str(getattr(self.state.db, "db_path", "") or "").strip()
        current_path_norm = os.path.normcase(current_path) if current_path else ""
        for entry in self.state.db_registry.entries():
            label = entry.get("label", "")
            path = entry.get("path", "")
            path_exists = bool(path and os.path.exists(path))
            path_norm = os.path.normcase(path) if path else ""
            if self.state.db.connected and current_path_norm and path_norm == current_path_norm:
                state = "APERTO"
            elif path_exists:
                state = "PRONTO"
            else:
                state = "DA RICOLLEGARE"
            rows.append({"label": label, "path": path, "state": state})
        return rows

    def run_profiler(self):
        if not self.state.db.connected:
            return messagebox.showwarning("!", "Apri un Database prima di eseguire il profiler.")
        try:
            from data_profiler import DataProfiler
            profiler = DataProfiler(self.state.db)
            self.state.current_insights = profiler.analyze()
            self.state.status.set(f"Profiler completato: {len(self.state.current_insights)} insight generati.")
        except Exception as e:
            logger.error(f"Errore profiler: {e}")
            messagebox.showerror("Errore profiler", str(e))
