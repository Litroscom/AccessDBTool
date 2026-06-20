"""Smoke test QA: istanzia ogni builder, round-trip get_config/set_config
(incluse esclusioni) ed esercita i flussi save/load/update della libreria.
Headless: crea un root tkinter nascosto, senza mainloop."""
import os
import sys
import types
import tempfile
import unittest

sys.modules.setdefault("pyodbc", types.SimpleNamespace(drivers=lambda: []))

import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import ui_components
from ui_components import (
    ValueComparisonBuilder, DuplicateBuilder, SimilarityBuilder,
    CrossTableBuilder, FormulaBuilder, ConcatSimilarityBuilder,
    LinkedTableBuilder, FormatValidationBuilder, DailyCoverageBuilder,
    MandatoryRecordBuilder, DependentConditionBuilder, RowCrossColumnBuilder,
    LookupValidationBuilder, AggregateThresholdBuilder,
)
import constants
from storage import ConditionStore
from app.controllers.db_controller import DBController
from app.controllers.library_controller import LibraryController


class FakeDB:
    def __init__(self):
        self.connected = True
        self.tables = ["Clienti", "Ordini"]
        self.table_columns = {
            "Clienti": ["ID", "Nome", "Citta", "Stato"],
            "Ordini": ["ID", "ClienteID", "Data", "Importo"],
        }

    def columns(self, table):
        return self.table_columns.get(table, [])

    def fetch(self, sql, params=None):
        return [], []


def _run_headless(test_func):
    root = tk.Tk()
    root.withdraw()
    try:
        test_func(root)
    finally:
        root.destroy()


class BuilderRoundTripTests(unittest.TestCase):
    """Verifica che ogni builder faccia round-trip di get_config/set_config
    senza perdere campi chiave (tabella, conditions, exclude_conditions)."""

    BUILDERS = [
        ("value_comparison", ValueComparisonBuilder),
        ("duplicate_check", DuplicateBuilder),
        ("similarity_check", SimilarityBuilder),
        ("cross_table_existence", CrossTableBuilder),
        ("formula_condition", FormulaBuilder),
        ("concat_similarity", ConcatSimilarityBuilder),
        ("linked_table_intersection", LinkedTableBuilder),
        ("format_validation", FormatValidationBuilder),
        ("daily_coverage_check", DailyCoverageBuilder),
        ("mandatory_record_check", MandatoryRecordBuilder),
        ("dependent_condition_check", DependentConditionBuilder),
        ("row_cross_column_check", RowCrossColumnBuilder),
        ("lookup_validation", LookupValidationBuilder),
        ("aggregate_threshold_check", AggregateThresholdBuilder),
    ]

    def _config_seed(self, ctype):
        base = {
            "value_comparison": {"table": "Clienti", "column": "Nome", "operator": "=", "value": "x",
                                 "conditions": [{"column": "Citta", "operator": "=", "value": "Roma", "logic": "AND"}],
                                 "exclude_conditions": [{"column": "Stato", "operator": "=", "value": "CHIUSO", "logic": "OR"}]},
            "duplicate_check": {"table": "Clienti", "column": "Nome", "exceptions": ["SPA"],
                                "exclude_conditions": [{"column": "Stato", "operator": "=", "value": "OLD", "logic": "OR"}]},
            "similarity_check": {"table": "Clienti", "column": "Nome", "key_column": "ID", "threshold": 80,
                                 "exceptions": ["Casa | Quartiere"],
                                 "exclude_conditions": [{"column": "Citta", "operator": "=", "value": "MI", "logic": "OR"}]},
            "cross_table_existence": {"source_table": "Clienti", "key_source": "ID",
                                      "destinations": [{"table": "Ordini", "key": "ClienteID"}],
                                      "exclude_conditions": [{"column": "Stato", "operator": "=", "value": "OLD", "logic": "OR"}]},
            "formula_condition": {"table": "Clienti", "formula": "Stato = 'OK'"},
            "concat_similarity": {"table": "Clienti", "columns": ["Nome", "Citta"], "key_column": "ID", "threshold": 85,
                                  "exceptions": ["A | B"]},
            "linked_table_intersection": {"table": "Clienti", "dest_table": "Ordini",
                                          "link_key_src": "ID", "link_key_dest": "ClienteID"},
            "format_validation": {"table": "Clienti", "column": "Nome", "pattern": "^[A-Z]+"},
            "daily_coverage_check": {"table": "Ordini", "date_column": "Data"},
            "mandatory_record_check": {"table": "Clienti", "dest_table": "Ordini",
                                       "link_key_src": "ID", "link_key_dest": "ClienteID",
                                       "exclude_conditions": [{"column": "Citta", "operator": "=", "value": "X", "logic": "OR"}],
                                       "exclude_dest_conditions": [{"column": "Importo", "operator": ">", "value": "0", "logic": "OR"}]},
            "dependent_condition_check": {"table": "Clienti", "antecedent": [{"column": "Stato", "operator": "=", "value": "A", "logic": "AND"}],
                                          "consequent": [{"column": "Citta", "operator": "=", "value": "Roma", "logic": "AND"}]},
            "row_cross_column_check": {"table": "Clienti"},
            "lookup_validation": {"table": "Clienti"},
            "aggregate_threshold_check": {"table": "Ordini"},
        }
        return dict(base.get(ctype, {"table": "Clienti"}))

    def test_round_trip_all_builders(self):
        root = tk.Tk()
        root.withdraw()
        try:
            db = FakeDB()
            for ctype, cls in self.BUILDERS:
                with self.subTest(builder=ctype):
                    parent = ttk.Frame(root)
                    b = cls(parent, db, on_table_change=None)
                    b.pack()
                    seed = self._config_seed(ctype)
                    try:
                        b.set_config(seed)
                    except Exception as e:
                        self.fail(f"{ctype}: set_config fallito: {e}")
                    cfg = b.get_config()
                    got_table = cfg.get("table") or cfg.get("source_table")
                    self.assertEqual(got_table, seed.get("table") or seed.get("source_table"),
                                     f"{ctype}: tabella non preservata")
                    # Se il seed aveva exclude_conditions, il builder deve
                    # preservarle (inline) dopo il round-trip.
                    if seed.get("exclude_conditions"):
                        self.assertIn("exclude_conditions", cfg,
                                      f"{ctype}: exclude_conditions perse dopo round-trip")
                        self.assertGreaterEqual(
                            len(cfg["exclude_conditions"]),
                            len(seed["exclude_conditions"]),
                            f"{ctype}: exclude_conditions ridotte dopo round-trip",
                        )
        finally:
            root.destroy()


