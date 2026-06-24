import json
import os
import queue
import sys
import tempfile
import types
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

sys.modules.setdefault("pyodbc", types.SimpleNamespace(drivers=lambda: []))

import ui_components
from engines import ConditionExecutor
from monitor_engine import MonitorEngine
from storage import ConditionStore, DatabaseRegistry, GroupStore
from app.controllers.app_controller import AppController
from app.controllers.db_controller import DBController
from app.controllers.library_controller import LibraryController
from app.controllers.result_controller import ResultController


class FakeDB:
    def __init__(self):
        self.fetch_responses = []
        self.fetch_calls = []
        self.execute_calls = []
        self.bulk_update_calls = []
        self.cast_calls = []
        self.connected = True
        self.table_columns = {}

    def queue_fetch(self, cols, rows):
        self.fetch_responses.append((cols, rows))

    def fetch(self, sql, params=None):
        if not self.fetch_responses:
            raise AssertionError(f"Unexpected fetch: {sql}")
        self.fetch_calls.append((sql, list(params) if isinstance(params, (list, tuple)) else params))
        return self.fetch_responses.pop(0)

    def execute(self, sql, params=None):
        self.execute_calls.append((sql, tuple(params) if params is not None else None))
        return 1

    def bulk_update(self, table, set_col, pk_col, pairs):
        pairs = list(pairs)
        self.bulk_update_calls.append((table, set_col, pk_col, pairs))
        return len(pairs)

    def columns(self, table):
        return [col["name"] for col in self.table_columns.get(table, [])]

    def cast_value(self, table, col_name, value):
        self.cast_calls.append((table, col_name, value))
        if col_name == "Amount":
            return float(str(value).replace(",", "."))
        if col_name == "ID":
            return int(str(value))
        return value


class DummyStatus:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class DummyTree:
    def __init__(self):
        self.inserted = []

    def insert(self, _parent, _index, values=()):
        self.inserted.append(values)

    def winfo_exists(self):
        return True


class DummyResultTree:
    def __init__(self, rows_by_iid):
        self._rows_by_iid = rows_by_iid
        self._selection = list(rows_by_iid.keys())
        self.focused = None

    def get_children(self):
        return list(self._rows_by_iid.keys())

    def item(self, iid, option=None):
        values = self._rows_by_iid[iid]
        if option == "values":
            return values
        return {"values": values}

    def selection(self):
        return list(self._selection)

    def selection_add(self, iid):
        if iid not in self._selection:
            self._selection.append(iid)

    def selection_set(self, iid):
        self._selection = [iid]

    def focus(self, iid):
        self.focused = iid

    def identify_row(self, _y):
        return self._selection[0] if self._selection else ""

    def identify_column(self, _x):
        return "#1"


class DummyWidget:
    def __init__(self):
        self.config_calls = []

    def config(self, **kwargs):
        self.config_calls.append(kwargs)


class DummyVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DummyText:
    def __init__(self, value=""):
        self.value = value

    def get(self, *_args):
        return self.value


class DummyMonitorLog:
    def __init__(self):
        self.entries = []
        self.flushed = False

    def add(self, entry):
        self.entries.append(entry)

    def flush(self):
        self.flushed = True

    def clear(self):
        self.entries = []


class DummyBuilder:
    def __init__(self):
        self.exception_calls = []
        self.record_calls = []

    def add_exceptions(self, values, column=None):
        self.exception_calls.append((list(values), column))
        return len(values)

    def add_record_exclusions(self, values, column=None):
        self.record_calls.append((list(values), column))
        return len(values)

    def get_exception_column(self):
        return "ID"


class DummyNotebook:
    def __init__(self):
        self.selected = None

    def select(self, tab):
        self.selected = tab


class DummyExecutor:
    def run(self, _cond):
        return {"count": 0, "title": "OK", "columns": [], "rows": []}


