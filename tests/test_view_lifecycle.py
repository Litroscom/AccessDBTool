"""Test del ciclo di vita delle view: cambio tab senza ricostruzione."""
import os
import sys
import types
import unittest

sys.modules.setdefault("pyodbc", types.SimpleNamespace(drivers=lambda: []))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Nessuna root e nessuna Style create a livello di modulo: la root è l'App.
# ttkbootstrap tollera una sola Style per processo e `tests/smoke_qa.py` la
# crea già quando la suite gira insieme; una seconda la resetterebbe.


class ViewLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import access_db_tool
        cls.app = access_db_tool.App()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.app.app_ctrl.stop_monitor()
        cls.app.db_ctrl.close_db()

    def test_switch_tab_reuses_same_view_instance(self):
        app = self.app
        app._switch_tab("controls")
        first = app.views["controls"]
        app._switch_tab("dashboard")
        app._switch_tab("controls")
        self.assertIs(app.views["controls"], first)
        self.assertIs(app.current_view, first)

    def test_all_four_views_alive_after_full_cycle(self):
        app = self.app
        for tab in ("db", "controls", "dashboard", "monitor"):
            app._switch_tab(tab)
        self.assertEqual(set(app.views), {"db", "controls", "dashboard", "monitor"})

    def test_only_one_view_packed(self):
        app = self.app
        for tab in ("controls", "dashboard", "monitor", "db", "controls"):
            app._switch_tab(tab)
            packed = app.main_panel.pack_slaves()
            self.assertEqual(len(packed), 1)
            self.assertIs(packed[0], app.views[tab])

    def test_results_callbacks_do_not_grow_on_tab_switch(self):
        app = self.app
        app._switch_tab("controls")
        app._switch_tab("dashboard")
        before = len(app.result_ctrl._on_results_callbacks)
        self.assertGreaterEqual(before, 1)
        for i in range(10):
            app._switch_tab("controls" if i % 2 else "dashboard")
        self.assertEqual(len(app.result_ctrl._on_results_callbacks), before)

    def test_refresh_hook_runs_once_per_show(self):
        app = self.app
        app._switch_tab("dashboard")
        view = app.views["dashboard"]
        calls = []
        original = view.refresh
        view.refresh = lambda: (calls.append(1), original())
        try:
            app._switch_tab("controls")
            app._switch_tab("dashboard")
        finally:
            view.refresh = original
        self.assertEqual(len(calls), 1)

    def test_batch_log_during_tab_switch_lands_on_live_dashboard(self):
        app = self.app
        app._switch_tab("dashboard")
        app._switch_tab("controls")
        app.batch_ctrl._on_log("messaggio di prova")
        app.update()
        dash = app.views["dashboard"]
        self.assertIn("messaggio di prova", dash.log_text.get("1.0", "end"))
        self.assertEqual(len(app.main_panel.pack_slaves()), 1)

    def test_active_builder_survives_tab_switch(self):
        app = self.app
        app._switch_tab("controls")
        view = app.views["controls"]
        view.load_condition({
            "type": "similarity_check", "name": "QA Sim", "table": "Clienti",
            "column": "Nome", "key_column": "ID", "threshold": 80,
        })
        builder = app.state.active_builder
        self.assertIsNotNone(builder)
        app._switch_tab("dashboard")
        app._switch_tab("controls")
        self.assertIs(app.state.active_builder, builder)

    def test_open_in_builder_twice_keeps_single_packed_view(self):
        app = self.app
        cond = {"type": "value_comparison", "name": "QA Val", "table": "Clienti"}
        app._switch_tab("controls")
        app._open_cond_in_builder(cond)
        app._open_cond_in_builder(cond)
        self.assertEqual(len(app.main_panel.pack_slaves()), 1)
        self.assertIs(app.current_view, app.views["controls"])

    def test_manager_load_reaches_live_view(self):
        app = self.app
        app._switch_tab("controls")  # assicura la view viva (indipendente dall'ordine dei test)
        app._switch_tab("dashboard")
        view = app.views["controls"]
        received = []
        original = view.load_condition
        view.load_condition = lambda cond: received.append(cond)
        cond = {"type": "value_comparison", "name": "QA Gestore", "table": "Clienti"}
        try:
            app.library_ctrl.load_condition_in_view(cond)
        finally:
            view.load_condition = original
        self.assertEqual(len(received), 1)
        self.assertEqual(app.state.var_saved.get(), "QA Gestore")
        self.assertIs(app.current_view, app.views["controls"])

    def test_active_db_switch_refreshes_every_live_view(self):
        app = self.app
        for tab in ("db", "controls", "dashboard", "monitor"):
            app._switch_tab(tab)
        called, originals = [], {}
        for name, view in app.views.items():
            originals[name] = view.refresh
            view.refresh = (lambda n=name: called.append(n))
        try:
            app._on_active_db_switched()
        finally:
            for name, fn in originals.items():
                app.views[name].refresh = fn
        self.assertEqual(set(called), {"db", "controls", "dashboard", "monitor"})

    def test_close_db_with_live_views_does_not_raise(self):
        app = self.app
        app._switch_tab("controls")
        called, originals = [], {}
        for name, view in app.views.items():
            originals[name] = view.refresh
            view.refresh = (lambda n=name: called.append(n))
        try:
            app._close_db()
        finally:
            for name, fn in originals.items():
                app.views[name].refresh = fn
        self.assertEqual(len(app.main_panel.pack_slaves()), 1)
        self.assertIn("controls", called)

    def test_database_controller_notifies_after_connection_is_established(self):
        app = self.app
        state = app.state
        original_db = state.db
        original_label = state.current_db_label
        original_registry = state.db_registry
        original_status = state.status.get()
        notifications = []

        class FakeDatabase:
            connected = False
            db_path = ""
            tables = []

            def connect(self, path):
                self.db_path = path
                self.connected = True
                self.tables = ["Nuova"]

            def disconnect(self):
                self.connected = False
                self.db_path = ""
                self.tables = []

        class FakeRegistry:
            def set_path(self, label, path):
                return label

            def remember(self, label):
                return label

        state.db = FakeDatabase()
        state.db_registry = FakeRegistry()
        app.db_ctrl.set_active_db_switched_callback(
            lambda: notifications.append(state.db.connected)
        )
        try:
            app.db_ctrl.connect_active_database("fake.accdb", "Finto")
            self.assertEqual(notifications, [True])
        finally:
            state.db = original_db
            state.current_db_label = original_label
            state.db_registry = original_registry
            state.status.set(original_status)
            app.db_ctrl.set_active_db_switched_callback(app._on_active_db_switched)

    def test_database_switch_from_worker_marshals_all_ui_work_to_main_thread(self):
        import threading

        app = self.app
        main_thread_id = threading.get_ident()
        scheduled = []
        operations = []
        originals = {
            "after": app.after,
            "stop_monitor": app.app_ctrl.stop_monitor,
            "indicator": app._set_mon_indicator,
            "status_set": app.state.status.set,
            "refresh": app._refresh_live_views,
        }
        app.after = lambda delay, callback, *args: scheduled.append((callback, args))
        app.app_ctrl.stop_monitor = lambda: operations.append(("stop", threading.get_ident()))
        app._set_mon_indicator = lambda state: operations.append(("indicator", threading.get_ident()))
        app.state.status.set = lambda value: operations.append(("status", threading.get_ident()))
        app._refresh_live_views = lambda: operations.append(("refresh", threading.get_ident()))
        try:
            worker = threading.Thread(target=app._on_active_db_switched)
            worker.start()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(scheduled), 1)
            self.assertEqual(operations, [])

            callback, args = scheduled[0]
            callback(*args)
            self.assertEqual(
                {thread_id for _name, thread_id in operations},
                {main_thread_id},
            )
        finally:
            app.after = originals["after"]
            app.app_ctrl.stop_monitor = originals["stop_monitor"]
            app._set_mon_indicator = originals["indicator"]
            app.state.status.set = originals["status_set"]
            app._refresh_live_views = originals["refresh"]

    def test_database_tab_close_button_uses_app_close_action(self):
        app = self.app
        was_wired = "db" in app._wired
        original_close = app._close_db
        original_db_close = app.db_ctrl.close_db
        close_calls = []
        view = app._create_view("db")

        def find_close_button(widget):
            for child in widget.winfo_children():
                if child.winfo_class() == "TButton" and child.cget("text") == "Chiudi":
                    return child
                found = find_close_button(child)
                if found is not None:
                    return found
            return None

        try:
            app._close_db = lambda: close_calls.append("app")
            app.db_ctrl.close_db = lambda: close_calls.append("controller")
            app._wired.discard("db")
            app._wire_view_once("db", view)
            button = find_close_button(view)
            self.assertIsNotNone(button)
            button.invoke()
            self.assertEqual(close_calls, ["app"])
        finally:
            view.destroy()
            app._close_db = original_close
            app.db_ctrl.close_db = original_db_close
            if was_wired:
                app._wired.add("db")
            else:
                app._wired.discard("db")

    def test_builder_refresh_rebuilds_db_bound_choices_and_clears_selection(self):
        from views.builder_view import BuilderView

        app = self.app
        state = app.state
        original = {
            "db": state.db,
            "active_builder": state.active_builder,
            "active_ctype": state.active_ctype,
            "sel_tables": state.sel_tables,
            "current_db_label": state.current_db_label,
            "var_saved": state.var_saved.get(),
            "var_ctype": state.var_ctype.get(),
            "loaded_condition_idx": state.loaded_condition_idx,
        }

        class FakeDatabase:
            connected = True
            db_path = "fake.accdb"

            def __init__(self, tables, columns):
                self.tables = tables
                self._columns = columns

            def columns(self, table):
                return self._columns.get(table, [])

        view = None
        try:
            state.db = FakeDatabase(["Prima"], {"Prima": ["VecchiaColonna"]})
            state.active_builder = None
            state.active_ctype = "similarity_check"
            state.sel_tables = []
            state.current_db_label = "Primo DB"
            view = BuilderView(app.main_panel, state, app.db_ctrl)
            view.load_condition({
                "type": "similarity_check", "name": "QA DB", "table": "Prima",
                "column": "VecchiaColonna", "key_column": "ID",
            })
            self.assertEqual(tuple(state.active_builder.cmb_table["values"]), ("Prima",))
            self.assertEqual(view.col_selector.get_selected(), [])

            state.db = FakeDatabase(["Seconda"], {"Seconda": ["NuovaColonna"]})
            state.current_db_label = "Secondo DB"
            view.refresh()

            self.assertEqual(tuple(state.active_builder.cmb_table["values"]), ("Seconda",))
            self.assertEqual(state.active_builder.var_table.get(), "")
            self.assertEqual(state.sel_tables, [])
            self.assertEqual(view.col_selector.col_vars, {})
        finally:
            if view is not None:
                view.destroy()
            state.db = original["db"]
            state.active_builder = original["active_builder"]
            state.active_ctype = original["active_ctype"]
            state.sel_tables = original["sel_tables"]
            state.current_db_label = original["current_db_label"]
            state.var_saved.set(original["var_saved"])
            state.var_ctype.set(original["var_ctype"])
            state.loaded_condition_idx = original["loaded_condition_idx"]
