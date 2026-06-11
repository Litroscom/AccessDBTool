#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Access DB Quality Control Tool - v7.2
Entry point principale - Architettura modulare con controller.
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

from app.state import AppState
from app.controllers.app_controller import AppController
from app.controllers.db_controller import DBController
from app.controllers.batch_controller import BatchController
from app.controllers.result_controller import ResultController
from app.controllers.library_controller import LibraryController

try:
    import winsound
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False

logger = setup_logging(constants._BASE_DIR)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        logger.info("Avvio Access DB Quality Control Tool v7.2...")

        db = DatabaseManager()
        executor = ConditionExecutor(db)
        store = ConditionStore()
        group_store = GroupStore()
        db_registry = DatabaseRegistry()
        mon_queue = queue.Queue()
        monitor = MonitorEngine(db, executor, mon_queue)

        self.state = AppState()
        self.state.db = db
        self.state.executor = executor
        self.state.store = store
        self.state.group_store = group_store
        self.state.db_registry = db_registry
        self.state.monitor_queue = mon_queue
        self.state.monitor = monitor
        self.state.mon_log = MonitorLog()
        self.state.status = tk.StringVar(value="Pronto")
        self.state.var_ctype = tk.StringVar()
        self.state.var_saved = tk.StringVar()
        self.state.var_lib_tag = tk.StringVar(value="Tutti")

        self.db_ctrl = DBController(self.state)
        self.library_ctrl = LibraryController(self.state, self.db_ctrl)
        self.result_ctrl = ResultController(self.state)
        self.batch_ctrl = BatchController(self.state, self.db_ctrl, self.result_ctrl)
        self.app_ctrl = AppController(self.state, self.db_ctrl)

        self.nav_buttons = {}
        self.main_panel = None
        self.current_view = None
        self.mon_indicator = None
        self.mon_queue = mon_queue
        self.btn_mon_start = None
        self.btn_mon_stop = None
        self.res_menu = None

        self.title(constants.APP_TITLE)
        self.geometry("1300x900")
        self.minsize(1024, 600)

        self.style = theme_config.setup_theme(self)

        self._build_menu()
        self._bind_global_shortcuts()
        self._build_layout()
        self.app_ctrl.poll_monitor(self)

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
        fm.add_command(label="Apri Database...", command=self.db_ctrl.open_db)
        fm.add_command(label="Chiudi Database", command=self._close_db)
        fm.add_separator()
        fm.add_command(label="Esporta CSV Risultati...", command=self.result_ctrl.export_csv)
        fm.add_separator()
        fm.add_command(label="Esci", command=self._quit)
        mb.add_cascade(label="File", menu=fm)

        cm = tk.Menu(mb, tearoff=0, bg=menu_bg, fg=menu_fg, activebackground=menu_active_bg,
                     activeforeground=menu_active_fg, disabledforeground=menu_disabled_fg,
                     font=("Segoe UI", 9))
        cm.add_command(label="Salva condizione corrente...", command=lambda: self.library_ctrl.save_cond(False))
        cm.add_command(label="Salva come nuova...", command=lambda: self.library_ctrl.save_cond(True))
        cm.add_command(label="Gestisci libreria...", command=self.library_ctrl.open_manager)
        cm.add_separator()
        cm.add_command(label="Esporta libreria condizioni...", command=self.library_ctrl.export_conditions)
        cm.add_command(label="Importa condizioni da file...", command=self.library_ctrl.import_conditions)
        mb.add_cascade(label="Condizioni", menu=cm)

        mm = tk.Menu(mb, tearoff=0, bg=menu_bg, fg=menu_fg, activebackground=menu_active_bg,
                     activeforeground=menu_active_fg, disabledforeground=menu_disabled_fg,
                     font=("Segoe UI", 9))
        mm.add_command(label="Avvia monitor", command=self._start_monitor)
        mm.add_command(label="Ferma monitor", command=self.app_ctrl.stop_monitor)
        mm.add_separator()
        mm.add_command(label="Annulla analisi batch", command=self.batch_ctrl.cancel_batch)
        mb.add_cascade(label="Monitor/Batch", menu=mm)

        self.config(menu=mb)

    def _bind_global_shortcuts(self):
        bindings = {
            "h": lambda: self._go_to_tab("db"),
            "a": self.db_ctrl.open_db,
            "c": self._close_db,
            "i": lambda: self._run_profiler_from_view(),
            "e": self.batch_ctrl.run_all_batch,
            "g": self.library_ctrl.open_manager,
            "r": self._run_current_from_view,
            "s": self._save_from_view,
            "u": self._update_from_view,
            "l": self._clear_from_view,
            "v": self._start_monitor,
            "f": self.app_ctrl.stop_monitor,
            "p": self.app_ctrl.clear_mon_log,
            "q": self._verify_active_formula,
            "t": lambda: self._go_to_tab("controls"),
            "d": lambda: self._go_to_tab("dashboard"),
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
            logger.exception("Errore nel determinare il toplevel per lo shortcut globale")
            return "break"
        try:
            callback()
        except Exception:
            logger.exception("Errore in shortcut globale")
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
        if self.state.active_ctype == "formula_condition" and self.state.active_builder and hasattr(self.state.active_builder, "verify_formula"):
            self.state.active_builder.verify_formula()

    def _build_layout(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.sidebar = ttk.Frame(main_frame, width=44, style="dark.TFrame")
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        content_frame = ttk.Frame(main_frame)
        content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.nav_bar = ttk.Frame(content_frame)
        self.nav_bar.pack(fill=tk.X, padx=8, pady=(8, 0))

        self.nav_buttons = {}
        for nav_id, label, icon in [
            ("db", "Database", "\U0001f5c4"),
            ("controls", "Controlli", "\u2699"),
            ("dashboard", "Dashboard", "\U0001f4ca"),
            ("monitor", "Monitor", "\U0001f514"),
        ]:
            btn = ttk.Button(
                self.nav_bar, text=f"{icon} {label}",
                command=lambda nid=nav_id: self._switch_tab(nid),
                bootstyle="secondary-outline",
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.nav_buttons[nav_id] = btn

        self.main_panel = ttk.Frame(content_frame, padding=8)
        self.main_panel.pack(fill=tk.BOTH, expand=True)

        self._build_status_bar(main_frame)
        self._switch_tab("db")

    def _build_status_bar(self, parent):
        sb = ttk.Frame(parent, bootstyle="dark")
        sb.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_label = ttk.Label(
            sb, textvariable=self.state.status,
            bootstyle="inverse-dark", padding=(8, 4)
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.mon_indicator = ttk.Label(
            sb, text=" MONITOR OFF ",
            bootstyle="inverse-danger", padding=(8, 2)
        )
        self.mon_indicator.pack(side=tk.RIGHT)

    def _switch_tab(self, tab_id):
        self.current_view = self.app_ctrl.switch_tab(
            tab_id, self.nav_buttons, self.main_panel
        )
        if self.current_view:
            self._wire_view_callbacks(tab_id)

    def _wire_view_callbacks(self, tab_id):
        view = self.current_view
        if tab_id == "controls":
            view.library_ctrl = self.library_ctrl
            view.result_ctrl = self.result_ctrl
            view.refresh_lib()
        elif tab_id == "dashboard":
            view.library_ctrl = self.library_ctrl
            view.batch_ctrl = self.batch_ctrl
            view.result_ctrl = self.result_ctrl
            if self.batch_ctrl:
                # Le callback arrivano da thread worker del batch: marshalling
                # sul main thread via after(), altrimenti Tkinter cross-thread
                # solleva eccezioni e interrompe l'aggiornamento.
                self.batch_ctrl.set_log_callback(
                    lambda line, v=view: v.after(0, v._append_log, line))
                self.batch_ctrl.set_progress_callback(
                    lambda cur, tot, v=view: v.after(0, v._update_progress, cur, tot))
                self.batch_ctrl.set_dash_update_callback(
                    lambda v=view: v.after(0, v._refresh))
            if self.result_ctrl:
                self.result_ctrl.set_results_callback(
                    lambda res, v=view: v.after(0, v.show_results, res))
            if hasattr(view, "results_view"):
                view.results_view.result_ctrl = self.result_ctrl
                view.results_view.set_open_in_builder_callback(
                    lambda cond: self.library_ctrl.load_cond_into_builder(cond)
                )
            view._refresh()
        elif tab_id == "db":
            if hasattr(view, "set_load_insight_callback"):
                view.set_load_insight_callback(self._load_insight)
            if hasattr(view, "set_profiler_done_callback"):
                view.set_profiler_done_callback(lambda: None)

    def _close_db(self):
        self.app_ctrl.stop_monitor()
        self.db_ctrl.close_db()
        if hasattr(self, "current_view") and hasattr(self.current_view, "refresh"):
            self.current_view.refresh()

    def _start_monitor(self):
        if self.app_ctrl.start_monitor():
            if self.mon_indicator:
                self.mon_indicator.config(text=" MONITOR ON ", bootstyle="inverse-success")

    def _run_profiler_from_view(self):
        self.db_ctrl.run_profiler()
        if hasattr(self, "current_view") and hasattr(self.current_view, "refresh"):
            self.current_view.refresh()

    def _run_current_from_view(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "_run_current"):
            self.current_view._run_current()

    def _save_from_view(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "_save_to_lib"):
            self.current_view._save_to_lib()

    def _update_from_view(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "_update_to_lib"):
            self.current_view._update_to_lib()

    def _clear_from_view(self):
        if hasattr(self, "current_view") and hasattr(self.current_view, "_clear_builder"):
            self.current_view._clear_builder()

    def _load_insight(self, event=None):
        view = self.current_view
        if not view or not hasattr(view, "ins_tree"):
            return
        sel = view.ins_tree.selection()
        if not sel:
            return
        item = view.ins_tree.item(sel[0])
        values = item.get("values", [])
        if not values:
            return
        action = values[2] if len(values) > 2 else ""
        ins = self.state.current_insights
        if not ins:
            return
        for insight in ins:
            if insight.get("action") == action:
                cond = insight.get("condition")
                if cond:
                    self._switch_tab("controls")
                    self.library_ctrl.load_cond_into_builder(cond)
                    if hasattr(self.current_view, "_on_ctype_change"):
                        self.current_view._on_ctype_change()
                break

    def _quit(self):
        self.app_ctrl.stop_monitor()
        self.db_ctrl.close_db()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