class ConditionExecutorSmokeTests(unittest.TestCase):
    def test_build_where_preserves_left_to_right_logic(self):
        executor = ConditionExecutor(FakeDB())
        where, params = executor._build_where([
            {"column": "A", "operator": "=", "value": "1", "logic": "AND"},
            {"column": "B", "operator": "=", "value": "1", "logic": "OR"},
            {"column": "C", "operator": "=", "value": "1", "logic": "AND"},
        ])
        self.assertEqual(where, "(([A] = ? OR [B] = ?) AND [C] = ?)")
        self.assertEqual(params, ["1", "1", "1"])

    def test_cross_table_existence_smoke(self):
        db = FakeDB()
        db.queue_fetch(["ID"], [[1]])
        result = ConditionExecutor(db).run({
            "type": "cross_table_existence",
            "source_table": "Source",
            "key_source": "ID",
            "conditions": [{"column": "Status", "operator": "=", "value": "NEW", "logic": "AND"}],
            "destinations": [{"table": "Dest", "key": "ID"}],
            "dest_logic": "ALMENO_UNA",
            "display_columns": ["ID"],
        })
        self.assertEqual(result["count"], 1)
        self.assertIn("EXISTS", db.fetch_calls[0][0])

    def test_duplicate_check_smoke(self):
        db = FakeDB()
        db.queue_fetch(["ID", "Name"], [[1, "Mario"], [2, "Mario"], [3, "Luca"]])
        result = ConditionExecutor(db).run({
            "type": "duplicate_check",
            "table": "People",
            "column": "Name",
            "key_column": "ID",
        })
        self.assertEqual(result["count"], 2)

    def test_similarity_check_smoke(self):
        db = FakeDB()
        db.queue_fetch(["ID", "Name"], [[1, "Mario"], [2, "Marioo"], [3, "Luca"]])
        result = ConditionExecutor(db).run({
            "type": "similarity_check",
            "table": "People",
            "column": "Name",
            "key_column": "ID",
            "threshold": 80,
        })
        self.assertEqual(result["count"], 1)

    def test_similarity_single_id_exceptions_exclude_by_key(self):
        """Eccezioni singole numeriche o 'ID:xxx' escludono il record con quell'ID."""
        db = FakeDB()
        db.queue_fetch(["ID", "Name"], [[1, "Mario"], [2, "Marioo"], [3, "Luca"]])
        result = ConditionExecutor(db).run({
            "type": "similarity_check",
            "table": "People",
            "column": "Name",
            "key_column": "ID",
            "threshold": 80,
            "exceptions": ["2"],
        })
        self.assertEqual(result["count"], 0)

    def test_similarity_single_id_exception_with_prefix(self):
        db = FakeDB()
        db.queue_fetch(["ID", "Name"], [[1, "Mario"], [2, "Marioo"], [3, "Luca"]])
        result = ConditionExecutor(db).run({
            "type": "similarity_check",
            "table": "People",
            "column": "Name",
            "key_column": "ID",
            "threshold": 80,
            "exceptions": ["ID:2"],
        })
        self.assertEqual(result["count"], 0)

    def test_value_comparison_regex_keeps_hidden_filter_columns(self):
        db = FakeDB()
        db.queue_fetch(["Name", "Code"], [["Alice", "A12"], ["Bob", "B12"]])
        result = ConditionExecutor(db).run({
            "type": "value_comparison",
            "table": "People",
            "display_columns": ["Name"],
            "conditions": [{"column": "Code", "operator": "REGEXP", "value": r"^A\d+$", "logic": "AND"}],
        })
        self.assertEqual(result["columns"], ["Name"])
        self.assertEqual(result["rows"], [["Alice"]])
        self.assertIn("[Code]", db.fetch_calls[0][0])

    def test_concat_similarity_smoke(self):
        db = FakeDB()
        db.queue_fetch(["ID", "Name"], [[1, "Mario"], [2, "Marioo"]])
        result = ConditionExecutor(db).run({
            "type": "concat_similarity",
            "table": "People",
            "columns": ["Name"],
            "key_column": "ID",
            "threshold": 80,
        })
        self.assertEqual(result["count"], 1)

    def test_formula_condition_smoke(self):
        db = FakeDB()
        db.queue_fetch(["ID"], [[1]])
        result = ConditionExecutor(db).run({
            "type": "formula_condition",
            "table": "People",
            "display_columns": ["ID"],
            "formula": "[Enabled] = True",
        })
        self.assertEqual(result["count"], 1)

    def test_formula_condition_applies_exclude_conditions(self):
        """Bug #27: formula_condition deve applicare exclude_conditions
        (record esclusi dal tasto destro/dashboard) come 'AND NOT (...)'."""
        db = FakeDB()
        db.queue_fetch(["ID"], [[1]])
        ConditionExecutor(db).run({
            "type": "formula_condition",
            "table": "People",
            "display_columns": ["ID"],
            "formula": "[Enabled] = True",
            "exclude_conditions": [{"column": "ID", "operator": "=", "value": "7", "logic": "AND"}],
        })
        sql, params = db.fetch_calls[0]
        self.assertIn("NOT (", sql)
        self.assertIn("[ID]", sql)
        self.assertEqual(params, ["7"])

    def test_linked_table_intersection_smoke(self):
        db = FakeDB()
        db.queue_fetch(["ID"], [[1]])
        result = ConditionExecutor(db).run({
            "type": "linked_table_intersection",
            "table": "People",
            "dest_table": "Events",
            "link_key_src": "ID",
            "link_key_dest": "PersonID",
            "display_columns": ["ID"],
            "conditions": [{"column": "Status", "operator": "=", "value": "Active", "logic": "AND"}],
            "dest_conditions": [{"column": "Kind", "operator": "=", "value": "A", "logic": "AND"}],
        })
        self.assertEqual(result["count"], 1)

    def test_daily_coverage_check_smoke(self):
        db = FakeDB()
        db.queue_fetch(["Day"], [["2026-04-01"], ["2026-04-03"]])
        result = ConditionExecutor(db).run({
            "type": "daily_coverage_check",
            "table": "Agenda",
            "day_column": "Day",
            "expected_count": 3,
            "start_date": "01/04/2026",
        })
        self.assertEqual(result["rows"], [["02/04/2026"]])

    def test_mandatory_record_check_smoke(self):
        db = FakeDB()
        db.queue_fetch(["Exists"], [])
        result = ConditionExecutor(db).run({
            "type": "mandatory_record_check",
            "table": "Agenda",
            "conditions": [{"column": "Week", "operator": "=", "value": "15", "logic": "AND"}],
        })
        self.assertEqual(result["title"], "REQUISITO MANCANTE")
        self.assertEqual(result["count"], 1)

    def test_dependent_condition_regex_keeps_hidden_columns(self):
        db = FakeDB()
        db.queue_fetch(
            ["Name", "Code", "Status"],
            [["Alice", "A1", "KO"], ["Bob", "B1", "KO"], ["Cara", "A2", "OK"]],
        )
        result = ConditionExecutor(db).run({
            "type": "dependent_condition_check",
            "table": "People",
            "display_columns": ["Name"],
            "antecedent": [{"column": "Code", "operator": "REGEXP", "value": r"^A", "logic": "AND"}],
            "consequent": [{"column": "Status", "operator": "=", "value": "OK", "logic": "AND"}],
        })
        self.assertEqual(result["columns"], ["Name"])
        self.assertEqual(result["rows"], [["Alice"]])
        self.assertIn("[Code]", db.fetch_calls[0][0])
        self.assertIn("[Status]", db.fetch_calls[0][0])

    def test_row_cross_column_check_smoke(self):
        db = FakeDB()
        db.queue_fetch(["ID"], [[1]])
        result = ConditionExecutor(db).run({
            "type": "row_cross_column_check",
            "table": "Orders",
            "left_column": "EndDate",
            "right_column": "StartDate",
            "operator": ">=",
            "display_columns": ["ID"],
        })
        self.assertEqual(result["count"], 1)

    def test_lookup_validation_ignores_empty_values(self):
        db = FakeDB()
        db.queue_fetch(["Code"], [[""], ["  "], ["X"], ["A"]])
        result = ConditionExecutor(db).run({
            "type": "lookup_validation",
            "table": "Codes",
            "column": "Code",
            "allowed_values": ["A", "B"],
            "ignore_empty": True,
            "trim": True,
        })
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["rows"][0][0], "X")

    def test_aggregate_threshold_check_smoke(self):
        db = FakeDB()
        db.queue_fetch(["Dept", "AggVal"], [["Sales", 100]])
        result = ConditionExecutor(db).run({
            "type": "aggregate_threshold_check",
            "table": "Hours",
            "group_by": ["Dept"],
            "agg_function": "SUM",
            "agg_column": "Amount",
            "operator": ">",
            "threshold": 40,
        })
        self.assertEqual(result["count"], 1)

    def test_format_validation_smoke(self):
        db = FakeDB()
        db.queue_fetch(["ID", "Name"], [[1, "Alice"], [2, "123"]])
        result = ConditionExecutor(db).run({
            "type": "format_validation",
            "table": "People",
            "conditions": [{"column": "Name", "operator": "REGEXP", "value": r"^[A-Z]+$", "logic": "AND"}],
            "display_columns": ["ID", "Name"],
        })
        # format_validation è mappato su _comparison: restituisce i record che
        # soddisfano la regex (Name REGEXP ^[A-Z]+$ -> "Alice")
        self.assertEqual(result["rows"], [[1, "Alice"]])

    def test_mandatory_record_check_with_exclude_dest_conditions(self):
        db = FakeDB()
        # Requisito soddisfatto: esiste almeno un record sorgente non escluso
        # che ha riscontro in dest (con esclusione dest applicata via WHERE).
        db.queue_fetch(["Expr1000"], [[1]])
        result = ConditionExecutor(db).run({
            "type": "mandatory_record_check",
            "table": "Agenda",
            "conditions": [{"column": "Week", "operator": "=", "value": "15", "logic": "AND"}],
            "exclude_conditions": [{"column": "Area", "operator": "=", "value": "TEST", "logic": "OR"}],
            "dest_table": "Volontari",
            "link_key_src": "ID",
            "link_key_dest": "AgendaID",
            "dest_conditions": [{"column": "Anno", "operator": "=", "value": "2026", "logic": "AND"}],
            "exclude_dest_conditions": [{"column": "Stato", "operator": "=", "value": "ANN", "logic": "OR"}],
        })
        self.assertEqual(result["title"], "Requisito OK")
        sql = db.fetch_calls[0][0]
        self.assertIn("t1", sql)
        self.assertIn("t2", sql)
        # Le esclusioni destinazione devono figurare nella subquery EXISTS
        self.assertIn("[Stato]", sql)


