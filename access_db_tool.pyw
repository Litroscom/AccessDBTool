#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Access DB Quality Control Tool - v6.0 (MODULAR)
Entry point principale.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import queue
import threading
import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import tkinter.scrolledtext as st

# Import Moduli Locali
import constants
from logger_config import setup_logging
import theme_config
import ui_helpers
from db_manager import DatabaseManager
from engines import ConditionExecutor, SimilarityEngine
from storage import ConditionStore, MonitorLog, GroupStore, DatabaseRegistry
from monitor_engine import MonitorEngine
import ui_components
from ui_components import (
    NotificationPopup, ColumnSelector, MultiConditionBuilder,
    ConditionSaveDialog, RecordEditorDialog, GroupSelector,
    DependentConditionBuilder, RowCrossColumnBuilder,
    LookupValidationBuilder, AggregateThresholdBuilder,
    FormatValidationBuilder, DailyCoverageBuilder, MandatoryRecordBuilder,
    periodic_review_summary,
)
from data_profiler import DataProfiler

# Gestione suoni
try:
    import winsound
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False

# Inizializza Logging
logger = setup_logging(constants._BASE_DIR)

class GroupStoreAdapter:
    def __init__(self, app):
        self.app = app

    def names(self):
        return [group.get("name", "") for group in self.app._get_effective_groups()]

    def get(self, name):
        for group in self.app._get_effective_groups():
            if group.get("name") == name:
                return group
        return None

    def save_group(self, name, conditions, database_label=""):
        self.app.group_store.save_group(name, conditions, database_label=database_label)

    def delete_group(self, name):
        self.app.group_store.delete_group(name)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        logger.info("Avvio Access DB Quality Control Tool v6.0...")
        self.title(constants.APP_TITLE)
        self.geometry("1300x900")
        self.minsize(1024, 600)
        
        # Componenti Logici
        self.db = DatabaseManager()
        self.executor = ConditionExecutor(self.db)
        self.store = ConditionStore()
        self.group_store = GroupStore()
        self.db_registry = DatabaseRegistry()
        self.group_store_adapter = GroupStoreAdapter(self)
        self.mon_log = MonitorLog()
        self.monitor_queue = queue.Queue()
        self.monitor = MonitorEngine(self.db, self.executor, self.monitor_queue)
        self.status = tk.StringVar(value="Pronto")
        # Stato dell'applicazione
        self.current_result = None
        self._all_rows = []
        self._result_cols = []
        self._active_ctype = None
        self.sel_tables = []
        self._batch_running = False
        self._loaded_condition_idx = None
        self._lib_items = []
        self._dash_items = []
        self._dash_state_by_key = {}
        self.current_db_label = ""
        self.var_ctype = tk.StringVar()
        self.var_saved = tk.StringVar()
        self.var_lib_tag = tk.StringVar(value="Tutti")
        
        # Inizializza placeholder UI
        self.btn_mon_start = None
        self.btn_mon_stop = None
        self.mon_indicator = None
        self.cmb_saved = None
        self.cmb_macro_filter = None
        self.cmb_lib_tag = None
        self.res_menu = None
        self.active_builder = None
        self.mon_tree = None
        self.db_registry_tree = None
        self.lbl_db_registry_path = None
        
        # Inizializza Libreria
        self._refresh_lib()
        
        # Layout principale
        self.main_container = ttk.Frame(self, style="V5.TFrame")
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Stili UI
        self.style = theme_config.setup_theme(self)
        
        self._build_menu()
        self._bind_global_shortcuts()
        self._build_layout()
        self._poll_monitor()
        
        self.protocol("WM_DELETE_WINDOW", self._quit)
        logger.info("Interfaccia caricata.")

    def _build_menu(self):
        menu_bg = "#2B3E50"
        menu_fg = "#FFFFFF"
        menu_active_bg = "#4E5D6C"
        menu_active_fg = "#FFFFFF"
        menu_disabled_fg = "#8696A7"

        mb = tk.Menu(self, bg=menu_bg, fg=menu_fg, activebackground=menu_active_bg,
                     activeforeground=menu_active_fg, disabledforeground=menu_disabled_fg,
                     font=("Segoe UI", 9))
        fm = tk.Menu(mb, tearoff=0, bg=menu_bg, fg=menu_fg, activebackground=menu_active_bg,
                     activeforeground=menu_active_fg, disabledforeground=menu_disabled_fg,
                     font=("Segoe UI", 9))
        fm.add_command(label="Apri Database...", command=self._open_db)
        fm.add_command(label="Chiudi Database", command=self._close_db)
        fm.add_separator()
        fm.add_command(label="Esporta CSV Risultati...", command=self._export_csv)
        fm.add_separator()
        fm.add_command(label="Esci", command=self._quit)
        mb.add_cascade(label="File", menu=fm)

        cm = tk.Menu(mb, tearoff=0, bg=menu_bg, fg=menu_fg, activebackground=menu_active_bg,
                     activeforeground=menu_active_fg, disabledforeground=menu_disabled_fg,
                     font=("Segoe UI", 9))
        cm.add_command(label="Salva condizione corrente...", command=lambda: self._save_cond(False))
        cm.add_command(label="Salva come nuova...", command=lambda: self._save_cond(True))
        cm.add_command(label="Gestisci libreria...", command=self._open_manager)
        cm.add_separator()
        cm.add_command(label="Esporta libreria condizioni...", command=self._export_conditions)
        cm.add_command(label="Importa condizioni da file...", command=self._import_conditions)
        mb.add_cascade(label="Condizioni", menu=cm)

        mm = tk.Menu(mb, tearoff=0, bg=menu_bg, fg=menu_fg, activebackground=menu_active_bg,
                     activeforeground=menu_active_fg, disabledforeground=menu_disabled_fg,
                     font=("Segoe UI", 9))
        mm.add_command(label="Avvia monitor", command=self._start_monitor)
        mm.add_command(label="Ferma monitor", command=self._stop_monitor)
        mm.add_separator()
        mm.add_command(label="Annulla analisi batch", command=self._cancel_batch)
        mb.add_cascade(label="Monitor/Batch", menu=mm)

        self.config(menu=mb)

    def _bind_global_shortcuts(self):
        bindings = {
            "h": lambda: self._go_to_tab("db"),
            "a": self._open_db,
            "c": self._close_db,
            "i": self._run_profiler,
            "e": self._run_all_batch,
            "g": self._open_manager,
            "r": self._run_current,
            "s": self._save_to_lib,
            "u": self._update_to_lib,
            "l": self._clear_builder,
            "v": self._start_monitor,
            "f": self._stop_monitor,
            "p": self._clear_mon_log,
            "q": self._verify_active_formula,
            "t": lambda: self._go_to_tab("build"),
            "d": lambda: self._go_to_tab("dash"),
        }
        for letter, callback in bindings.items():
            self.bind_all(f"<Alt-{letter}>", lambda _evt, cb=callback: self._handle_global_shortcut(cb), add="+")

    def _handle_global_shortcut(self, callback):
        focused = self.focus_displayof()
        if focused is None:
            return "break"
        try:
            top = focused.winfo_toplevel()
            if top is not self:
                return "break"
        except Exception:
            return "break"
        try:
            callback()
        except Exception:
            pass
        return "break"

    def _go_to_tab(self, tab_name):
        tab_map = {
            "build": "controls",
            "dash": "dashboard",
        }
        tab_id = tab_map.get(tab_name, tab_name)
        if hasattr(self, "nav_buttons") and tab_id in self.nav_buttons:
            self._switch_tab(tab_id)
        else:
            self._build_layout()
            self._switch_tab(tab_id)

    def _verify_active_formula(self):
        if self._active_ctype == "formula_condition" and self.active_builder and hasattr(self.active_builder, "verify_formula"):
            self.active_builder.verify_formula()

    def _condition_cache_key(self, cond):
        payload = {}
        for key, value in dict(cond or {}).items():
            if key in ("saved_at", "updated_at", "_group_name"):
                continue
            payload[key] = value
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)

    def _dashboard_state_for_condition(self, cond):
        return self._dash_state_by_key.get(self._condition_cache_key(cond), {})

    def _set_dashboard_state(self, cond, count, status, tag, result=None):
        state = {
            "count": count,
            "status": status,
            "tag": tag,
            "result": result,
            "updated_at": datetime.now().isoformat(),
        }
        self._dash_state_by_key[self._condition_cache_key(cond)] = state
        return state

    def _periodic_review_text(self, cond):
        return periodic_review_summary(cond).get("label", "-")

    def _dashboard_row_values(self, idx, cond, count=None, status=None):
        state = self._dashboard_state_for_condition(cond)
        effective_count = state.get("count", "-") if count is None else count
        effective_status = state.get("status", "Pronto") if status is None else status
        tp = constants.CONDITION_TYPES.get(cond.get("type", ""), cond.get("type", ""))
        return (
            idx + 1,
            cond.get("_group_name", ""),
            self._stored_database_label_for_condition(cond),
            cond.get("name", ""),
            self._periodic_review_text(cond),
            cond.get("tag", ""),
            tp,
            effective_count,
            effective_status,
        )

    def _database_registry_rows(self):
        rows = []
        current_path = str(getattr(self.db, "db_path", "") or "").strip()
        current_path_norm = os.path.normcase(current_path) if current_path else ""
        for entry in self.db_registry.entries():
            label = entry.get("label", "")
            path = entry.get("path", "")
            path_exists = bool(path and os.path.exists(path))
            path_norm = os.path.normcase(path) if path else ""
            if self.db.connected and current_path_norm and path_norm == current_path_norm:
                state = "APERTO"
            elif path_exists:
                state = "PRONTO"
            else:
                state = "DA RICOLLEGARE"
            rows.append({
                "label": label,
                "path": path,
                "state": state,
            })
        return rows

    def _refresh_database_registry_ui(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "_refresh_registry"):
            self.current_view._refresh_registry()
            return
        if not self.db_registry_tree or not self.db_registry_tree.winfo_exists():
            return
        self.db_registry_tree.delete(*self.db_registry_tree.get_children())
        for idx, entry in enumerate(self._database_registry_rows()):
            self.db_registry_tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(entry["label"], entry["state"]),
            )
        if self.lbl_db_registry_path and self.lbl_db_registry_path.winfo_exists():
            self.lbl_db_registry_path.config(text="Seleziona un database collegato per vedere il percorso.")

    def _on_db_registry_select(self, _evt=None):
        if not self.db_registry_tree or not self.db_registry_tree.winfo_exists():
            return
        sel = self.db_registry_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        rows = self._database_registry_rows()
        if idx >= len(rows):
            return
        entry = rows[idx]
        text = entry["path"] or "Percorso non ancora associato."
        if self.lbl_db_registry_path and self.lbl_db_registry_path.winfo_exists():
            self.lbl_db_registry_path.config(text=text)

    def _build_layout(self):
        for w in self.main_container.winfo_children(): w.destroy()

        # Main horizontal: sidebar + content
        main_frame = ttk.Frame(self.main_container)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Sidebar icon-based (~44px)
        self.sidebar = ttk.Frame(main_frame, width=44, style="dark.TFrame")
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        # Content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Barra navigazione tab
        self.nav_bar = ttk.Frame(content_frame)
        self.nav_bar.pack(fill=tk.X, padx=8, pady=(8, 0))

        self.nav_buttons = {}
        for nav_id, label, icon in [
            ("db", "Database", "🗄"),
            ("controls", "Controlli", "⚙"),
            ("dashboard", "Dashboard", "📊"),
        ]:
            btn = ttk.Button(
                self.nav_bar, text=f"{icon} {label}",
                command=lambda nid=nav_id: self._switch_tab(nid),
                bootstyle="secondary-outline",
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.nav_buttons[nav_id] = btn

        # Pannello principale
        self.main_panel = ttk.Frame(content_frame, padding=8)
        self.main_panel.pack(fill=tk.BOTH, expand=True)

        # Status bar
        self._build_status_bar(self.main_container)

        # Mostra tab iniziale
        self._switch_tab("db")

    def _build_status_bar(self, parent):
        sb = ttk.Frame(parent, bootstyle="dark")
        sb.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_label = ttk.Label(
            sb, textvariable=self.status,
            bootstyle="inverse-dark", padding=(8, 4)
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.mon_indicator = ttk.Label(
            sb, text=" MONITOR OFF ",
            bootstyle="inverse-danger", padding=(8, 2)
        )
        self.mon_indicator.pack(side=tk.RIGHT)

    def _switch_tab(self, tab_id):
        for btn in self.nav_buttons.values():
            btn.configure(bootstyle="secondary-outline")
        self.nav_buttons[tab_id].configure(bootstyle="primary")

        for w in self.main_panel.winfo_children():
            w.destroy()

        if tab_id == "db":
            from views.database_view import DatabaseView
            self.current_view = DatabaseView(self.main_panel, self)
            self.current_view.refresh()
        elif tab_id == "controls":
            from views.builder_view import BuilderView
            self.current_view = BuilderView(self.main_panel, self)
        elif tab_id == "dashboard":
            from views.dashboard_view import DashboardView
            self.current_view = DashboardView(self.main_panel, self)
            self.current_view._refresh()

        self.current_view.pack(fill=tk.BOTH, expand=True)

    def _get_dash_tree(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "dash_tree"):
            return self.current_view.dash_tree
        return getattr(self, "dash_tree", None)

    def _get_res_tree(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "res_tree"):
            return self.current_view.res_tree
        if hasattr(self, "current_view") and hasattr(self.current_view, "results_view"):
            return getattr(self.current_view.results_view, "res_tree", None)
        return getattr(self, "res_tree", None)

    def _get_res_lbl(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "res_lbl"):
            return self.current_view.res_lbl
        if hasattr(self, "current_view") and hasattr(self.current_view, "results_view"):
            return getattr(self.current_view.results_view, "res_lbl", None)
        return getattr(self, "res_lbl", None)

    def _on_dash_double_click(self, evt):
        dt = self._get_dash_tree()
        if dt is None: return
        sel = dt.selection()
        if not sel: return
        try:
            item = dt.item(sel[0])
            idx = int(item['values'][0]) - 1
            cond = self._dash_items[idx]
            state = self._dashboard_state_for_condition(cond)
            result = state.get("result")
            if result:
                self._load_cond_into_builder(cond)
                self._show_results(result)
                self.status.set(f"Riaperto ultimo risultato: {cond.get('name', '')}")
                return
            self._start_dashboard_execution(idx, cond)
        except Exception as e:
            logger.error(f"Errore caricamento condizione da dash: {e}")

    # --- LOGICA ---

    def _suggest_database_label(self, path):
        return os.path.basename(str(path or "").strip())

    def _register_database_reference(self, label, path=""):
        normalized_label = str(label or "").strip()
        if not normalized_label and path:
            normalized_label = self._suggest_database_label(path)
        if normalized_label:
            if path:
                self.db_registry.set_path(normalized_label, path)
            else:
                self.db_registry.remember(normalized_label)
            self._refresh_database_registry_ui()
        return normalized_label

    def _sync_open_database_ui(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "refresh"):
            self.current_view.refresh()
        else:
            if hasattr(self, "lbl_db"):
                if self.db.connected:
                    label = self.current_db_label or self._suggest_database_label(self.db.db_path)
                    self.lbl_db.config(text=f"{label}\n{self.db.db_path}")
                else:
                    self.lbl_db.config(text="Nessun DB")
            if hasattr(self, "lst_tables"):
                self.lst_tables.delete(0, tk.END)
                if self.db.connected:
                    for table in self.db.tables:
                        self.lst_tables.insert(tk.END, table)
            self._refresh_database_registry_ui()

    def _connect_active_database(self, path, database_label=""):
        if self.db.connected and self.db.db_path != path:
            self.db.disconnect()
        self.db.connect(path)
        self.current_db_label = self._register_database_reference(database_label, path)
        self._sync_open_database_ui()
        self.status.set(f"DB aperto: {self.current_db_label or os.path.basename(path)}")
        logger.info(f"Database aperto: {path} [{self.current_db_label}]")
        return self.current_db_label

    def _resolve_database_path(self, database_label="", interactive=False):
        label = str(database_label or "").strip()
        if not label and self.current_db_label:
            label = self.current_db_label

        if label and self.db.connected and self.current_db_label == label and os.path.exists(self.db.db_path):
            return label, self.db.db_path

        stored_path = self.db_registry.get_path(label) if label else ""
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

        resolved_label = label or self._suggest_database_label(path)
        self._register_database_reference(resolved_label, path)
        return resolved_label, path

    def _ensure_active_database_for_label(self, database_label="", interactive=False):
        label, path = self._resolve_database_path(database_label, interactive=interactive)
        if not path:
            return False
        if self.db.connected and self.db.db_path == path:
            if label:
                self.current_db_label = self._register_database_reference(label, path)
                self._sync_open_database_ui()
            return True
        try:
            self._stop_monitor()
            self.db.disconnect()
            self._connect_active_database(path, label)
            return True
        except Exception as e:
            messagebox.showerror("Errore", str(e))
            logger.error(f"Errore apertura DB '{label}': {e}")
            return False

    def _database_label_for_condition(self, cond):
        label = str(cond.get("database_label", "") or "").strip()
        if label:
            return label
        if self.current_db_label:
            return self.current_db_label
        if self.db.connected and self.db.db_path:
            return self._register_database_reference("", self.db.db_path)
        return ""

    def _prepare_condition_for_storage(self, cond):
        prepared = dict(cond)
        prepared["database_label"] = self._database_label_for_condition(prepared)
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

    def _stored_database_label_for_condition(self, cond):
        return str(cond.get("database_label", "") or "").strip()

    def _group_database_label(self, conditions):
        for cond in conditions or []:
            label = str(cond.get("database_label", "") or "").strip()
            if label:
                return label
        return self.current_db_label

    def _guess_database_label_for_tag(self, tag):
        normalized_tag = str(tag or "").strip().lower()
        if not normalized_tag:
            return ""
        matches = []
        for label in self.db_registry.names():
            label_norm = label.lower()
            stem_norm = os.path.splitext(label_norm)[0]
            if normalized_tag == label_norm or normalized_tag == stem_norm:
                return label
            if normalized_tag in label_norm or normalized_tag in stem_norm:
                matches.append(label)
        return matches[0] if len(matches) == 1 else ""

    def _build_tag_groups(self):
        groups_by_tag = {}
        for cond in self.store.items:
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
                db_label = self._guess_database_label_for_tag(tag)

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
        explicit_groups = self.group_store.all_groups()
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

    def _iter_group_conditions(self):
        for group in self._get_effective_groups():
            group_name = group.get("name", "")
            group_db_label = str(group.get("database_label", "") or "").strip()
            for cond in group.get("conditions", []):
                item = dict(cond)
                item["_group_name"] = group_name
                item["database_label"] = str(item.get("database_label", "") or "").strip() or group_db_label
                yield item

    def _all_condition_tags(self):
        tags = set(self.store.tags())
        for cond in self._iter_group_conditions():
            tag = str(cond.get("tag", "") or "").strip()
            if tag:
                tags.add(tag)
        return sorted(tags)

    def _get_dashboard_items(self, tag):
        selected = str(tag or "").strip()
        items = list(self._iter_group_conditions())
        if not items:
            items = [dict(cond, _group_name="Libreria corrente") for cond in self.store.items]
        if selected and selected != "Tutti":
            items = [item for item in items if str(item.get("tag", "") or "").strip() == selected]
        return items

    def _prepare_batch_database_paths(self, batch_items):
        db_paths = {}
        for cond in batch_items:
            label = self._stored_database_label_for_condition(cond)
            if not label:
                resolved_label, path = self._resolve_database_path("", interactive=True)
                if not path:
                    return None
                cond["database_label"] = resolved_label
                label = resolved_label
            if label in db_paths:
                continue
            resolved_label, path = self._resolve_database_path(label, interactive=True)
            if not path:
                return None
            if resolved_label and resolved_label != label:
                cond["database_label"] = resolved_label
                label = resolved_label
            db_paths[label] = path
        return db_paths

    def _open_db(self):
        p = filedialog.askopenfilename(filetypes=[("Access DB", "*.mdb *.accdb")])
        if not p: return
        try:
            self._connect_active_database(p, self._suggest_database_label(p))
        except Exception as e:
            messagebox.showerror("Errore", str(e))
            logger.error(f"Errore apertura DB: {e}")

    def _close_db(self):
        self._stop_monitor()
        self.db.disconnect()
        self.current_db_label = ""
        self._sync_open_database_ui()
        self.status.set("DB chiuso")

    def _get_table_listbox(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "lst_tables"):
            return self.current_view.lst_tables
        return getattr(self, "lst_tables", None)

    def _get_builder_parent(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "frm_dyn"):
            return self.current_view.frm_dyn
        return getattr(self, "frm_dyn", None)

    def _get_col_selector(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "col_selector"):
            return self.current_view.col_selector
        return getattr(self, "col_selector", None)

    def _get_col_selector_selected(self):
        cs = self._get_col_selector()
        if cs:
            return cs.get_selected()
        return []

    def _on_table_sel(self, _evt=None):
        lb = self._get_table_listbox()
        if lb is None:
            return
        self.sel_tables = [lb.get(i) for i in lb.curselection()]
        cs = self._get_col_selector()
        if cs:
            all_cols = []
            for t in self.sel_tables:
                all_cols.extend(self.db.columns(t))
            cs.set_columns(list(set(all_cols)))

    def _on_builder_table_change(self, table):
        self.sel_tables = [table]
        cs = self._get_col_selector()
        if cs:
            cs.set_columns(self.db.columns(table))

    def _on_ctype_change(self, _evt=None):
        ctype_name = self.var_ctype.get()
        rev = {v: k for k, v in constants.CONDITION_TYPES.items()}
        self._active_ctype = rev.get(ctype_name)
        self._update_builder_fields()

    def _update_builder_fields(self):
        parent = self._get_builder_parent()
        if parent is None:
            return
        for w in parent.winfo_children(): w.destroy()
        self.active_builder = None
        if not self._active_ctype: return
        
        if self._active_ctype == "value_comparison":
            self.active_builder = ui_components.ValueComparisonBuilder(parent, self.db, self._on_builder_table_change)
        elif self._active_ctype == "duplicate_check":
            self.active_builder = ui_components.DuplicateBuilder(parent, self.db, self._on_builder_table_change)
        elif self._active_ctype == "similarity_check":
            self.active_builder = ui_components.SimilarityBuilder(parent, self.db, self._on_builder_table_change)
        elif self._active_ctype == "cross_table_existence":
            self.active_builder = ui_components.CrossTableBuilder(parent, self.db, self._on_builder_table_change)
        elif self._active_ctype == "formula_condition":
            self.active_builder = ui_components.FormulaBuilder(parent, self.db, self._on_builder_table_change)
        elif self._active_ctype == "concat_similarity":
            self.active_builder = ui_components.ConcatSimilarityBuilder(parent, self.db, self._on_builder_table_change)
        elif self._active_ctype == "linked_table_intersection":
            self.active_builder = ui_components.LinkedTableBuilder(parent, self.db, self._on_builder_table_change)
            if self.sel_tables: self.active_builder.sec1.set_table(self.sel_tables[0])
            if len(self.sel_tables) > 1: self.active_builder.sec2.set_table(self.sel_tables[1])
        elif self._active_ctype == "format_validation":
            try:
                self.active_builder = FormatValidationBuilder(parent, self.db, self._on_builder_table_change)
            except Exception as _e:
                import traceback as _tb
                logger.error(f"FormatValidationBuilder init error: {_tb.format_exc()}")
                self.status.set(f"Errore builder: {_e}")
        elif self._active_ctype == "daily_coverage_check":
            try:
                self.active_builder = DailyCoverageBuilder(parent, self.db, self._on_builder_table_change)
            except Exception as _e:
                import traceback as _tb
                logger.error(f"DailyCoverageBuilder init error: {_tb.format_exc()}")
                self.status.set(f"Errore builder: {_e}")
        elif self._active_ctype == "mandatory_record_check":
            try:
                self.active_builder = MandatoryRecordBuilder(parent, self.db, self._on_builder_table_change)
            except Exception as _e:
                import traceback as _tb
                logger.error(f"MandatoryRecordBuilder init error: {_tb.format_exc()}")
                self.status.set(f"Errore builder: {_e}")
        elif self._active_ctype == "dependent_condition_check":
            try:
                self.active_builder = DependentConditionBuilder(parent, self.db, self._on_builder_table_change)
            except Exception as _e:
                import traceback as _tb
                logger.error(f"DependentConditionBuilder init error: {_tb.format_exc()}")
                self.status.set(f"Errore builder: {_e}")
        elif self._active_ctype == "row_cross_column_check":
            try:
                self.active_builder = RowCrossColumnBuilder(parent, self.db, self._on_builder_table_change)
            except Exception as _e:
                import traceback as _tb
                logger.error(f"RowCrossColumnBuilder init error: {_tb.format_exc()}")
                self.status.set(f"Errore builder: {_e}")
        elif self._active_ctype == "lookup_validation":
            try:
                self.active_builder = LookupValidationBuilder(parent, self.db, self._on_builder_table_change)
            except Exception as _e:
                import traceback as _tb
                logger.error(f"LookupValidationBuilder init error: {_tb.format_exc()}")
                self.status.set(f"Errore builder: {_e}")
        elif self._active_ctype == "aggregate_threshold_check":
            try:
                self.active_builder = AggregateThresholdBuilder(parent, self.db, self._on_builder_table_change)
            except Exception as _e:
                import traceback as _tb
                logger.error(f"AggregateThresholdBuilder init error: {_tb.format_exc()}")
                self.status.set(f"Errore builder: {_e}")

        if self.active_builder:
            self.active_builder.pack(fill=tk.BOTH, expand=True)
        elif parent.winfo_ismapped():
            ttk.Label(parent, text=f"Configurazione standard per: {self.var_ctype.get()}").pack()

    def _validate_active_builder(self):
        if self.active_builder and hasattr(self.active_builder, "validate"):
            ok, msg = self.active_builder.validate()
            if not ok:
                self.status.set(msg)
                messagebox.showwarning("Configurazione incompleta", msg)
                return False
        return True

    def _run_current(self):
        if not self.db.connected: return messagebox.showwarning("!", "Apri DB")
        ctype = self._active_ctype
        if not ctype: return messagebox.showwarning("!", "Seleziona tipo analisi")
        if not self._validate_active_builder(): return
        cs = self._get_col_selector()
        selected_cols = cs.get_selected() if cs else []
        
        cond = {
            "type": ctype,
            "name": "Analisi Manuale",
            "tables": self.sel_tables,
            "columns": selected_cols,
            "display_columns": selected_cols,
        }
        if self.active_builder:
            cond.update(self.active_builder.get_config())
        cond = self._prepare_condition_for_storage(cond)
        threading.Thread(target=self._execute_task, args=(cond,), daemon=True).start()

    def _execute_task(self, cond):
        self.after(0, lambda: self.status.set("Esecuzione in corso..."))
        try:
            res = self.executor.run(cond)
            if isinstance(res, dict):
                res["_condition"] = cond
                res["_condition_type"] = cond.get("type")
            self.after(0, lambda: self._show_results(res))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Errore", str(e)))

    def _show_results(self, res):
        self.current_result = res
        self._switch_tab("dashboard")
        if hasattr(self, "current_view") and hasattr(self.current_view, "show_results"):
            self.current_view.show_results(res)
        self.status.set("Risultati caricati.")

    def _apply_res_filter(self, _evt=None):
        res_tree = self._get_res_tree()
        res_lbl = self._get_res_lbl()
        if res_tree is None or res_lbl is None:
            return
        if not self.current_result:
            return
        
        res_tree.delete(*res_tree.get_children())
        rows = self.current_result.get("rows", [])
        
        count = 0
        for i, r in enumerate(rows):
            res_tree.insert("", tk.END, iid=str(i), values=r)
            count += 1
        
        res_lbl.config(text=f"{self.current_result['title']} ({count} record)")

    def _selected_dashboard_index(self):
        dt = self._get_dash_tree()
        if dt is None:
            return None
        sel = dt.selection()
        if not sel:
            return None
        item = dt.item(sel[0])
        values = item.get("values", [])
        if not values:
            return None
        return int(values[0]) - 1

    def _run_selected_dashboard_check(self):
        idx = self._selected_dashboard_index()
        if idx is None:
            return messagebox.showinfo("Dashboard", "Seleziona un controllo dalla dashboard.")
        if idx < 0 or idx >= len(self._dash_items):
            return
        self._start_dashboard_execution(idx, self._dash_items[idx])

    def _start_dashboard_execution(self, idx, cond):
        if not self._ensure_active_database_for_label(self._database_label_for_condition(cond), interactive=True):
            return
        self._set_dashboard_state(cond, "-", "In corso...", "running")
        self._update_dash_row(idx, "-", "In corso...", "running")
        threading.Thread(target=self._execute_dashboard_task, args=(idx, dict(cond)), daemon=True).start()

    def _execute_dashboard_task(self, idx, cond):
        self.after(0, lambda: self.status.set(f"Esecuzione dashboard in corso: {cond.get('name', '')}"))
        try:
            res = self.executor.run(cond)
            if isinstance(res, dict):
                res["_condition"] = cond
                res["_condition_type"] = cond.get("type")
            self.after(0, lambda: self._complete_dashboard_task(idx, cond, res))
        except Exception as e:
            self.after(0, lambda: self._complete_dashboard_task_error(idx, cond, str(e)))

    def _complete_dashboard_task(self, idx, cond, res):
        tag = "error" if res["count"] > 0 else "ok"
        status = "Completato"
        self._set_dashboard_state(cond, res["count"], status, tag, result=res)
        self._update_dash_row(idx, res["count"], status, tag)
        self._show_results(res)

    def _complete_dashboard_task_error(self, idx, cond, error_text):
        self._set_dashboard_state(cond, "ERR", "Errore", "error")
        self._update_dash_row(idx, "ERR", "Errore", "error")
        self.status.set(f"Errore su '{cond.get('name', '')}': {error_text}")
        messagebox.showerror("Errore", error_text)

    def _run_all_batch(self):
        if self._batch_running: return
        if not self._dash_items:
            return messagebox.showinfo("Info", "Nessuna condizione disponibile nel batch corrente.")
        db_paths = self._prepare_batch_database_paths(self._dash_items)
        if not db_paths:
            self.status.set("Batch annullato: risoluzione database interrotta.")
            return
        self._batch_running = True
        threading.Thread(target=self._batch_worker, args=(db_paths,), daemon=True).start()

    def _batch_worker(self, db_paths):
        batch_items = list(self._dash_items)
        grouped = {}
        for idx, cond in enumerate(batch_items):
            label = self._stored_database_label_for_condition(cond)
            grouped.setdefault(label, []).append((idx, dict(cond)))

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

        self._batch_running = False
        if errors:
            self.after(0, lambda: self.status.set("Batch completato con errori."))
            logger.error("Batch multi-db completato con errori: %s", " | ".join(errors))
        else:
            self.after(0, lambda: self.status.set("Analisi batch multi-database finita."))

    def _run_batch_for_database(self, database_label, db_path, items):
        if not db_path:
            raise RuntimeError(f"Nessun percorso risolto per il database '{database_label}'.")
        db = DatabaseManager()
        db.connect(db_path)
        executor = ConditionExecutor(db)
        try:
            for idx, cond in items:
                if not self._batch_running:
                    break
                self.after(
                    0,
                    lambda row_idx=idx, row_cond=dict(cond), label=database_label: self._mark_batch_row_running(
                        row_idx, row_cond, label
                    ),
                )
                try:
                    res = executor.run(cond)
                    if isinstance(res, dict):
                        res["_condition"] = dict(cond)
                        res["_condition_type"] = cond.get("type")
                    tag = "error" if res["count"] > 0 else "ok"
                    status = "Completato"
                    count = res["count"]
                except Exception as e:
                    logger.error(f"Errore batch su '{cond.get('name', '?')}' [{database_label}]: {e}")
                    tag = "error"
                    status = "Errore"
                    count = "ERR"
                    res = None
                self.after(
                    0,
                    lambda row_idx=idx, row_cond=dict(cond), row_count=count, row_status=status, row_tag=tag, row_res=res: self._finalize_batch_row(
                        row_idx, row_cond, row_count, row_status, row_tag, row_res
                    ),
                )
        finally:
            db.disconnect()

    def _mark_batch_row_running(self, idx, cond, database_label):
        self._set_dashboard_state(cond, "-", f"In corso ({database_label})...", "running")
        self._update_dash_row(idx, "-", f"In corso ({database_label})...", "running")

    def _finalize_batch_row(self, idx, cond, count, status, tag, result):
        self._set_dashboard_state(cond, count, status, tag, result=result)
        self._update_dash_row(idx, count, status, tag)

    def _update_dash_row(self, idx, count, status, tag):
        dt = self._get_dash_tree()
        if dt is None:
            return
        children = dt.get_children()
        if idx < 0 or idx >= len(children) or idx >= len(self._dash_items):
            return
        iid = children[idx]
        cond = self._dash_items[idx]
        dt.item(
            iid,
            values=self._dashboard_row_values(idx, cond, count, status),
            tags=(tag,),
        )

    def _refresh_dash(self):
        dt = self._get_dash_tree()
        if dt is None:
            return
        for i in dt.get_children(): dt.delete(i)
        selected_tag = self.var_macro_filter.get().strip() if hasattr(self, "var_macro_filter") else "Tutti"
        self._dash_items = self._get_dashboard_items(selected_tag)
        self._refresh_tag_filters()
        for i, c in enumerate(self._dash_items):
            state = self._dashboard_state_for_condition(c)
            dt.insert(
                "",
                tk.END,
                values=self._dashboard_row_values(i, c),
                tags=(state.get("tag", ""),) if state.get("tag") else (),
            )

    def _poll_monitor(self):
        try:
            while True:
                m = self.monitor_queue.get_nowait()
                try:
                    self._handle_monitor_msg(m)
                except Exception as e:
                    logger.error(f"Errore gestione messaggio monitor {m.get('type', '?')}: {e}")
        except queue.Empty: pass
        self.after(500, self._poll_monitor)

    def _handle_monitor_msg(self, m):
        msg_type = m.get("type")
        if msg_type == "status":
            self.status.set(m.get("msg", "Monitor"))
            return
        if msg_type == "cycle_start":
            self.status.set(f"Monitor: avvio ciclo su {m.get('total', 0)} controlli")
            return
        if msg_type == "progress":
            self.status.set(f"Monitor: {m.get('current', 0)}/{m.get('total', 0)} - {m.get('name', '?')}")
            return

        event_time = datetime.now().strftime("%H:%M:%S")
        mon_tree = getattr(self, "mon_tree", None)
        if msg_type == "check_result":
            name = m.get("name") or m.get("check") or "?"
            count = m.get("count", 0)
            status = "Trovati" if count > 0 else "OK"
            if mon_tree and mon_tree.winfo_exists():
                mon_tree.insert("", 0, values=(event_time, name, status, count))
            self.mon_log.add(dict(m))
            if count > 0 and m.get("sound", True) and HAS_SOUND:
                winsound.Beep(1000, 200)
            return
        if msg_type == "check_error":
            if mon_tree and mon_tree.winfo_exists():
                mon_tree.insert("", 0, values=(event_time, m.get("name", "?"), "Errore", 0))
            self.mon_log.add(dict(m))
            self.status.set(f"Errore monitor: {m.get('name', '?')}")
            return
        if msg_type == "cycle_end":
            self.mon_log.flush()
            self.status.set(
                f"Monitor: ciclo completato, anomalie {m.get('errors_count', 0)} - prossimo avvio {m.get('next_run', '?')}"
            )

    def _start_monitor(self):
        if not self.db.connected:
            return messagebox.showwarning("!", "Apri un Database prima di avviare il monitor.")
        if not self.store.items:
            return messagebox.showwarning("!", "Salva almeno una condizione prima di avviare il monitor.")
        if not self.monitor.start(self.store.items):
            self.status.set("Monitor non avviato.")
            return
        if self.btn_mon_start: self.btn_mon_start.config(state=tk.DISABLED)
        if self.btn_mon_stop: self.btn_mon_stop.config(state=tk.NORMAL)
        if self.mon_indicator: self.mon_indicator.config(text=" MONITOR ON ", bg="#4CAF50")

    def _stop_monitor(self):
        self.monitor.stop()
        self.mon_log.flush()
        if self.btn_mon_start: self.btn_mon_start.config(state=tk.NORMAL)
        if self.btn_mon_stop: self.btn_mon_stop.config(state=tk.DISABLED)
        if self.mon_indicator: self.mon_indicator.config(text=" MONITOR OFF ", bootstyle="danger")

    def _run_profiler(self):
        if not self.db.connected: return messagebox.showwarning("!", "Apri un Database prima di generare Insight.")
        
        self.ins_tree.delete(*self.ins_tree.get_children())
        self.status.set("Generazione insight in corso...")
        self.update()
        
        try:
            p = DataProfiler(self.db)
            self.current_insights = p.analyze()
            
            for i, ins in enumerate(self.current_insights):
                act_label = constants.CONDITION_TYPES.get(ins.get("action", ""), ins.get("action", ""))
                self.ins_tree.insert("", tk.END, iid=str(i), values=[ins.get("title", ""), ins.get("desc", ""), act_label])
                
            self.status.set(f"Generati {len(self.current_insights)} suggerimenti.")
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante l'analisi: {e}")
            self.status.set("Errore generazione insight.")

    def _load_insight(self, event=None):
        sel = self.ins_tree.selection()
        if not sel: return
        try:
            idx = int(sel[0])
            insight = self.current_insights[idx]
            self._load_cond_into_builder(insight.get("config", {}))
            self.status.set(f"Caricato suggerimento: {insight.get('title', '')}")
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile caricare il suggerimento: {e}")

    def _export_csv(self):
        if not self.current_result: return
        p = filedialog.asksaveasfilename(defaultextension=".csv")
        if p:
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(self.current_result["columns"])
                w.writerows(self.current_result["rows"])
            messagebox.showinfo("OK", "Esportato")

    def _export_conditions(self, items=None):
        """Esporta tutte le condizioni (o la lista passata) in un file JSON."""
        items_to_export = items if items is not None else self.store.items
        if not items_to_export:
            messagebox.showwarning("Attenzione", "Nessuna condizione da esportare.")
            return
        default_name = f"condizioni_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        path = filedialog.asksaveasfilename(
            title="Esporta condizioni",
            defaultextension=".json",
            filetypes=[("Condizioni AccessDBTool (*.json)", "*.json"), ("Tutti i file", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return
        try:
            import json as _json
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(items_to_export, f, indent=2, ensure_ascii=False)
            messagebox.showinfo(
                "Esportazione completata",
                f"Esportate {len(items_to_export)} condizioni in:\n{path}"
            )
            logger.info(f"Esportate {len(items_to_export)} condizioni in {path}")
        except Exception as e:
            messagebox.showerror("Errore esportazione", str(e))
            logger.error(f"Errore esportazione condizioni: {e}")

    def _import_conditions(self):
        """Importa condizioni da un file JSON, con scelta merge o sostituzione."""
        path = filedialog.askopenfilename(
            title="Importa condizioni",
            filetypes=[("Condizioni AccessDBTool (*.json)", "*.json"), ("Tutti i file", "*.*")],
        )
        if not path:
            return
        try:
            import json as _json
            with open(path, "r", encoding="utf-8") as f:
                data = _json.load(f)
        except Exception as e:
            messagebox.showerror("Errore lettura file", f"Impossibile leggere il file:\n{e}")
            return

        if not isinstance(data, list):
            messagebox.showerror("Formato non valido", "Il file non contiene una lista di condizioni.")
            return

        valid = [c for c in data if isinstance(c, dict) and "type" in c and "name" in c]
        if not valid:
            messagebox.showwarning("Nessuna condizione", "Nessuna condizione valida trovata nel file.")
            return

        n_existing = len(self.store.items)
        answer = messagebox.askyesnocancel(
            "Modalità importazione",
            f"Trovate {len(valid)} condizioni nel file.\n"
            f"Libreria attuale: {n_existing} condizioni.\n\n"
            "SÌ  → Aggiungi alle condizioni esistenti (duplicati per nome saltati)\n"
            "NO  → Sostituisci tutta la libreria con le condizioni importate\n"
            "ANNULLA → Interrompi",
        )
        if answer is None:
            return

        if answer:  # SÌ = merge
            existing_names = {c.get("name", "").strip().lower() for c in self.store.items}
            added = 0
            for c in valid:
                if c.get("name", "").strip().lower() not in existing_names:
                    self.store.items.append(self.store._normalize_condition(c))
                    existing_names.add(c.get("name", "").strip().lower())
                    added += 1
            msg = f"Aggiunte {added} nuove condizioni ({len(valid) - added} duplicate ignorate)."
        else:  # NO = replace
            self.store.items = [self.store._normalize_condition(c) for c in valid]
            msg = f"Libreria sostituita con {len(valid)} condizioni importate."

        self.store._save()
        self._refresh_lib()
        messagebox.showinfo("Importazione completata", msg)
        logger.info(f"Importazione da {path}: {msg}")

    def _save_cond(self, force_new=False):
        """Compatibilita menu: salva nuova o aggiorna la condizione caricata."""
        if force_new:
            if hasattr(self, "var_saved"):
                self.var_saved.set("")
            self._loaded_condition_idx = None
            return self._save_to_lib()
        if getattr(self, "_loaded_condition_idx", None) is not None:
            return self._update_to_lib()
        if hasattr(self, "var_saved") and self.var_saved.get():
            return self._update_to_lib()
        return self._save_to_lib()

    def _save_to_lib(self):
        ctype = self._active_ctype
        if not ctype: return messagebox.showwarning("!", "Configura una condizione")
        if not self._validate_active_builder(): return
        
        current_tag = self.var_lib_tag.get().strip() if hasattr(self, "var_lib_tag") else ""
        if current_tag == "Tutti":
            current_tag = ""
        dlg = ConditionSaveDialog(self, initial_tag=current_tag)
        self.wait_window(dlg)
        if not dlg.result: return
        name = dlg.result["name"]
        desc = dlg.result["description"]
        tag = dlg.result["tag"]

        cond_data = {
            "name": name,
            "description": desc,
            "tag": tag,
            "type": ctype,
            "display_columns": self._get_col_selector_selected(),
            "saved_at": datetime.now().isoformat(),
            "database_label": self.current_db_label,
            "periodic_review_enabled": dlg.result.get("periodic_review_enabled", False),
            "periodic_review_cycle": dlg.result.get("periodic_review_cycle", ""),
            "periodic_review_note": dlg.result.get("periodic_review_note", ""),
            "periodic_review_last_ack": datetime.now().isoformat() if dlg.result.get("periodic_review_enabled") else "",
        }
        if self.sel_tables: cond_data["table"] = self.sel_tables[0]
        if self.active_builder: cond_data.update(self.active_builder.get_config())
        cond_data = self._prepare_condition_for_storage(cond_data)

        self.store.add(cond_data)
        self._refresh_lib()
        if hasattr(self, "var_lib_tag"):
            self.var_lib_tag.set(tag)
            self._refresh_lib()
        self.var_saved.set(name)
        self._loaded_condition_idx = len(self.store.items) - 1
        self._refresh_dash()
        self.status.set(f"Salvata condizione: {name}")

    def _update_to_lib(self):
        name = self.var_saved.get()
        if not name:
            messagebox.showwarning("!", "Nessuna condizione caricata da aggiornare.\nUsa 'Salva Nuova' per crearne una.")
            return

        ctype = self._active_ctype
        if not ctype: return messagebox.showwarning("!", "Seleziona tipo analisi")
        if not self._validate_active_builder(): return

        idx = self._loaded_condition_idx
        if idx is None:
            idx = -1
            selected_tag = self.var_lib_tag.get().strip() if hasattr(self, "var_lib_tag") else ""
            if selected_tag == "Tutti":
                selected_tag = ""
            for i, c in enumerate(self.store.items):
                if c.get("name") != name:
                    continue
                if selected_tag and c.get("tag", "").strip() != selected_tag:
                    continue
                idx = i
                break
        if idx is None or idx < 0:
            return messagebox.showerror("Errore", "Condizione originale non trovata nella libreria.")

        desc = self.store.items[idx].get("description", "")
        tag = self.store.items[idx].get("tag", "")
        
        cond_data = {
            "name": name,
            "description": desc,
            "tag": tag,
            "type": ctype,
            "display_columns": self._get_col_selector_selected(),
            "updated_at": datetime.now().isoformat(),
            "database_label": self.current_db_label,
            "periodic_review_enabled": self.store.items[idx].get("periodic_review_enabled", False),
            "periodic_review_cycle": self.store.items[idx].get("periodic_review_cycle", ""),
            "periodic_review_note": self.store.items[idx].get("periodic_review_note", ""),
            "periodic_review_last_ack": datetime.now().isoformat() if self.store.items[idx].get("periodic_review_enabled") else "",
        }
        if self.sel_tables: cond_data["table"] = self.sel_tables[0]
        if self.active_builder: cond_data.update(self.active_builder.get_config())
        cond_data = self._prepare_condition_for_storage(cond_data)
        
        self.store.update(idx, cond_data)
        self._refresh_lib()
        self.var_saved.set(name)
        self._refresh_dash()
        self.status.set("Condizione aggiornata!")
        messagebox.showinfo("OK", "Condizione aggiornata con successo!")

    def _refresh_lib(self):
        self._refresh_tag_filters()
        selected_tag = self.var_lib_tag.get().strip() if hasattr(self, "var_lib_tag") else "Tutti"
        self._lib_items = self._filter_conditions_by_tag(selected_tag)
        names = [c.get("name", "") for c in self._lib_items]
        if self.cmb_saved:
            self.cmb_saved["values"] = names
            if self.var_saved.get() not in names:
                self.var_saved.set("")
        if hasattr(self, "current_view") and hasattr(self.current_view, "refresh_lib"):
            self.current_view.refresh_lib()
        self._refresh_dash()

    def _on_lib_filter_change(self, event=None):
        self.var_saved.set("")
        self._loaded_condition_idx = None
        self._refresh_lib()

    def _get_lib_combo(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "cmb_lib"):
            return self.current_view.cmb_lib
        return getattr(self, "cmb_saved", None)

    def _load_from_lib(self, event=None):
        combo = self._get_lib_combo()
        if combo is None:
            return
        idx = combo.current()
        if idx < 0: return
        cond = self._lib_items[idx]
        self._load_cond_into_builder(cond)

    def _filter_conditions_by_tag(self, tag):
        normalized = (tag or "").strip()
        if not normalized or normalized == "Tutti":
            return list(self.store.items)
        return [c for c in self.store.items if c.get("tag", "").strip() == normalized]

    def _refresh_tag_filters(self):
        values = ["Tutti"] + self._all_condition_tags()
        if self.cmb_macro_filter and self.cmb_macro_filter.winfo_exists():
            current = self.var_macro_filter.get().strip() if hasattr(self, "var_macro_filter") else ""
            if current not in values:
                current = "Tutti"
            self.cmb_macro_filter["values"] = values
            self.var_macro_filter.set(current or "Tutti")
        if self.cmb_lib_tag and self.cmb_lib_tag.winfo_exists():
            current = self.var_lib_tag.get().strip() if hasattr(self, "var_lib_tag") else ""
            if current not in values:
                current = "Tutti"
            self.cmb_lib_tag["values"] = values
            self.var_lib_tag.set(current or "Tutti")

    def _find_store_index(self, cond):
        for idx, current in enumerate(self.store.items):
            if current is cond or current == cond:
                return idx
        return None

    def _load_cond_into_builder(self, cond):
        """Carica una condizione nei campi del costruttore e seleziona il tab."""
        if not cond: return
        try:
            cond_db_label = str(cond.get("database_label", "") or "").strip()
            if cond_db_label and cond_db_label != self.current_db_label:
                self._ensure_active_database_for_label(cond_db_label, interactive=False)

            self._switch_tab("controls")

            ctype_key = cond.get("type", "")
            ctype_label = constants.CONDITION_TYPES.get(ctype_key, "")
            if ctype_label:
                self.var_ctype.set(ctype_label)
            
            self.var_saved.set(cond.get("name", ""))
            self._loaded_condition_idx = self._find_store_index(cond)
            tag = cond.get("tag", "").strip()
            if tag and hasattr(self, "var_lib_tag"):
                self.var_lib_tag.set(tag)
                self._refresh_lib()
                self.var_saved.set(cond.get("name", ""))
            
            self._active_ctype = ctype_key
            self._update_builder_fields()

            if ctype_key in ("cross_table_existence",):
                main_tables = [t for t in [cond.get("source_table")] if t]
            else:
                main_tables = [t for t in [cond.get("table")] if t]

            if main_tables:
                self.sel_tables = main_tables

            cs = self._get_col_selector()
            if cs and self.db.connected:
                display_cols = cond.get("display_columns", [])
                all_cols = []
                for t in self.sel_tables:
                    all_cols.extend(self.db.columns(t))
                if all_cols:
                    cs.set_columns(list(dict.fromkeys(all_cols)))
                    cs.set_selected(display_cols)

            if self.active_builder:
                self.active_builder.set_config(cond)

            self.current_view.sync_ctype()
            self.status.set(f"Caricata: {cond.get('name', '?')}")
        except Exception as e:
            import traceback
            self.status.set(f"Errore caricamento: {e}")
            logger.error(f"_load_cond_into_builder error: {traceback.format_exc()}")


    def _open_manager(self): 
        from views.condition_manager_view import ConditionManagerDialog
        ConditionManagerDialog(self, self.store, self._refresh_lib, self._load_cond_into_builder)
    def _clear_builder(self):
        self.var_ctype.set("")
        self.var_saved.set("")
        self._loaded_condition_idx = None
        self._update_builder_fields()
    def _clear_mon_log(self):
        if self.mon_tree and self.mon_tree.winfo_exists():
            self.mon_tree.delete(*self.mon_tree.get_children())
        self.mon_log.clear()
    def _cancel_batch(self): self._batch_running = False

    # --- NUOVE FUNZIONI FASE B ---

    def _result_supports_direct_update(self):
        if not self.current_result or not self.current_result.get("source_table"):
            return False
        cols = self.current_result.get("columns", [])
        blocked_cols = {"Tab1", "Tab2", "Key1", "Key2", "Val1", "Val2", "Sim%"}
        return not any(str(col).endswith(("_1", "_2")) or col in blocked_cols for col in cols)

    def _current_result_condition_type(self):
        if self.current_result and self.current_result.get("_condition_type"):
            return self.current_result.get("_condition_type")
        return self._active_ctype

    def _extract_similarity_exception_payload(self):
        if not self.current_result:
            return {"pair_values": [], "pair_records": [], "left_records": [], "right_records": []}
        cols = self.current_result.get("columns", [])
        sel = self._get_res_tree().selection()
        payload = {"pair_values": [], "pair_records": [], "left_records": [], "right_records": []}
        if not sel or not cols:
            return payload

        left_indexes = [idx for idx, name in enumerate(cols) if str(name).endswith("_1")]
        right_indexes = [idx for idx, name in enumerate(cols) if str(name).endswith("_2")]
        left_key_idx = left_indexes[0] if left_indexes else (0 if len(cols) > 0 else -1)
        left_val_idx = left_indexes[1] if len(left_indexes) > 1 else (1 if len(cols) > 1 else -1)
        right_key_idx = right_indexes[0] if right_indexes else (2 if len(cols) > 2 else -1)
        right_val_idx = right_indexes[1] if len(right_indexes) > 1 else (3 if len(cols) > 3 else -1)

        key_col = ""
        if self.active_builder and hasattr(self.active_builder, "get_exception_column"):
            key_col = self.active_builder.get_exception_column()

        seen = {name: set() for name in payload}
        for iid in sel:
            vals = self._get_res_tree().item(iid, "values")
            if not vals:
                continue
            left_key = str(vals[left_key_idx]).strip() if 0 <= left_key_idx < len(vals) else ""
            left_val = str(vals[left_val_idx]).strip() if 0 <= left_val_idx < len(vals) else ""
            right_key = str(vals[right_key_idx]).strip() if 0 <= right_key_idx < len(vals) else ""
            right_val = str(vals[right_val_idx]).strip() if 0 <= right_val_idx < len(vals) else ""
            pair_values = f"{left_val} | {right_val}" if left_val and right_val else ""
            pair_records = f"{key_col}:{left_key} | {key_col}:{right_key}" if key_col and left_key and right_key else ""
            if pair_values and pair_values.upper() not in seen["pair_values"]:
                payload["pair_values"].append(pair_values)
                seen["pair_values"].add(pair_values.upper())
            if pair_records and pair_records.upper() not in seen["pair_records"]:
                payload["pair_records"].append(pair_records)
                seen["pair_records"].add(pair_records.upper())
            if left_key and left_key.upper() not in seen["left_records"]:
                payload["left_records"].append(left_key)
                seen["left_records"].add(left_key.upper())
            if right_key and right_key.upper() not in seen["right_records"]:
                payload["right_records"].append(right_key)
                seen["right_records"].add(right_key.upper())
        return payload

    def _ensure_active_builder_from_result(self):
        if self.active_builder and hasattr(self.active_builder, "add_exceptions"):
            return
        if not self.current_result:
            return
        cond = self.current_result.get("_condition")
        if not cond:
            return
        ctype = cond.get("type") or self._current_result_condition_type()
        if not ctype:
            return
        if not hasattr(self, "_hidden_builder_frame"):
            self._hidden_builder_frame = ttk.Frame(self)
        self._active_ctype = ctype
        parent = self._get_builder_parent() or self._hidden_builder_frame
        for w in parent.winfo_children():
            w.destroy()
        self.active_builder = None

        import ui_components
        db = self.db
        on_tc = self._on_builder_table_change
        builders = {
            "value_comparison": ui_components.ValueComparisonBuilder,
            "duplicate_check": ui_components.DuplicateBuilder,
            "similarity_check": ui_components.SimilarityBuilder,
            "cross_table_existence": ui_components.CrossTableBuilder,
            "formula_condition": ui_components.FormulaBuilder,
            "concat_similarity": ui_components.ConcatSimilarityBuilder,
            "linked_table_intersection": ui_components.LinkedTableBuilder,
        }
        builder_cls = builders.get(ctype)
        if builder_cls:
            try:
                self.active_builder = builder_cls(parent, db, on_tc)
                self.active_builder.set_config(cond)
            except Exception:
                pass

    def _show_res_menu(self, event):
        iid = self._get_res_tree().identify_row(event.y)
        if not iid: return
        current_sel = set(self._get_res_tree().selection())
        if iid not in current_sel:
            self._get_res_tree().selection_add(iid)
        self._get_res_tree().focus(iid)

        m = tk.Menu(self, tearoff=0)
        edit_state = tk.NORMAL if self._result_supports_direct_update() else tk.DISABLED
        m.add_command(label="Modifica record...", command=self._edit_res_record, state=edit_state)
        m.add_separator()
        m.add_command(label="Sostituzione Massiva...", command=self._bulk_replace_results, state=edit_state)

        self._ensure_active_builder_from_result()

        if self.active_builder and hasattr(self.active_builder, "add_exceptions"):
            ctype = self._current_result_condition_type()
            if ctype != "concat_similarity":
                m.add_separator()
                if ctype == "similarity_check":
                    sim_menu = tk.Menu(m, tearoff=0)
                    sim_menu.add_command(
                        label="Escludi coppia per sempre (valori)",
                        command=lambda: self._add_selected_to_exceptions(mode="pair_values"),
                    )
                    sim_menu.add_command(
                        label="Escludi coppia specifica di record",
                        command=lambda: self._add_selected_to_exceptions(mode="pair_records"),
                    )
                    sim_menu.add_separator()
                    sim_menu.add_command(
                        label="Escludi record sinistri selezionati",
                        command=lambda: self._add_selected_to_exceptions(mode="left_records"),
                    )
                    sim_menu.add_command(
                        label="Escludi record destri selezionati",
                        command=lambda: self._add_selected_to_exceptions(mode="right_records"),
                    )
                    m.add_cascade(label="Esclusioni Somiglianze", menu=sim_menu)
                else:
                    clicked_col = self._get_result_column_from_event(event)
                    target_col = self._resolve_non_fuzzy_exception_target(clicked_col)
                    label = "Aggiungi Selezionati a Esclusioni"
                    if target_col:
                        label = f"Aggiungi '{target_col}' selezionati a Esclusioni"
                    m.add_command(label=label, command=lambda col=target_col: self._add_selected_to_exceptions(col))
            
        m.post(event.x_root, event.y_root)

    def _get_result_column_from_event(self, event):
        if not self.current_result:
            return ""
        col_id = self._get_res_tree().identify_column(event.x)
        if not col_id or col_id == "#0":
            return ""
        try:
            idx = int(str(col_id).lstrip("#")) - 1
        except ValueError:
            return ""
        cols = self.current_result.get("columns", [])
        return cols[idx] if 0 <= idx < len(cols) else ""

    def _resolve_non_fuzzy_exception_target(self, clicked_col=""):
        if not self.active_builder or not self.current_result:
            return ""
        cols = self.current_result.get("columns", [])
        targets = []
        if hasattr(self.active_builder, "get_exception_targets"):
            try:
                targets = self.active_builder.get_exception_targets(cols)
            except Exception:
                targets = []
        if clicked_col and clicked_col in targets:
            return clicked_col
        return targets[0] if targets else ""

    def _add_selected_to_exceptions(self, target_column="", mode="default"):
        sel = self._get_res_tree().selection()
        if not sel or not self.current_result or not self.active_builder: return
        if not hasattr(self.active_builder, "add_exceptions"): return
        
        # Raccoglie i valori delle prime colonne utili in base alla riga selezionata
        vals_to_add = []
        cols = self.current_result.get("columns", [])
        ctype = self._current_result_condition_type()

        if ctype == "similarity_check":
            payload = self._extract_similarity_exception_payload()
            if mode in ("pair_values", "pair_records"):
                vals_to_add = payload.get(mode, [])
                cnt = self.active_builder.add_exceptions(vals_to_add)
            else:
                vals_to_add = payload.get(mode, [])
                if hasattr(self.active_builder, "add_record_exclusions"):
                    cnt = self.active_builder.add_record_exclusions(vals_to_add)
                else:
                    target = target_column or (self.active_builder.get_exception_column() if hasattr(self.active_builder, "get_exception_column") else None)
                    cnt = self.active_builder.add_exceptions(vals_to_add, column=target)
            self._switch_tab("controls")
            self._show_builder_on_controls_tab()
            if vals_to_add:
                if cnt > 0:
                    messagebox.showinfo("OK", f"Aggiunte {cnt} esclusioni al costruttore.")
                else:
                    messagebox.showinfo("Info", "Tutti i valori erano gia presenti nelle esclusioni.")
            return
        
        for idx_str in sel:
            vals = self._get_res_tree().item(idx_str, "values")
            if not vals: continue
            
            if ctype == "cross_table_existence":
                target_col = target_column or (self.active_builder.get_exception_column() if hasattr(self.active_builder, "get_exception_column") else "")
                if target_col and target_col in cols:
                    val = str(vals[cols.index(target_col)]).strip()
                else:
                    val = str(vals[0]).strip()
                if val: vals_to_add.append(val)
            else:
                target_col = target_column or (self.active_builder.get_exception_column() if hasattr(self.active_builder, "get_exception_column") else "")
                if target_col and target_col in cols:
                    val = str(vals[cols.index(target_col)]).strip()
                else:
                    val = str(vals[0]).strip()
                if val: vals_to_add.append(val)
                
        if vals_to_add:
            cnt = self.active_builder.add_exceptions(vals_to_add, column=target_column or None)
            self._switch_tab("controls")
            self._show_builder_on_controls_tab()
            if cnt > 0:
                messagebox.showinfo("OK", f"Aggiunte {cnt} esclusioni al costruttore.")
            else:
                messagebox.showinfo("Info", "Tutti i valori erano gia presenti nelle esclusioni.")

    def _show_builder_on_controls_tab(self):
        if not self.active_builder:
            return
        if not hasattr(self, "current_view") or not hasattr(self.current_view, "_sections"):
            return
        base = self.current_view._sections.get("base")
        if not base:
            return
        if not base["built"]:
            self.current_view._build_section_base(base["body"])
            base["built"] = True
        if not base["expanded"]:
            base["body"].pack(fill=tk.BOTH, expand=True)
            base["expanded"] = True
            base["header"].configure(bootstyle="primary")
        self.current_view.sync_ctype()

    def _bulk_replace_results(self):
        if not self._result_supports_direct_update():
            return messagebox.showwarning(
                "Operazione non disponibile",
                "La sostituzione massiva e disponibile solo per risultati che mappano in modo univoco a una singola tabella."
            )
        if not hasattr(self, "current_result") or not self.current_result:
            return messagebox.showwarning("!", "Nessun risultato caricato correttamente.")
            
        rows = self.current_result.get("rows", [])
        if not rows: 
            return messagebox.showwarning("!", "Nessun record presente nei risultati.")
        
        cols = self.current_result.get("columns", [])
        dlg = ui_components.BulkReplaceDialog(self, cols, len(rows))
        self.wait_window(dlg)
        
        if dlg.result:
            col = dlg.result["column"]
            val = dlg.result["value"]
            
            # Identifica PK
            pk_col = None
            for c in cols:
                if c.lower() in ("id", "pk", "codice", "code", "key"):
                    pk_col = c
                    break
            if not pk_col: pk_col = cols[0]
            
            # Identifica Tabella
            table = self.current_result.get("source_table")
            if not table and self.active_builder:
                config = self.active_builder.get_config()
                table = config.get("table") or config.get("source_table")
            
            if not table:
                return messagebox.showerror("Errore", "Impossibile identificare la tabella sorgente dei risultati.")

            # Trova indici
            try:
                pk_idx = cols.index(pk_col)
            except ValueError:
                return messagebox.showerror("Errore", f"Impossibile trovare la colonna PK {pk_col} nei risultati.")

            # Pulizia nomi colonne per SQL (rimuovi _1, _2 se presenti in similarity)
            sql_col = col
            if sql_col.endswith(("_1", "_2")) and sql_col not in self.db.columns(table):
                sql_col = sql_col[:-2]
            
            sql_pk = pk_col
            if sql_pk.endswith(("_1", "_2")) and sql_pk not in self.db.columns(table):
                sql_pk = sql_pk[:-2]
            table_cols = set(self.db.columns(table))
            if sql_col not in table_cols:
                return messagebox.showerror("Errore", f"La colonna '{sql_col}' non esiste nella tabella [{table}].")
            if sql_pk not in table_cols:
                return messagebox.showerror("Errore", f"La chiave '{sql_pk}' non esiste nella tabella [{table}].")

            # Itera SOLO sui record visibili (filtrati)
            visible_iids = self._get_res_tree().get_children()
            count = 0
            updated_count = 0
            for iid in visible_iids:
                try:
                    idx = int(iid)
                    r = rows[idx]
                    pk_val = r[pk_idx]
                except (ValueError, IndexError):
                    continue

                if pk_val is not None:
                    try:
                        typed_value = self.db.cast_value(table, sql_col, val)
                        typed_pk = self.db.cast_value(table, sql_pk, pk_val)
                        sql = f"UPDATE [{table}] SET [{sql_col}] = ? WHERE [{sql_pk}] = ?"
                        affected = self.db.execute(sql, (typed_value, typed_pk))
                        if affected > 0:
                            updated_count += affected
                        count += 1
                    except Exception as e:
                        logger.error(f"Errore update massivo record {pk_val} su {table}: {e}")
            
            messagebox.showinfo("Successo", f"Aggiornamento completato.\n{updated_count} record effettivamente modificati su {len(visible_iids)} filtrati.")
            self.status.set(f"Ultima operazione: Sostituzione massiva ({updated_count} record).")
            # Riesegui filtro per aggiornare vista se necessario (ma i valori in current_result non cambiano finché non si riesegue query)
            self._apply_res_filter()

    def _edit_res_record(self):
        if not self._result_supports_direct_update():
            return messagebox.showwarning(
                "Operazione non disponibile",
                "La modifica diretta e disponibile solo per risultati che mappano in modo univoco a una singola tabella."
            )
        sel = self._get_res_tree().selection()
        if not sel or not self.current_result: return
        
        idx_str = sel[0]
        try:
            idx = int(idx_str)
            row_typed = self.current_result["rows"][idx]
            cols = self.current_result["columns"]
            data = dict(zip(cols, row_typed))
        except (ValueError, IndexError):
            # Fallback se l'iid non è numerico o fuori range (anche se improbabile qui)
            vals = self._get_res_tree().item(sel[0], "values")
            cols = self.current_result["columns"]
            data = dict(zip(cols, vals))
        
        table = self.current_result.get("source_table")
        if not table:
            # Se è una cross-tabella, cerca di capire quale
            table = simpledialog.askstring("Tabella Sorgente", "In quale tabella vuoi modificare il record?")
        
        if table:
            dlg = RecordEditorDialog(self, self.db, table, data)
            self.wait_window(dlg)
            if dlg.result:
                # Se possibile, rinfresca la riga (semplificato: riesegui)
                self.status.set("Record modificato. Riesegui il controllo per aggiornare la vista.")

    def _load_group_conditions(self, group_payload):
        if isinstance(group_payload, dict):
            conditions = group_payload.get("conditions", [])
            group_name = group_payload.get("name", "")
            group_db_label = str(group_payload.get("database_label", "") or "").strip()
        else:
            conditions = group_payload
            group_name = ""
            group_db_label = ""

        prepared = []
        for cond in conditions:
            if not isinstance(cond, dict):
                continue
            item = dict(cond)
            if group_db_label and not str(item.get("database_label", "") or "").strip():
                item["database_label"] = group_db_label
            prepared.append(item)

        self.store.items = prepared
        self._loaded_condition_idx = None
        self._refresh_lib()
        self._refresh_dash()
        if group_db_label:
            self._ensure_active_database_for_label(group_db_label, interactive=False)
        if group_name:
            self.status.set(f"Caricate {len(prepared)} condizioni dal gruppo '{group_name}' ({group_db_label or 'DB non associato'}).")
        else:
            self.status.set(f"Caricate {len(prepared)} condizioni dal gruppo.")

    def _on_save_group_request(self, _evt):
        database_label = self._group_database_label(self.store.items)
        if not database_label:
            database_label = simpledialog.askstring(
                "Database del gruppo",
                "Nome logico del database associato al gruppo (es. Datico.mdb):",
            )
            if not database_label:
                self.status.set("Salvataggio gruppo annullato: database non specificato.")
                return
            self._register_database_reference(database_label)

        prepared_items = []
        for cond in self.store.items:
            if not isinstance(cond, dict):
                continue
            item = dict(cond)
            item["database_label"] = str(item.get("database_label", "") or "").strip() or database_label
            prepared_items.append(item)

        self.group_sel.finalize_save(prepared_items, database_label=database_label)
        self._refresh_dash()

    def _quit(self):
        self._stop_monitor()
        self.db.disconnect()
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
