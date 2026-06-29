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
    LookupValidationBuilder, AggregateThresholdBuilder, AggregateMultiTableBuilder,
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
            "formula_condition": {"table": "Clienti", "formula": "Stato = 'OK'",
                                  "exclude_conditions": [{"column": "ID", "operator": "=", "value": "5", "logic": "OR"}]},
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

    def test_dashboard_double_click_opens_builder_not_rerun(self):
        """Doppio click su riga dashboard deve aprire la condizione nel
        tab Controlli (builder), NON rieseguire il controllo."""
        app = self.app
        app._switch_tab("dashboard")
        dash = app.current_view
        self.assertIsNotNone(dash)
        # La callback open_in_builder deve essere cablata da _wire_view_callbacks
        self.assertIsNotNone(dash._on_open_in_builder)

        cond = {
            "type": "similarity_check", "name": "QA DblClick", "table": "Clienti",
            "column": "Nome", "key_column": "ID", "threshold": 80,
        }
        # Popola la tree via mock library_ctrl (evita di toccare lo store reale)
        dash.library_ctrl = SimpleNamespace(
            get_dashboard_items=lambda tag: [cond],
            all_condition_tags=lambda: [],
        )
        dash._refresh()
        dash.dash_tree.selection_set("0")
        dash.dash_tree.focus("0")

        called = {"open": False, "run": False}
        original_open = dash._on_open_in_builder
        def fake_open(c, pending=None):
            called["open"] = True
            original_open(c)
        dash._on_open_in_builder = fake_open
        if dash.batch_ctrl is not None:
            dash.batch_ctrl.run_selected_dashboard_check = lambda c: called.__setitem__("run", True)
        try:
            dash._on_double_click(None)
        finally:
            dash._on_open_in_builder = original_open

        self.assertTrue(called["open"], "double click non ha invocato open_in_builder")
        self.assertFalse(called["run"], "double click ha rieseguito il controllo (comportamento legacy)")
        # Dopo l'apertura: tab Controlli attivo e condizione caricata nel builder
        self.assertEqual(app.state.active_ctype, "similarity_check")
        self.assertIsNotNone(app.state.active_builder)

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


class RecordEditorDialogTests(unittest.TestCase):
    """Modifica diretta di un record dal risultato: il dialog deve usare la
    chiave primaria reale, castare i valori al tipo originale e scrivere via
    db.update_record_safe (rifiuta se non identifica esattamente 1 record)."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    class _FakeEditDB:
        def __init__(self, pks=("ID",)):
            self.calls = []
            self._pks = list(pks)
        def primary_keys(self, table):
            return list(self._pks)
        def update_record_safe(self, table, key_dict, data):
            self.calls.append((table, dict(key_dict), dict(data)))
            return 1

    def test_save_uses_real_pk_and_safe_update(self):
        from unittest.mock import patch
        from ui_components import RecordEditorDialog

        db = self._FakeEditDB(pks=["ID"])
        data = {"ID": 5, "Amount": 3.0, "Nome": "Mario"}  # valori tipizzati come da fetch
        with patch("ui_components.messagebox"):
            dlg = RecordEditorDialog(self.root, db, "Invoices", data)
            self.assertEqual(dlg.key_cols, ["ID"])  # PK reale, bloccata
            dlg.entries["Amount"].delete(0, tk.END)
            dlg.entries["Amount"].insert(0, "12,5")
            dlg.entries["Nome"].delete(0, tk.END)
            dlg.entries["Nome"].insert(0, "Luigi")
            dlg._save()

        self.assertEqual(len(db.calls), 1)
        table, key_dict, new = db.calls[0]
        self.assertEqual(table, "Invoices")
        self.assertEqual(key_dict, {"ID": 5})       # WHERE sulla PK reale
        self.assertEqual(new["Amount"], 12.5)       # "12,5" -> float 12.5
        self.assertEqual(new["Nome"], "Luigi")
        self.assertNotIn("ID", new)                 # PK esclusa dal SET
        self.assertTrue(dlg.result)

    def test_refuses_when_primary_key_not_in_result(self):
        from unittest.mock import patch
        from ui_components import RecordEditorDialog

        db = self._FakeEditDB(pks=["ID"])
        data = {"Nome": "Mario", "Citta": "Roma"}  # niente ID tra le colonne
        with patch("ui_components.messagebox") as mb:
            dlg = RecordEditorDialog(self.root, db, "Clienti", data)
            self.assertEqual(dlg.key_cols, [])      # nessuna chiave sicura
            dlg._save()
            self.assertTrue(mb.showwarning.called)   # avvisa l'utente
        self.assertEqual(db.calls, [])               # NESSUNA scrittura tentata
        self.assertIsNone(dlg.result)

    def test_fallback_key_when_driver_exposes_no_pk(self):
        from unittest.mock import patch
        from ui_components import RecordEditorDialog

        db = self._FakeEditDB(pks=[])  # driver non espone PK
        data = {"ID": 7, "Nome": "Mario"}
        with patch("ui_components.messagebox"):
            dlg = RecordEditorDialog(self.root, db, "Clienti", data)
            self.assertEqual(dlg.key_cols, ["ID"])  # ripiega su colonna id-like
            dlg.entries["Nome"].delete(0, tk.END)
            dlg.entries["Nome"].insert(0, "Luigi")
            dlg._save()
        _t, key_dict, _new = db.calls[0]
        self.assertEqual(key_dict, {"ID": 7})

    def test_pk_resolved_case_insensitively(self):
        from unittest.mock import patch
        from ui_components import RecordEditorDialog

        db = self._FakeEditDB(pks=["ID"])      # PK dichiarata "ID"
        data = {"Id": 5, "Nome": "Mario"}      # ma nel risultato e' "Id"
        with patch("ui_components.messagebox"):
            dlg = RecordEditorDialog(self.root, db, "Clienti", data)
            self.assertEqual(dlg.key_cols, ["Id"])   # risolta alla grafia dei dati
            dlg.entries["Nome"].delete(0, tk.END)
            dlg.entries["Nome"].insert(0, "Luigi")
            dlg._save()
        _t, key_dict, _new = db.calls[0]
        self.assertEqual(key_dict, {"Id": 5})

    def test_emptied_numeric_field_becomes_null(self):
        from unittest.mock import patch
        from ui_components import RecordEditorDialog

        db = self._FakeEditDB(pks=["ID"])
        data = {"ID": 1, "Amount": 9.0}
        with patch("ui_components.messagebox"):
            dlg = RecordEditorDialog(self.root, db, "Invoices", data)
            dlg.entries["Amount"].delete(0, tk.END)  # svuota campo numerico
            dlg._save()
        _t, _key, new = db.calls[0]
        self.assertIsNone(new["Amount"])  # numerico svuotato -> NULL, non ""


class AggregateRangeBuilderTests(unittest.TestCase):
    """Operatore 'tra' (intervallo) nel builder Soglia Aggregata."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_between_operator_round_trip(self):
        db = FakeDB()
        b = AggregateThresholdBuilder(ttk.Frame(self.root), db, on_table_change=None)
        b.set_config({
            "table": "casa-quartiere", "group_by": ["Diffusori"],
            "agg_function": "SUM", "agg_column": "mh",
            "operator": "tra", "threshold": 14, "threshold_max": 16,
        })
        cfg = b.get_config()
        self.assertEqual(cfg["operator"], "tra")
        self.assertEqual(cfg["threshold"], 14)
        self.assertEqual(cfg["threshold_max"], 16)
        self.assertEqual(cfg["group_by"], ["Diffusori"])

    def test_single_operator_has_no_threshold_max(self):
        db = FakeDB()
        b = AggregateThresholdBuilder(ttk.Frame(self.root), db, on_table_change=None)
        b.set_config({
            "table": "T", "group_by": ["G"], "agg_function": "SUM",
            "agg_column": "mh", "operator": ">=", "threshold": 14,
        })
        cfg = b.get_config()
        self.assertEqual(cfg["operator"], ">=")
        self.assertNotIn("threshold_max", cfg)

    def test_multi_table_builder_round_trip(self):
        db = FakeDB()
        b = AggregateMultiTableBuilder(ttk.Frame(self.root), db, on_table_change=None)
        seed = {
            "sources": [
                {"table": "Clienti", "group_col": "Nome", "value_col": "Citta"},
                {"table": "Ordini", "group_col": "ClienteID", "value_col": "Importo"},
            ],
            "agg_function": "SUM", "operator": "tra",
            "threshold": 14, "threshold_max": 16,
            "conditions": [{"column": "Mese", "operator": "=", "value": "giu", "logic": "AND"}],
        }
        b.set_config(seed)
        cfg = b.get_config()
        self.assertEqual(len(cfg["sources"]), 2)
        self.assertEqual(cfg["sources"][0], {"table": "Clienti", "group_col": "Nome", "value_col": "Citta"})
        self.assertEqual(cfg["sources"][1]["value_col"], "Importo")
        self.assertEqual(cfg["operator"], "tra")
        self.assertEqual(cfg["threshold_max"], 16)
        self.assertEqual(cfg["conditions"][0]["column"], "Mese")