class AppLogicTests(unittest.TestCase):
    def test_monitor_engine_accepts_conditions_on_start(self):
        q = queue.Queue()
        engine = MonitorEngine(db=None, executor=DummyExecutor(), result_queue=q)
        try:
            self.assertTrue(engine.start([{"name": "Check A"}]))
            self.assertTrue(engine.is_running)
        finally:
            engine.stop()

    def test_handle_monitor_message_uses_name_key(self):
        state = SimpleNamespace(status=DummyStatus(), mon_log=DummyMonitorLog())
        ctrl = AppController(state, db_controller=None)
        rows = []
        ctrl.set_monitor_row_callback(rows.append)
        ctrl._handle_monitor_msg({"type": "check_result", "name": "Controllo A", "count": 2, "sound": False})
        self.assertEqual(rows[0][1], "Controllo A")
        self.assertEqual(rows[0][2], "Trovati")
        self.assertEqual(state.mon_log.entries[0]["name"], "Controllo A")

    def test_bulk_replace_casts_values_before_update(self):
        db = FakeDB()
        db.table_columns = {"Invoices": [{"name": "ID"}, {"name": "Amount"}]}
        state = SimpleNamespace(
            current_result={"rows": [[1, 3.0]], "columns": ["ID", "Amount"], "source_table": "Invoices"},
            db=db,
            active_builder=None,
        )
        ctrl = ResultController(state)
        updated = ctrl.apply_bulk_replace({"column": "Amount", "value": "12,5", "mode": "replace_all"}, [0])
        # Un solo commit transazionale via bulk_update, niente execute per-riga.
        self.assertEqual(db.bulk_update_calls[0], ("Invoices", "Amount", "ID", [(12.5, 1)]))
        self.assertEqual(updated, 1)

    def test_bulk_replace_rejects_ambiguous_pk(self):
        # Nessuna colonna riconoscibile come PK -> update RIFIUTATO (-1), zero scritture.
        db = FakeDB()
        db.table_columns = {"Invoices": [{"name": "Amount"}, {"name": "Note"}]}
        state = SimpleNamespace(
            current_result={"rows": [[3.0, "x"]], "columns": ["Amount", "Note"], "source_table": "Invoices"},
            db=db,
            active_builder=None,
        )
        ctrl = ResultController(state)
        updated = ctrl.apply_bulk_replace({"column": "Amount", "value": "12,5", "mode": "replace_all"}, [0])
        self.assertEqual(updated, -1)
        self.assertEqual(db.bulk_update_calls, [])

    def test_python_like_uses_substring_semantics(self):
        # Allineamento con il path SQL (%val%): LIKE deve essere substring, non fullmatch.
        ex = ConditionExecutor(None)
        self.assertTrue(ex._eval_condition_python("HELLO WORLD", "LIKE", "%WOR%"))
        self.assertTrue(ex._eval_condition_python("HELLO WORLD", "LIKE", "%WORLD%"))
        self.assertFalse(ex._eval_condition_python("HELLO WORLD", "LIKE", "%ZZZ%"))
        self.assertFalse(ex._eval_condition_python("HELLO WORLD", "NOT LIKE", "%WOR%"))
        self.assertTrue(ex._eval_condition_python("HELLO WORLD", "NOT LIKE", "%ZZZ%"))

    def test_identifier_quoting_escapes_bracket(self):
        from db_manager import DatabaseManager
        import engines
        self.assertEqual(DatabaseManager._qi("Name"), "[Name]")
        self.assertEqual(DatabaseManager._qi("a]b"), "[a]]b]")
        self.assertEqual(engines._qi("a]b"), "[a]]b]")

    def test_batch_runs_all_conditions_despite_failing_ui_callback(self):
        # Regressione "Esegui Tutti esegue solo alcuni": una callback UI che
        # solleva (es. Tkinter cross-thread) NON deve abortire il loop del batch.
        import threading as _threading
        import app.controllers.batch_controller as bc
        from app.state import AppState

        state = AppState()
        state.batch_running = True
        state.status = DummyStatus()
        items = [(i, {"name": f"C{i}", "type": "x", "database_label": "DB"}) for i in range(5)]

        class FakeDM:
            def connect(self, _p): pass
            def disconnect(self): pass

        class FakeExec:
            def __init__(self, _db): pass
            def run(self, _cond): return {"count": 0}

        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            raise RuntimeError("Tk cross-thread")

        ctrl = bc.BatchController(
            state, db_controller=None,
            result_controller=SimpleNamespace(_on_results_callback=None),
        )
        ctrl._batch_total = len(items)
        ctrl._batch_done = 0
        ctrl._batch_progress_lock = _threading.Lock()
        ctrl.set_dash_update_callback(boom)

        with patch.object(bc, "DatabaseManager", FakeDM), patch.object(bc, "ConditionExecutor", FakeExec):
            ctrl._run_batch_for_database("DB", "fake.mdb", items)

        # Tutte e 5 le condizioni eseguite e registrate, callback fallita ogni volta.
        self.assertEqual(len(state.dash_state_by_key), 5)
        self.assertEqual(calls["n"], 5)

    def test_apply_pending_exclusion_dispatches_by_kind(self):
        ctrl = ResultController(SimpleNamespace(current_result=None, active_ctype="duplicate_check"))
        # nonfuzzy: usa la colonna target sui valori di riga
        b1 = DummyBuilder()
        n1 = ctrl.apply_pending_exclusion(
            {"kind": "nonfuzzy", "cols": ["ID", "Name"], "rows": [["10", "Mario"]], "target": "Name"},
            b1,
        )
        self.assertEqual(n1, 1)
        self.assertEqual(b1.exception_calls[0], (["Mario"], "Name"))
        # similarity: split coppia valori
        b2 = DummyBuilder()
        n2 = ctrl.apply_pending_exclusion(
            {"kind": "similarity", "mode": "pair_values",
             "cols": ["ID_1", "Name_1", "ID_2", "Name_2", "Sim%"],
             "rows": [[10, "Mario", 20, "Marco", "88.0"]], "key_col": "ID"},
            b2,
        )
        self.assertEqual(n2, 1)
        self.assertEqual(b2.exception_calls[0][0], ["Mario | Marco"])
        # nessun builder -> 0
        self.assertEqual(ctrl.apply_pending_exclusion({"kind": "nonfuzzy"}, None), 0)

    def test_similarity_exclusion_modes_are_split_correctly(self):
        builder = DummyBuilder()
        ctrl = ResultController(SimpleNamespace(current_result=None, active_ctype="similarity_check"))
        cols = ["ID_1", "Name_1", "ID_2", "Name_2", "Sim%"]
        rows = [[10, "Mario", 20, "Marco", "88.0"]]
        key_col = builder.get_exception_column()
        ctrl.add_similarity_exceptions("pair_values", cols, rows, key_col, builder)
        ctrl.add_similarity_exceptions("pair_records", cols, rows, key_col, builder)
        ctrl.add_similarity_exceptions("left_records", cols, rows, key_col, builder)
        ctrl.add_similarity_exceptions("right_records", cols, rows, key_col, builder)

        self.assertEqual(builder.exception_calls[0][0], ["Mario | Marco"])
        self.assertEqual(builder.exception_calls[1][0], ["ID:10 | ID:20"])
        self.assertEqual(builder.record_calls[0][0], ["10"])
        self.assertEqual(builder.record_calls[1][0], ["20"])

    def test_similarity_pair_records_fallback_without_key_col(self):
        """Senza key_col esplicito (path dashboard) pair_records deve comunque
        produrre una coppia di RECORD valida: ricava il nome colonna chiave
        dall'intestazione del risultato ('ID_1' -> 'ID') e usa il prefisso
        'ID:' cosi' la coppia e' riconosciuta come coppia di chiavi, non di
        valori (bug #26)."""
        builder = DummyBuilder()
        ctrl = ResultController(SimpleNamespace(current_result=None, active_ctype="similarity_check"))
        cols = ["ID_1", "Name_1", "ID_2", "Name_2", "Sim%"]
        rows = [[10, "Mario", 20, "Marco", "88.0"]]
        payload = ctrl.extract_similarity_exception_payload(cols, rows, key_col="")
        self.assertEqual(payload["pair_records"], ["ID:10 | ID:20"])
        # pair_values non e' influenzato dal key_col
        self.assertEqual(payload["pair_values"], ["Mario | Marco"])

    def test_similarity_pair_records_from_dashboard_actually_excludes(self):
        """Regressione bug #26: una coppia di record esclusa dalla dashboard
        (key_col vuoto) deve effettivamente sparire dai risultati alla
        riesecuzione. Prima il fallback senza prefisso veniva trattato come
        coppia di valori e non escludeva nulla."""
        from engines import SimilarityEngine
        ctrl = ResultController(SimpleNamespace(current_result=None, active_ctype="similarity_check"))
        cols = ["ID_1", "Name_1", "ID_2", "Name_2", "Sim%"]
        rows = [["1", "Mario Rossi", "2", "Maria Rossi", "90.9"]]
        data = [(1, "Mario Rossi"), (2, "Maria Rossi")]
        # baseline: la coppia c'e'
        self.assertEqual(len(SimilarityEngine.find_similar(data, threshold=80)), 1)
        # esclusione catturata dalla dashboard (key_col vuoto)
        exc = ctrl.extract_similarity_exception_payload(cols, rows, key_col="")["pair_records"]
        # alla riesecuzione la coppia deve sparire
        self.assertEqual(len(SimilarityEngine.find_similar(data, threshold=80, exceptions=exc)), 0)

    def test_similarity_builder_record_exclusions_use_or_after_first(self):
        class FakeSimilarityBuilder:
            def __init__(self):
                self._exclude_cond_rows = []

            def get_exception_column(self):
                return "ID"

            def get_exclude_conditions(self):
                return ui_components.SimilarityBuilder.get_exclude_conditions(self)

            def _add_exclude_cond_row(self, col="", op="=", val=""):
                op_display = op + "  (" + ui_components.constants.OPERATORS.get(op, "") + ")"
                self._exclude_cond_rows.append({
                    "col": DummyVar(col),
                    "op": DummyVar(op_display),
                    "val": DummyVar(val),
                    "logic": DummyVar("AND"),
                })

        builder = FakeSimilarityBuilder()

        added = ui_components.SimilarityBuilder.add_record_exclusions(builder, ["10", "20"])

        self.assertEqual(added, 2)
        self.assertEqual(builder._exclude_cond_rows[0]["logic"].get(), "AND")
        self.assertEqual(builder._exclude_cond_rows[1]["logic"].get(), "OR")

    def test_duplicate_builder_exclusions_are_saved_as_or_after_first(self):
        builder = SimpleNamespace(
            var_table=DummyVar("People"),
            var_col=DummyVar("Name"),
            var_key=DummyVar("ID"),
            var_disp=DummyVar("ID, Name"),
            var_phonetic=DummyVar(False),
            txt_exc=DummyText(""),
            _filter_rows=[],
            _excl_rows=[
                {"col": DummyVar("ID"), "op": DummyVar("="), "val": DummyVar("10")},
                {"col": DummyVar("ID"), "op": DummyVar("="), "val": DummyVar("20")},
            ],
        )

        cfg = ui_components.DuplicateBuilder.get_config(builder)

        self.assertEqual(
            cfg["exclude_conditions"],
            [
                {"column": "ID", "operator": "=", "value": "10", "logic": "AND"},
                {"column": "ID", "operator": "=", "value": "20", "logic": "OR"},
            ],
        )

    def test_effective_groups_fall_back_to_macrosettore_tags(self):
        state = SimpleNamespace(
            group_store=SimpleNamespace(
                all_groups=lambda: [{"name": "Legacy", "database_label": "", "conditions": [{"name": "Old"}]}]
            ),
            store=SimpleNamespace(
                items=[
                    {"name": "Check A", "tag": "datico"},
                    {"name": "Check B", "tag": "datico"},
                    {"name": "Check C", "tag": "aocasa"},
                ]
            ),
            db_registry=SimpleNamespace(names=lambda: ["Datico.MDB", "aocasa.mdb"]),
            current_db_label="",
        )
        lib = LibraryController(state, DBController(state))

        groups = lib._get_effective_groups()

        self.assertEqual([group["name"] for group in groups], ["aocasa", "datico"])
        self.assertEqual(groups[0]["database_label"], "aocasa.mdb")
        self.assertEqual(groups[1]["database_label"], "Datico.MDB")
        self.assertEqual(len(groups[1]["conditions"]), 2)

    def test_prepare_condition_for_storage_normalizes_periodic_review(self):
        state = SimpleNamespace(
            current_db_label="Datico.mdb",
            db=SimpleNamespace(connected=False, db_path=""),
            db_registry=SimpleNamespace(names=lambda: []),
        )
        lib = LibraryController(state, DBController(state))

        prepared = lib.prepare_condition_for_storage({
            "name": "Controllo mese",
            "periodic_review_enabled": True,
            "periodic_review_cycle": "MONTHLY",
            "periodic_review_note": "Aggiornare mese corrente ",
            "periodic_review_last_ack": "2026-05-01T09:00:00",
        })

        self.assertEqual(prepared["database_label"], "Datico.mdb")
        self.assertEqual(prepared["periodic_review_cycle"], "monthly")
        self.assertEqual(prepared["periodic_review_note"], "Aggiornare mese corrente")

    def test_prepare_condition_for_storage_clears_periodic_review_when_disabled(self):
        state = SimpleNamespace(
            current_db_label="",
            db=SimpleNamespace(connected=False, db_path=""),
            db_registry=SimpleNamespace(names=lambda: []),
        )
        lib = LibraryController(state, DBController(state))

        prepared = lib.prepare_condition_for_storage({
            "name": "Controllo statico",
            "periodic_review_enabled": False,
            "periodic_review_cycle": "monthly",
            "periodic_review_note": "Da pulire",
            "periodic_review_last_ack": "2026-05-01T09:00:00",
        })

        self.assertEqual(prepared["periodic_review_cycle"], "")
        self.assertEqual(prepared["periodic_review_note"], "")
        self.assertEqual(prepared["periodic_review_last_ack"], "")


