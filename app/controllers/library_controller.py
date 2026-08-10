import logging
from datetime import datetime
from tkinter import messagebox, simpledialog, filedialog

import constants

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
        from tkinter import StringVar
        self.state.var_lib_tag = getattr(self.state, "var_lib_tag", StringVar(value="Tutti"))
        selected_tag = self.state.var_lib_tag.get().strip()
        names = [c.get("name", "") for c in self.filter_conditions_by_tag(selected_tag)]
        return names

    def all_condition_tags(self):
        tags = set(self.state.store.tags())
        for group in self._get_effective_groups():
            for cond in group.get("conditions", []):
                tag = str(cond.get("tag", "") or "").strip()
                if tag:
                    tags.add(tag)
        return sorted(tags)

    def save_to_lib(self, name, desc, tag, ctype, config, display_cols, periodic_data):
        if not ctype:
            return
        cond_data = {
            "name": name,
            "description": desc,
            "tag": tag,
            "type": ctype,
            "saved_at": datetime.now().isoformat(),
            "database_label": self.state.current_db_label,
            "periodic_review_enabled": periodic_data.get("periodic_review_enabled", False),
            "periodic_review_cycle": periodic_data.get("periodic_review_cycle", ""),
            "periodic_review_note": periodic_data.get("periodic_review_note", ""),
            "periodic_review_last_ack": datetime.now().isoformat() if periodic_data.get("periodic_review_enabled") else "",
        }
        # display_cols None = selettore non inizializzato: non scrivere la
        # chiave (così l'engine usa il default "tutte le colonne" e un
        # eventuale valore precedente non viene azzerato per errore).
        if display_cols is not None:
            cond_data["display_columns"] = display_cols
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
            # Non silenziare mai: l'utente deve sapere che l'aggiornamento
            # non e' avvenuto (es. condizione aperta da dashboard senza match).
            messagebox.showwarning(
                "Aggiorna salvata",
                "Nessuna condizione di libreria caricata da aggiornare.\n"
                "Apri la condizione dalla libreria (menu a tendina) o usa \n"
                "\"Salva\" per crearne una nuova.",
            )
            return
        desc = self.state.store.items[idx].get("description", "")
        tag = self.state.store.items[idx].get("tag", "")
        cond_data = {
            "name": name, "description": desc, "tag": tag,
            "type": ctype,
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
        # display_cols viene applicato DOPO config perché alcuni builder includono
        # display_columns nel proprio get_config() e sovrascriverebbero la
        # selezione dell'utente. None = selettore non inizializzato: mantieni
        # le display_columns eventualmente presenti in config/store.
        if display_cols is not None:
            cond_data["display_columns"] = display_cols
        cond_data = self.prepare_condition_for_storage(cond_data)
        self.state.store.update(idx, cond_data)
        self.state.var_saved.set(name)
        self.state.status.set("Condizione aggiornata!")
        messagebox.showinfo("OK", "Condizione aggiornata con successo!")
        return cond_data

    def save_cond(self, force_new=False, display_cols=None):
        """Salva/aggiorna la condizione corrente.

        display_cols=None = selettore colonne non inizializzato: non toccare
        le display_columns eventualmente già salvate (fix: il salvataggio dal
        menu Alt+S azzerava la selezione report perché passava []).
        """
        import json
        ctype = self.state.active_ctype
        if not ctype:
            return messagebox.showwarning("!", "Seleziona tipo analisi")
        if not self.state.active_builder:
            return messagebox.showwarning("!", "Configura una condizione prima di salvare.")
        config = self.state.active_builder.get_config()
        from ui_components import ConditionSaveDialog
        dialog = ConditionSaveDialog(
            None, self.state.store,
            default_name=self.state.var_saved.get(),
            default_tag=self.state.var_saved.get() if not force_new else "",
            force_new=force_new,
        )
        if not dialog.result:
            return
        desc = dialog.result.get("description", "")
        tag = dialog.result.get("tag", "").strip()
        if force_new:
            return self.save_to_lib(dialog.result["name"], desc, tag, ctype, config, display_cols, {})
        existing_idx = None
        loaded_name = self.state.var_saved.get()
        if loaded_name:
            for i, c in enumerate(self.state.store.items):
                if c.get("name") == loaded_name:
                    existing_idx = i
                    break
        if existing_idx is not None:
            desc = self.state.store.items[existing_idx].get("description", "")
            tag = self.state.store.items[existing_idx].get("tag", "")
            cond_data = {
                "name": dialog.result["name"], "description": desc, "tag": tag,
                "type": ctype,
                "updated_at": datetime.now().isoformat(),
                "database_label": self.state.current_db_label,
            }
            # display_columns applicate solo se il selettore è stato inizializzato
            # (None = mantieni quelle già salvate)
            if display_cols is not None:
                cond_data["display_columns"] = display_cols
            if self.state.sel_tables:
                cond_data["table"] = self.state.sel_tables[0]
            if config:
                cond_data.update(config)
            cond_data = self.prepare_condition_for_storage(cond_data)
            self.state.store.update(existing_idx, cond_data)
            self.state.var_saved.set(dialog.result["name"])
            self.state.status.set("Condizione aggiornata!")
        else:
            self.save_to_lib(dialog.result["name"], desc, tag, ctype, config, display_cols, {})

    def load_cond_into_builder(self, cond):
        if not cond:
            return
        cond_db_label = str(cond.get("database_label", "") or "").strip()
        if cond_db_label and cond_db_label != self.state.current_db_label:
            self.db_ctrl.ensure_active_database_for_label(cond_db_label, interactive=False)
        ctype_key = cond.get("type", "")
        ctype_label = constants.CONDITION_TYPES.get(ctype_key, "")
        if ctype_label:
            self.state.var_ctype.set(ctype_label)
        self.state.var_saved.set(cond.get("name", ""))
        self.state.loaded_condition_idx = None
        # 'cond' può essere una copia proveniente dalla dashboard
        # (get_dashboard_items aggiunge la chiave '_group_name'), quindi il
        # match per identità/uguaglianza fallirebbe. Usiamo il nome come
        # chiave stabile (univoca in libreria, vedi bug #18).
        cond_name = str(cond.get("name", "") or "").strip()
        for i, c in enumerate(self.state.store.items):
            if c is cond or (cond_name and str(c.get("name", "") or "").strip() == cond_name):
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

    def open_groups(self):
        """Apre il gestore gruppi in una finestra dedicata.

        Il GroupSelector è un Frame: va impacchettato in un Toplevel per essere
        visibile. "Salva Set Corrente" salva la libreria corrente come gruppo
        (l'evento <<SaveGroup>> viene gestito qui, dove abbiamo accesso alla
        libreria e al database attivo).
        """
        import tkinter as tk
        from ui_components import GroupSelector

        def _on_load(group):
            if group and group.get("conditions"):
                self._load_group_conditions(group)

        top = tk.Toplevel()
        top.title("Gruppi di condizioni")
        top.geometry("640x120")
        top.resizable(False, False)

        selector = GroupSelector(top, self.state.group_store, _on_load)
        selector.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._wire_group_selector(selector)

    def _wire_group_selector(self, selector):
        """Collega l'evento <<SaveGroup>> del GroupSelector al salvataggio
        della libreria corrente come gruppo (separato per testabilità)."""
        def _on_save_group(_evt=None):
            selector.finalize_save(
                [dict(c) for c in self.state.store.items],
                database_label=self.state.current_db_label or "",
            )

        selector.bind("<<SaveGroup>>", _on_save_group)

    def _load_group_conditions(self, group):
        for cond in group.get("conditions", []):
            item = dict(cond)
            item["_group_name"] = group.get("name", "")
            self.state.store.add(item)
        self.state.status.set(f"Gruppo '{group.get('name', '')}' caricato nella libreria.")
        messagebox.showinfo("OK", f"Gruppo '{group.get('name', '')}' caricato nella libreria.")

    def export_conditions(self, items=None):
        import json
        data = items if items else self.state.store.items
        if not data:
            return messagebox.showinfo("Info", "Nessuna condizione da esportare.")
        path = filedialog.asksaveasfilename(
            title="Esporta condizioni",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        self.state.status.set(f"Esportate {len(data)} condizioni.")
        messagebox.showinfo("OK", f"Esportate {len(data)} condizioni.")

    def import_conditions(self):
        import json
        path = filedialog.askopenfilename(
            title="Importa condizioni",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            return messagebox.showerror("Errore", f"File non valido: {e}")
        if not isinstance(data, list):
            return messagebox.showerror("Errore", "Formato non valido: atteso array JSON.")
        added = 0
        updated = 0
        for cond in data:
            if not isinstance(cond, dict):
                continue
            name = str(cond.get("name", "") or "").strip()
            existing_idx = None
            if name:
                for i, c in enumerate(self.state.store.items):
                    if str(c.get("name", "") or "").strip() == name:
                        existing_idx = i
                        break
            if existing_idx is not None:
                # Sovrascrive la condizione esistente con lo stesso nome
                # (preserva eccezioni/esclusioni del file importato)
                self.state.store.update(existing_idx, dict(cond))
                updated += 1
            else:
                self.state.store.add(dict(cond))
                added += 1
        self.state.status.set(f"Importate {added} nuove, {updated} aggiornate.")
        messagebox.showinfo(
            "OK",
            f"Importate {added} nuove condizioni, {updated} aggiornate (sovrascritte).",
        )

    def ensure_active_builder_from_result(self):
        if not self.state.current_result:
            return
        cond = self.state.current_result.get("_condition")
        if not cond:
            return
        self.load_cond_into_builder(cond)

    def _iter_group_conditions(self):
        for group in self._get_effective_groups():
            group_name = group.get("name", "")
            group_db_label = str(group.get("database_label", "") or "").strip()
            for cond in group.get("conditions", []):
                item = dict(cond)
                item["_group_name"] = group_name
                item["database_label"] = str(item.get("database_label", "") or "").strip() or group_db_label
                yield item

    def _build_tag_groups(self):
        groups_by_tag = {}
        for cond in self.state.store.items:
            if not isinstance(cond, dict):
                continue
            tag = str(cond.get("tag", "") or "").strip()
            if not tag:
                continue
            groups_by_tag.setdefault(tag, []).append(dict(cond))
        groups = []
        for tag in sorted(groups_by_tag.keys()):
            items = groups_by_tag[tag]
            db_label = ""
            seen_labels = {
                str(item.get("database_label", "") or "").strip()
                for item in items
                if str(item.get("database_label", "") or "").strip()
            }
            if len(seen_labels) == 1:
                db_label = next(iter(seen_labels))
            elif len(seen_labels) == 0:
                db_label = self.db_ctrl.guess_database_label_for_tag(tag)
            prepared = []
            for item in items:
                if db_label and not str(item.get("database_label", "") or "").strip():
                    item["database_label"] = db_label
                prepared.append(item)
            groups.append({
                "name": tag,
                "database_label": db_label,
                "conditions": prepared,
                "_derived_from_tag": True,
            })
        return groups

    def _get_effective_groups(self):
        explicit_groups = self.state.group_store.all_groups()
        has_bound_groups = any(
            str(group.get("database_label", "") or "").strip()
            or any(str(cond.get("database_label", "") or "").strip() for cond in group.get("conditions", []))
            for group in explicit_groups
        )
        if has_bound_groups:
            return explicit_groups
        tag_groups = self._build_tag_groups()
        if tag_groups:
            return tag_groups
        return explicit_groups

    def get_dashboard_items(self, tag):
        selected = str(tag or "").strip()
        items = list(self._iter_group_conditions())
        if not items:
            items = [dict(cond, _group_name="Libreria corrente") for cond in self.state.store.items]
        if selected and selected != "Tutti":
            items = [item for item in items if str(item.get("tag", "") or "").strip() == selected]
        return items
