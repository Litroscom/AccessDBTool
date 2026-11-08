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