class StorageV5Tests(unittest.TestCase):
    def test_group_store_loads_legacy_list_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "groups.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"Gruppo A": [{"name": "Check 1", "type": "duplicate_check"}]}, fh)

            store = GroupStore(path)

            self.assertEqual(store.names(), ["Gruppo A"])
            group = store.get("Gruppo A")
            self.assertEqual(group["name"], "Gruppo A")
            self.assertEqual(group["database_label"], "")
            self.assertEqual(group["conditions"][0]["name"], "Check 1")

    def test_group_store_saves_database_binding_and_propagates_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "groups.json")
            store = GroupStore(path)

            store.save_group(
                "Datico",
                [{"name": "Check 1", "type": "duplicate_check"}],
                database_label="Datico.mdb",
            )

            group = store.get("Datico")
            self.assertEqual(group["database_label"], "Datico.mdb")
            self.assertEqual(group["conditions"][0]["database_label"], "Datico.mdb")

    def test_database_registry_remembers_last_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "db_registry.json")
            registry = DatabaseRegistry(path)

            registry.remember("Datico.mdb")
            registry.set_path("Datico.mdb", r"C:\Data\Datico.mdb")

            self.assertEqual(registry.names(), ["Datico.mdb"])
            self.assertEqual(registry.get_path("Datico.mdb"), r"C:\Data\Datico.mdb")

    def test_database_registry_entries_are_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "db_registry.json")
            registry = DatabaseRegistry(path)

            registry.set_path("Zeta.mdb", r"C:\Data\Zeta.mdb")
            registry.set_path("Alpha.mdb", r"C:\Data\Alpha.mdb")

            self.assertEqual(
                [entry["label"] for entry in registry.entries()],
                ["Alpha.mdb", "Zeta.mdb"],
            )

    def test_periodic_review_summary_marks_monthly_conditions_due(self):
        summary = ui_components.periodic_review_summary(
            {
                "periodic_review_enabled": True,
                "periodic_review_cycle": "monthly",
                "periodic_review_note": "Aggiornare mese",
                "periodic_review_last_ack": "2026-04-30T23:00:00",
            },
            now=datetime(2026, 5, 12, 10, 0, 0),
        )

        self.assertTrue(summary["due"])
        self.assertIn("Mensile DA AGG.", summary["label"])

    def test_condition_store_normalize_periodic_review_defaults_cycle_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "conditions.json")
            store = ConditionStore(path)
            store.add({
                "name": "Controllo periodo",
                "type": "value_comparison",
                "periodic_review_enabled": True,
                "periodic_review_cycle": "BOGUS",
                "periodic_review_note": "  Aggiornare  ",
                "periodic_review_last_ack": "2026-05-01T09:00:00",
            })
            cond = store.items[0]
            self.assertEqual(cond["periodic_review_cycle"], "monthly")
            self.assertEqual(cond["periodic_review_note"], "Aggiornare")
            self.assertEqual(cond["periodic_review_last_ack"], "2026-05-01T09:00:00")

    def test_condition_store_normalize_periodic_review_clears_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "conditions.json")
            store = ConditionStore(path)
            store.add({
                "name": "Controllo statico",
                "type": "value_comparison",
                "periodic_review_enabled": False,
                "periodic_review_cycle": "monthly",
                "periodic_review_note": "Da pulire",
                "periodic_review_last_ack": "2026-05-01T09:00:00",
            })
            cond = store.items[0]
            self.assertEqual(cond["periodic_review_cycle"], "")
            self.assertEqual(cond["periodic_review_note"], "")
            self.assertEqual(cond["periodic_review_last_ack"], "")


