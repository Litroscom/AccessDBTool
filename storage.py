import json
import os
import re
import copy
import logging
from tkinter import messagebox
import constants

logger = logging.getLogger("AccessDBTool.Storage")


def _eq(a, b):
    """Confronto valore tollerante: trimmed e case-insensitive."""
    return str(a).strip().lower() == str(b).strip().lower()


def apply_value_replacement(cond, column, old_value, new_value):
    """Sostituzione massiva di un valore in una condizione di libreria.

    Ritorna (nuova_cond, changes). Pure: lavora su una copia profonda e non
    muta l'originale. 'changes' e' la lista delle modifiche per l'anteprima:
    ogni elemento e' un dict {name, where, column, old, new}.

    - Scorre OGNI lista di condizioni (qualsiasi lista di dict con chiave
      'value': conditions, exclude_conditions, dest_conditions, antecedent...):
      se la colonna combacia (o 'column' e' vuota = qualsiasi colonna) E il
      valore e' uguale a old_value (trimmed, case-insensitive) -> imposta new.
    - Testo 'formula' (formula_condition): se 'column' e' indicata agisce solo
      quando la colonna compare nella formula; sostituisce il letterale tra
      apici 'old_value' -> 'new_value'.
    """
    new_cond = copy.deepcopy(cond)
    changes = []
    name = str(new_cond.get("name", "") or "?")
    col_target = str(column or "").strip()

    for key, val in new_cond.items():
        if not isinstance(val, list):
            continue
        for elem in val:
            if not isinstance(elem, dict) or "value" not in elem:
                continue
            if col_target and not _eq(elem.get("column", ""), col_target):
                continue
            if _eq(elem.get("value", ""), old_value):
                elem["value"] = new_value
                changes.append({
                    "name": name, "where": key,
                    "column": elem.get("column", ""),
                    "old": old_value, "new": new_value,
                })

    formula = new_cond.get("formula")
    if isinstance(formula, str) and formula.strip():
        column_present = (not col_target) or bool(
            re.search(r"\b" + re.escape(col_target) + r"\b", formula, re.IGNORECASE)
        )
        if column_present:
            pattern = re.compile(r"'" + re.escape(str(old_value)) + r"'", re.IGNORECASE)
            replaced, n = pattern.subn("'" + str(new_value) + "'", formula)
            if n:
                new_cond["formula"] = replaced
                changes.append({
                    "name": name, "where": "formula",
                    "column": col_target, "old": old_value, "new": new_value,
                })

    return new_cond, changes

class ConditionStore:
    def __init__(self, path=constants.CONDITIONS_FILE):
        self.path = path
        self.items = []
        self._load()

    def _normalize_condition(self, cond):
        if not isinstance(cond, dict):
            return cond
        normalized = dict(cond)
        normalized["tag"] = str(normalized.get("tag", "") or "").strip()
        normalized["database_label"] = str(normalized.get("database_label", "") or "").strip()
        # Allineato a LibraryController.prepare_condition_for_storage:
        # quando il promemoria è disabilitato, azzera tutti i campi correlati;
        # quando è abilitato con ciclo non valido, defaulted a "monthly".
        normalized["periodic_review_enabled"] = bool(normalized.get("periodic_review_enabled"))
        cycle = str(normalized.get("periodic_review_cycle", "") or "").strip().lower()
        if normalized["periodic_review_enabled"]:
            normalized["periodic_review_cycle"] = cycle if cycle in ("daily", "weekly", "monthly") else "monthly"
            normalized["periodic_review_note"] = str(normalized.get("periodic_review_note", "") or "").strip()
            normalized["periodic_review_last_ack"] = str(normalized.get("periodic_review_last_ack", "") or "").strip()
        else:
            normalized["periodic_review_cycle"] = ""
            normalized["periodic_review_note"] = ""
            normalized["periodic_review_last_ack"] = ""
        return normalized

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.items = [self._normalize_condition(item) for item in data]
                        logger.info(f"Caricate {len(self.items)} condizioni da {self.path}")
                    else:
                        logger.warning(f"Il file {self.path} non contiene una lista. Inizializzato vuoto.")
                        self.items = []
            except Exception as e:
                logger.error(f"Errore caricamento condizioni: {e}")
                messagebox.showerror("Errore Caricamento", f"Impossibile leggere le condizioni da {self.path}:\n{e}")
                self.items = []
        else:
            logger.info(f"File condizioni non trovato. Creato nuovo in {self.path}")
            self.items = []
            self._save()

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.items, f, indent=2, ensure_ascii=False)
            logger.info(f"Salvate {len(self.items)} condizioni in {self.path}")
            return True
        except Exception as e:
            logger.error(f"Errore salvataggio condizioni: {e}")
            try:
                messagebox.showwarning("Errore Salvataggio",
                    f"Impossibile salvare le condizioni su disco:\n{e}\n\nLe modifiche potrebbero andare perse.")
            except Exception:
                pass  # Se il mainloop non è attivo, ignora
            return False

    def add(self, cond):
        self.items.append(self._normalize_condition(cond))
        self._save()

    def delete(self, idx):
        if 0 <= idx < len(self.items):
            del self.items[idx]
            self._save()

    def update(self, idx, cond):
        if 0 <= idx < len(self.items):
            self.items[idx] = self._normalize_condition(cond)
            self._save()

    def names(self):
        return [c.get("name", "#" + str(i + 1)) for i, c in enumerate(self.items)]

    def tags(self):
        return sorted({c.get("tag", "").strip() for c in self.items if c.get("tag", "").strip()})