class ConditionManagerBulkReplaceTests(unittest.TestCase):
    """Sostituzione massiva valori dal 'Gestione Condizioni' (#28), headless:
    esercita plan+apply senza i dialog interattivi."""

    def setUp(self):
        # ConditionManagerDialog usa widget con opzione 'bootstyle' (ttkbootstrap):
        # serve un root ttkbootstrap anche quando il test gira isolato.
        import ttkbootstrap as tb
        self.root = tb.Window()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_plan_and_apply_replaces_across_selected_conditions(self):
        from views.condition_manager_view import ConditionManagerDialog
        with tempfile.TemporaryDirectory() as tmp:
            store = ConditionStore(os.path.join(tmp, "conditions.json"))
            store.add({"name": "A", "type": "value_comparison", "table": "T",
                       "conditions": [{"column": "mese", "operator": "=", "value": "giu", "logic": "AND"}]})
            store.add({"name": "B", "type": "formula_condition", "table": "T",
                       "formula": "[mese] = 'giu'"})
            store.add({"name": "C", "type": "value_comparison", "table": "T",
                       "conditions": [{"column": "mese", "operator": "=", "value": "lug", "logic": "AND"}]})

            refreshed = {"n": 0}
            dlg = ConditionManagerDialog(self.root, store, lambda: refreshed.__setitem__("n", refreshed["n"] + 1), lambda c: None)
            try:
                indices = [0, 1, 2]
                plan = dlg._plan_replacement(indices, "mese", "giu", "mag")
                # solo A e B hanno 'giu' -> 2 condizioni nel piano
                self.assertEqual(len(plan), 2)
                applied = dlg._apply_replacement(plan)
                self.assertEqual(applied, 2)
                self.assertEqual(store.items[0]["conditions"][0]["value"], "mag")
                self.assertEqual(store.items[1]["formula"], "[mese] = 'mag'")
                self.assertEqual(store.items[2]["conditions"][0]["value"], "lug")  # invariato
                # persistito su disco
                reloaded = ConditionStore(os.path.join(tmp, "conditions.json"))
                self.assertEqual(reloaded.items[0]["conditions"][0]["value"], "mag")
            finally:
                dlg.destroy()


if __name__ == "__main__":
    unittest.main()