class DirectRecordEditTests(unittest.TestCase):
    """Verifica modifica diretta di un record dal risultato di una condizione."""

    def test_direct_update_gating(self):
        ctrl = ResultController(SimpleNamespace(current_result=None))
        # mono-tabella con PK riconoscibile -> editabile
        ctrl.state.current_result = {"source_table": "Clienti", "columns": ["ID", "Nome"]}
        self.assertTrue(ctrl.result_supports_direct_update())
        # risultato fuzzy (colonne _1/_2) -> NON editabile (mappa 2 record)
        ctrl.state.current_result = {"source_table": "Clienti", "columns": ["ID_1", "Nome_1", "ID_2"]}
        self.assertFalse(ctrl.result_supports_direct_update())
        # senza source_table -> NON editabile
        ctrl.state.current_result = {"columns": ["ID", "Nome"]}
        self.assertFalse(ctrl.result_supports_direct_update())


class SafeSingleRecordUpdateTests(unittest.TestCase):
    """update_record_safe garantisce che l'UPDATE colpisca ESATTAMENTE 1 record:
    verifica COUNT prima di scrivere, altrimenti rifiuta senza toccare nulla."""

    class _Cursor:
        def __init__(self, count):
            self._count = count
            self.updates = []
            self.rowcount = 1
            self._fetch = None
        def execute(self, sql, params=None):
            p = list(params or [])
            if sql.strip().upper().startswith("SELECT COUNT"):
                self._fetch = (self._count,)
            else:
                self.updates.append((sql, p))
        def fetchone(self):
            return self._fetch

    class _Conn:
        def __init__(self, count):
            self.cur = SafeSingleRecordUpdateTests._Cursor(count)
            self.committed = False
            self.rolled = False
        def cursor(self):
            return self.cur
        def commit(self):
            self.committed = True
        def rollback(self):
            self.rolled = True

    def _db(self, count):
        from db_manager import DatabaseManager
        db = DatabaseManager()
        db.conn = self._Conn(count)
        return db

    def test_updates_only_when_exactly_one_match(self):
        db = self._db(count=1)
        n = db.update_record_safe("Clienti", {"ID": 5}, {"ID": 5, "Nome": "X", "Citta": "Y"})
        self.assertEqual(n, 1)
        self.assertTrue(db.conn.committed)
        sql, params = db.conn.cur.updates[0]
        set_part, where_part = sql.split("WHERE")
        self.assertIn("[Nome] = ?", set_part)
        self.assertIn("[Citta] = ?", set_part)
        self.assertNotIn("[ID]", set_part)
        self.assertIn("[ID] = ?", where_part)
        self.assertEqual(params, ["X", "Y", 5])

    def test_refuses_when_zero_matches(self):
        db = self._db(count=0)
        with self.assertRaises(ValueError):
            db.update_record_safe("Clienti", {"ID": 5}, {"ID": 5, "Nome": "X"})
        self.assertEqual(db.conn.cur.updates, [])   # nessuna scrittura
        self.assertFalse(db.conn.committed)

    def test_refuses_when_multiple_matches(self):
        db = self._db(count=3)
        with self.assertRaises(ValueError):
            db.update_record_safe("Clienti", {"Nome": "Mario"}, {"Nome": "Mario", "Citta": "Y"})
        self.assertEqual(db.conn.cur.updates, [])   # MAI scrive se >1
        self.assertFalse(db.conn.committed)

    def test_composite_key_uses_all_columns_in_where(self):
        db = self._db(count=1)
        db.update_record_safe("T", {"A": 1, "B": 2}, {"A": 1, "B": 2, "Val": "z"})
        sql, params = db.conn.cur.updates[0]
        where_part = sql.split("WHERE")[1]
        self.assertIn("[A] = ?", where_part)
        self.assertIn("[B] = ?", where_part)
        self.assertIn("AND", where_part)
        self.assertEqual(params, ["z", 1, 2])

    def test_no_editable_columns_returns_zero_without_query(self):
        db = self._db(count=1)
        self.assertEqual(db.update_record_safe("T", {"ID": 5}, {"ID": 5}), 0)
        self.assertEqual(db.conn.cur.updates, [])

    def test_empty_key_refuses(self):
        db = self._db(count=1)
        with self.assertRaises(ValueError):
            db.update_record_safe("T", {}, {"Nome": "X"})

    def test_primary_keys_accessor(self):
        from db_manager import DatabaseManager
        db = DatabaseManager()
        self.assertEqual(db.primary_keys("Sconosciuta"), [])
        db.table_pks = {"Clienti": ["ID"]}
        self.assertEqual(db.primary_keys("Clienti"), ["ID"])


