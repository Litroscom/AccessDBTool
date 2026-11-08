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
            self.assertEqual(len(app.main_panel.pack_slaves()), 1)