class MonitorLog:
    _FLUSH_INTERVAL = 10  # Secondi minimo tra scritture su disco

    def __init__(self, path=constants.MONITOR_LOG_FILE):
        self.path = path
        self.entries = []
        self._dirty = False
        self._last_flush = 0
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.entries = data
                        logger.info(f"Caricate {len(self.entries)} voci di log da {self.path}")
                    else:
                        logger.warning(f"Il file {self.path} non contiene una lista. Inizializzato vuoto.")
                        self.entries = []
            except Exception as e:
                logger.warning(f"Errore caricamento log monitor: {e}")
                self.entries = []

    def _save(self, force=False):
        import time
        now = time.time()
        if not force and (now - self._last_flush) < self._FLUSH_INTERVAL:
            self._dirty = True
            return
        try:
            # Mantieni solo gli ultimi 500 eventi
            self.entries = self.entries[-500:]
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, indent=2, ensure_ascii=False)
            self._dirty = False
            self._last_flush = now
        except Exception as e:
            logger.error(f"Errore salvataggio log monitor: {e}")

    def add(self, entry):
        self.entries.append(entry)
        self._save()

    def flush(self):
        """Forza scrittura su disco se ci sono modifiche pendenti."""
        if self._dirty:
            self._save(force=True)

    def clear(self):
        self.entries = []
        self._save(force=True)
        logger.info("Log monitor pulito.")


class GroupStore:
    def __init__(self, path=constants.GROUPS_FILE):
        self.path = path
        self.groups = {}
        self._load()

    def _normalize_group(self, name, payload):
        group_name = str(name or "").strip()
        if isinstance(payload, list):
            conditions = payload
            database_label = ""
        elif isinstance(payload, dict):
            conditions = payload.get("conditions", [])
            database_label = payload.get("database_label", "")
            if not group_name:
                group_name = str(payload.get("name", "") or "").strip()
        else:
            conditions = []
            database_label = ""
        normalized_conditions = []
        for cond in conditions:
            if isinstance(cond, dict):
                item = dict(cond)
                item["tag"] = str(item.get("tag", "") or "").strip()
                if database_label and not str(item.get("database_label", "") or "").strip():
                    item["database_label"] = database_label
                normalized_conditions.append(item)
        return {
            "name": group_name,
            "database_label": str(database_label or "").strip(),
            "conditions": normalized_conditions,
        }

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw_groups = json.load(f)
                    if isinstance(raw_groups, dict):
                        normalized = {}
                        for name, payload in raw_groups.items():
                            group = self._normalize_group(name, payload)
                            if group["name"]:
                                normalized[group["name"]] = group
                        self.groups = normalized
                    else:
                        self.groups = {}
                    logger.info(f"Caricati {len(self.groups)} gruppi da {self.path}")
            except Exception as e:
                logger.error(f"Errore caricamento gruppi: {e}")

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.groups, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Errore salvataggio gruppi: {e}")

    def save_group(self, name, conditions, database_label=""):
        group = self._normalize_group(name, {
            "name": name,
            "database_label": database_label,
            "conditions": conditions,
        })
        if not group["name"]:
            return
        self.groups[group["name"]] = group
        self._save()

    def delete_group(self, name):
        if name in self.groups:
            del self.groups[name]
            self._save()

    def get(self, name):
        return self.groups.get(name)

    def all_groups(self):
        return [self.groups[name] for name in self.names()]

    def names(self):
        return sorted(list(self.groups.keys()))


class DatabaseRegistry:
    def __init__(self, path=constants.DATABASES_FILE):
        self.path = path
        self.items = {}
        self._load()

    def _normalize_label(self, label):
        return str(label or "").strip()

    def _normalize_entry(self, label, payload):
        if isinstance(payload, dict):
            path = str(payload.get("path", "") or "").strip()
        else:
            path = str(payload or "").strip()
        return {
            "label": self._normalize_label(label),
            "path": path,
        }

    def _load(self):
        if not os.path.exists(self.path):
            self._save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                normalized = {}
                for label, payload in data.items():
                    entry = self._normalize_entry(label, payload)
                    if entry["label"]:
                        normalized[entry["label"]] = entry
                self.items = normalized
            else:
                self.items = {}
        except Exception as e:
            logger.error(f"Errore caricamento registro database: {e}")
            self.items = {}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.items, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Errore salvataggio registro database: {e}")

    def remember(self, label, path=""):
        normalized_label = self._normalize_label(label)
        if not normalized_label:
            return ""
        entry = self._normalize_entry(normalized_label, {"path": path})
        current = self.items.get(normalized_label, {})
        if current.get("path") and not entry["path"]:
            entry["path"] = current["path"]
        self.items[normalized_label] = entry
        self._save()
        return normalized_label

    def set_path(self, label, path):
        normalized_label = self.remember(label, path)
        if normalized_label:
            self.items[normalized_label]["path"] = str(path or "").strip()
            self._save()
        return normalized_label

    def get_path(self, label):
        entry = self.items.get(self._normalize_label(label))
        return entry.get("path", "") if entry else ""

    def names(self):
        return sorted(self.items.keys())

    def entries(self):
        return [self.items[label] for label in self.names()]
