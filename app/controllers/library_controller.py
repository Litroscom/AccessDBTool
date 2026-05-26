import logging
from datetime import datetime
from tkinter import messagebox

logger = logging.getLogger("AccessDBTool.LibraryController")


class LibraryController:
    def __init__(self, state, db_controller):
        self.state = state
        self.db_ctrl = db_controller

    def prepare_condition_for_storage(self, cond):
        prepared = dict(cond)
        prepared["database_label"] = self.db_ctrl.database_label_for_condition(prepared)
        prepared["periodic_review_enabled"] = bool(prepared.get("periodic_review_enabled"))
        cycle = str(prepared.get("periodic_review_cycle", "") or "").strip().lower()
        if prepared["periodic_review_enabled"]:
            prepared["periodic_review_cycle"] = cycle if cycle in ("daily", "weekly", "monthly") else "monthly"
            prepared["periodic_review_note"] = str(prepared.get("periodic_review_note", "") or "").strip()
            prepared["periodic_review_last_ack"] = str(prepared.get("periodic_review_last_ack", "") or "").strip()
        else:
            prepared["periodic_review_cycle"] = ""
            prepared["periodic_review_note"] = ""
            prepared["periodic_review_last_ack"] = ""
        return prepared

    def filter_conditions_by_tag(self, tag):
        normalized = (tag or "").strip()
        if not normalized or normalized == "Tutti":
            return list(self.state.store.items)
        return [c for c in self.state.store.items if c.get("tag", "").strip() == normalized]

    def refresh_lib(self):
        names = [c.get("name", "") for c in self.state.store.items]
        return names

    def save_to_lib(self, name, desc, tag, ctype, config, display_cols, periodic_data):
        if not ctype:
            return
        cond_data = {
            "name": name,
            "description": desc,
            "tag": tag,
            "type": ctype,
            "display_columns": display_cols,
            "saved_at": datetime.now().isoformat(),
            "database_label": self.state.current_db_label,
            "periodic_review_enabled": periodic_data.get("periodic_review_enabled", False),
            "periodic_review_cycle": periodic_data.get("periodic_review_cycle", ""),
            "periodic_review_note": periodic_data.get("periodic_review_note", ""),
            "periodic_review_last_ack": datetime.now().isoformat() if periodic_data.get("periodic_review_enabled") else "",
        }
        if self.state.sel_tables:
            cond_data["table"] = self.state.sel_tables[0]
        if config:
            cond_data.update(config)
        cond_data = self.prepare_condition_for_storage(cond_data)
        self.state.store.add(cond_data)
        self.state.var_saved.set(name)
        self.state.loaded_condition_idx = len(self.state.store.items) - 1
        self.state.status.set(f"Salvata condizione: {name}")
        return cond_data

    def update_to_lib(self, ctype, config, display_cols):
        name = self.state.var_saved.get()
        idx = self.state.loaded_condition_idx
        if idx is None or idx < 0:
            return
        desc = self.state.store.items[idx].get("description", "")
        tag = self.state.store.items[idx].get("tag", "")
        cond_data = {
            "name": name, "description": desc, "tag": tag,
            "type": ctype, "display_columns": display_cols,
            "updated_at": datetime.now().isoformat(),
            "database_label": self.state.current_db_label,
            "periodic_review_enabled": self.state.store.items[idx].get("periodic_review_enabled", False),
            "periodic_review_cycle": self.state.store.items[idx].get("periodic_review_cycle", ""),
            "periodic_review_note": self.state.store.items[idx].get("periodic_review_note", ""),
            "periodic_review_last_ack": datetime.now().isoformat() if self.state.store.items[idx].get("periodic_review_enabled") else "",
        }
        if self.state.sel_tables:
            cond_data["table"] = self.state.sel_tables[0]
        if config:
            cond_data.update(config)
        cond_data = self.prepare_condition_for_storage(cond_data)
        self.state.store.update(idx, cond_data)
        self.state.var_saved.set(name)
        self.state.status.set("Condizione aggiornata!")
        messagebox.showinfo("OK", "Condizione aggiornata con successo!")
        return cond_data

    def load_cond_into_builder(self, cond):
        if not cond:
            return
        import constants
        cond_db_label = str(cond.get("database_label", "") or "").strip()
        if cond_db_label and cond_db_label != self.state.current_db_label:
            self.db_ctrl.ensure_active_database_for_label(cond_db_label, interactive=False)
        ctype_key = cond.get("type", "")
        ctype_label = constants.CONDITION_TYPES.get(ctype_key, "")
        if ctype_label:
            self.state.var_ctype.set(ctype_label)
        self.state.var_saved.set(cond.get("name", ""))
        self.state.loaded_condition_idx = None
        for i, c in enumerate(self.state.store.items):
            if c is cond or c == cond:
                self.state.loaded_condition_idx = i
                break
        tag = cond.get("tag", "").strip()
        if tag and hasattr(self.state, "var_lib_tag"):
            self.state.var_lib_tag.set(tag)
            self.state.var_saved.set(cond.get("name", ""))
        self.state.active_ctype = ctype_key
        self.state.status.set(f"Caricata: {cond.get('name', '?')}")
        return cond

    def open_manager(self):
        from views.condition_manager_view import ConditionManagerDialog
        ConditionManagerDialog(None, self.state.store, lambda: None, self.load_cond_into_builder)