class BulkValueReplacementTests(unittest.TestCase):
    """Sostituzione massiva di valori su condizioni selezionate in libreria (#28)."""

    def test_replaces_value_in_filter_when_column_and_value_match(self):
        from storage import apply_value_replacement
        cond = {
            "name": "Vendite mese",
            "conditions": [
                {"column": "mese", "operator": "=", "value": "giu", "logic": "AND"},
                {"column": "anno", "operator": "=", "value": "2026", "logic": "AND"},
            ],
        }
        new_cond, changes = apply_value_replacement(cond, "mese", "giu", "mag")
        self.assertEqual(new_cond["conditions"][0]["value"], "mag")
        self.assertEqual(new_cond["conditions"][1]["value"], "2026")  # invariato
        self.assertEqual(len(changes), 1)

    def test_does_not_mutate_original(self):
        from storage import apply_value_replacement
        cond = {"conditions": [{"column": "mese", "operator": "=", "value": "giu"}]}
        apply_value_replacement(cond, "mese", "giu", "mag")
        self.assertEqual(cond["conditions"][0]["value"], "giu")  # originale intatto

    def test_blank_column_matches_value_in_any_column(self):
        from storage import apply_value_replacement
        cond = {"conditions": [
            {"column": "mese", "operator": "=", "value": "giu"},
            {"column": "periodo", "operator": "=", "value": "giu"},
        ]}
        new_cond, changes = apply_value_replacement(cond, "", "giu", "mag")
        self.assertEqual([r["value"] for r in new_cond["conditions"]], ["mag", "mag"])
        self.assertEqual(len(changes), 2)

    def test_replaces_in_exclude_conditions_too(self):
        from storage import apply_value_replacement
        cond = {"exclude_conditions": [{"column": "mese", "operator": "=", "value": "giu"}]}
        new_cond, changes = apply_value_replacement(cond, "mese", "giu", "mag")
        self.assertEqual(new_cond["exclude_conditions"][0]["value"], "mag")
        self.assertEqual(len(changes), 1)

    def test_value_match_is_case_insensitive_and_trimmed(self):
        from storage import apply_value_replacement
        cond = {"conditions": [{"column": "Mese", "operator": "=", "value": " GIU "}]}
        new_cond, changes = apply_value_replacement(cond, "mese", "giu", "mag")
        self.assertEqual(new_cond["conditions"][0]["value"], "mag")
        self.assertEqual(len(changes), 1)

    def test_no_match_returns_empty_changes(self):
        from storage import apply_value_replacement
        cond = {"conditions": [{"column": "mese", "operator": "=", "value": "lug"}]}
        new_cond, changes = apply_value_replacement(cond, "mese", "giu", "mag")
        self.assertEqual(changes, [])
        self.assertEqual(new_cond["conditions"][0]["value"], "lug")

    def test_replaces_quoted_literal_in_formula_when_column_present(self):
        from storage import apply_value_replacement
        cond = {"type": "formula_condition", "formula": "[mese] = 'giu' AND [stato] = 'OK'"}
        new_cond, changes = apply_value_replacement(cond, "mese", "giu", "mag")
        self.assertEqual(new_cond["formula"], "[mese] = 'mag' AND [stato] = 'OK'")
        self.assertEqual(len(changes), 1)

    def test_does_not_touch_formula_when_column_absent(self):
        from storage import apply_value_replacement
        cond = {"type": "formula_condition", "formula": "[stato] = 'giu'"}
        new_cond, changes = apply_value_replacement(cond, "mese", "giu", "mag")
        self.assertEqual(new_cond["formula"], "[stato] = 'giu'")
        self.assertEqual(changes, [])


if __name__ == "__main__":
    unittest.main()