class LibraryFlowTests(unittest.TestCase):
    """Verifica save_to_lib / load_cond_into_builder / update_to_lib."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def _make_state(self, tmp):
        store = ConditionStore(os.path.join(tmp, "conditions.json"))
        state = SimpleNamespace(
            store=store,
            current_db_label="Datico.mdb",
            db=SimpleNamespace(connected=False, db_path=""),
            db_registry=SimpleNamespace(names=lambda: []),
            sel_tables=["Clienti"],
            active_ctype=None,
            active_builder=None,
            var_saved=tk.StringVar(),
            var_ctype=tk.StringVar(),
            var_lib_tag=tk.StringVar(value="Tutti"),
            loaded_condition_idx=None,
            status=SimpleNamespace(set=lambda v: None),
            group_store=SimpleNamespace(all_groups=lambda: [], names=lambda: []),
        )
        return state

    def test_save_and_update_preserves_exclude_and_periodic(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = self._make_state(tmp)
            db_ctrl = DBController(state)
            lib = LibraryController(state, db_ctrl)

            config = {
                "table": "Clienti", "column": "Nome", "operator": "=", "value": "x",
                "exclude_conditions": [{"column": "Stato", "operator": "=", "value": "CHIUSO", "logic": "OR"}],
            }
            cond = lib.save_to_lib(
                "Check Nome", "desc", "tag1", "value_comparison", config,
                ["ID", "Nome"],
                {"periodic_review_enabled": True, "periodic_review_cycle": "MONTHLY",
                 "periodic_review_note": "Aggiorna mese "},
            )
            self.assertEqual(cond["periodic_review_cycle"], "monthly")
            self.assertEqual(cond["periodic_review_note"], "Aggiorna mese")
            self.assertEqual(len(state.store.items), 1)
            self.assertEqual(state.store.items[0]["exclude_conditions"][0]["value"], "CHIUSO")

            # update_to_lib sovrascrive config mantenendo periodic + display_columns
            state.active_ctype = "value_comparison"
            state.active_builder = SimpleNamespace(
                get_config=lambda: {
                    "table": "Clienti", "column": "Nome", "operator": "=", "value": "y",
                    "exclude_conditions": [{"column": "Citta", "operator": "=", "value": "MI", "logic": "OR"}],
                },
            )
            updated = lib.update_to_lib("value_comparison",
                                        state.active_builder.get_config(),
                                        ["ID", "Nome", "Citta"])
            self.assertEqual(updated["value"], "y")
            self.assertEqual(updated["exclude_conditions"][0]["value"], "MI")
            self.assertEqual(updated["display_columns"], ["ID", "Nome", "Citta"])
            self.assertEqual(updated["periodic_review_cycle"], "monthly")

    def test_import_overwrites_duplicate_and_keeps_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = self._make_state(tmp)
            db_ctrl = DBController(state)
            lib = LibraryController(state, db_ctrl)
            lib.save_to_lib("Dup", "d", "t", "value_comparison",
                            {"table": "Clienti"}, [], {})
            import json
            import_file = os.path.join(tmp, "import.json")
            with open(import_file, "w", encoding="utf-8") as fh:
                json.dump([{"name": "Dup", "type": "value_comparison", "table": "Clienti",
                            "exclude_conditions": [{"column": "Stato", "operator": "=", "value": "X", "logic": "OR"}]}], fh)
            # monkeypatch filedialog
            from tkinter import filedialog
            orig = filedialog.askopenfilename
            filedialog.askopenfilename = lambda **k: import_file
            try:
                lib.import_conditions()
            finally:
                filedialog.askopenfilename = orig
            self.assertEqual(len(state.store.items), 1)
            self.assertEqual(state.store.items[0]["exclude_conditions"][0]["value"], "X")


class AppBuilderIntegrationTests(unittest.TestCase):
    """Test end-to-end: App reale, caricamento condizione nel builder e
    round-trip salvataggio con esclusioni gestite inline (no accordion).
    Usa una singola App per tutta la classe (ttkbootstrap non supporta bene
    istanze multiple di tk.Tk nello stesso processo)."""

    @classmethod
    def setUpClass(cls):
        import access_db_tool
        cls.app = access_db_tool.App()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()

    def _load_and_sync(self, cond):
        app = self.app
        app._switch_tab("controls")
        view = app.current_view
        view.load_condition(cond)
        view._sync_builder_from_sections()
        return app.state.active_builder.get_config()

    def test_load_condition_and_sync_preserves_exclude_conditions(self):
        app = self.app
        app._switch_tab("controls")
        view = app.current_view
        self.assertIsNotNone(view)
        # Condizione sintetica similarity con filtri, eccezioni (pairwise) e
        # exclude_conditions (record). Tabella fittizia: il builder non
        # interroga il DB al load, quindi va bene anche senza connessione.
        cond = {
            "type": "similarity_check",
            "name": "QA Sim",
            "table": "Clienti",
            "column": "Nome",
            "key_column": "ID",
            "threshold": 80,
            "exceptions": ["Casa | Quartiere"],
            "conditions": [{"column": "Citta", "operator": "=", "value": "Roma", "logic": "AND"}],
            "exclude_conditions": [{"column": "Stato", "operator": "=", "value": "CHIUSO", "logic": "OR"}],
            "display_columns": ["ID", "Nome"],
        }
        cfg = self._load_and_sync(cond)
        self.assertEqual(self.app.state.active_ctype, "similarity_check")
        self.assertEqual(cfg.get("table"), "Clienti")
        self.assertEqual(cfg.get("column"), "Nome")
        self.assertIn("Casa | Quartiere", cfg.get("exceptions", []))
        # Le exclude_conditions devono restare gestite inline dal builder
        self.assertIn("exclude_conditions", cfg)
        self.assertGreaterEqual(len(cfg["exclude_conditions"]), 1)
        self.assertEqual(cfg["exclude_conditions"][0]["value"], "CHIUSO")
        # I filtri della sezione accordion devono essere sincronizzati
        self.assertTrue(any(c["column"] == "Citta" for c in cfg.get("conditions", [])))

    def test_mandatory_builder_inline_exclusions_round_trip(self):
        cond = {
            "type": "mandatory_record_check",
            "name": "QA Mandatory",
            "table": "Agenda",
            "dest_table": "Volontari",
            "link_key_src": "ID",
            "link_key_dest": "AgendaID",
            "conditions": [{"column": "Week", "operator": "=", "value": "15", "logic": "AND"}],
            "exclude_conditions": [{"column": "Area", "operator": "=", "value": "TEST", "logic": "OR"}],
            "exclude_dest_conditions": [{"column": "Stato", "operator": "=", "value": "ANN", "logic": "OR"}],
        }
        cfg = self._load_and_sync(cond)
        self.assertEqual(self.app.state.active_ctype, "mandatory_record_check")
        self.assertEqual(cfg.get("exclude_conditions")[0]["value"], "TEST")
        self.assertEqual(cfg.get("exclude_dest_conditions")[0]["value"], "ANN")


if __name__ == "__main__":
    unittest.main()
