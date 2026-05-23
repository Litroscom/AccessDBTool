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
from access_db_tool import App
from engines import ConditionExecutor
from monitor_engine import MonitorEngine
from storage import DatabaseRegistry, GroupStore


class FakeDB:
    def __init__(self):
        self.fetch_responses = []
        self.fetch_calls = []
        self.execute_calls = []
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
        app = SimpleNamespace(
            status=DummyStatus(),
            mon_tree=DummyTree(),
            mon_log=DummyMonitorLog(),
        )
        App._handle_monitor_msg(app, {"type": "check_result", "name": "Controllo A", "count": 2, "sound": False})
        self.assertEqual(app.mon_tree.inserted[0][1], "Controllo A")
        self.assertEqual(app.mon_tree.inserted[0][2], "Trovati")
        self.assertEqual(app.mon_log.entries[0]["name"], "Controllo A")

    def test_bulk_replace_casts_values_before_update(self):
        db = FakeDB()
        db.table_columns = {"Invoices": [{"name": "ID"}, {"name": "Amount"}]}
        app = SimpleNamespace(
            current_result={"rows": [[1, 3.0]], "columns": ["ID", "Amount"], "source_table": "Invoices"},
            res_tree=DummyResultTree({"0": [1, 3.0]}),
            db=db,
            active_builder=None,
            status=DummyStatus(),
            wait_window=lambda _dlg: None,
            _apply_res_filter=lambda: None,
            _result_supports_direct_update=lambda: True,
        )

        class StubDialog:
            def __init__(self, _parent, _columns, _record_count):
                self.result = {"column": "Amount", "value": "12,5", "mode": "replace_all"}

        with patch("access_db_tool.ui_components.BulkReplaceDialog", StubDialog), \
             patch("access_db_tool.messagebox.showinfo"), \
             patch("access_db_tool.messagebox.showwarning"), \
             patch("access_db_tool.messagebox.showerror"):
            App._bulk_replace_results(app)

        self.assertEqual(db.execute_calls[0][1], (12.5, 1))

    def test_similarity_exclusion_modes_are_split_correctly(self):
        builder = DummyBuilder()
        app = SimpleNamespace(
            current_result={
                "rows": [[10, "Mario", 20, "Marco", "88.0"]],
                "columns": ["ID_1", "Name_1", "ID_2", "Name_2", "Sim%"],
                "_condition_type": "similarity_check",
            },
            res_tree=DummyResultTree({"0": [10, "Mario", 20, "Marco", "88.0"]}),
            active_builder=builder,
            nb=DummyNotebook(),
            tab_build="build",
            _current_result_condition_type=lambda: "similarity_check",
        )
        app._extract_similarity_exception_payload = lambda: App._extract_similarity_exception_payload(app)

        with patch("access_db_tool.messagebox.showinfo"):
            App._add_selected_to_exceptions(app, mode="pair_values")
            App._add_selected_to_exceptions(app, mode="pair_records")
            App._add_selected_to_exceptions(app, mode="left_records")
            App._add_selected_to_exceptions(app, mode="right_records")

        self.assertEqual(builder.exception_calls[0][0], ["Mario | Marco"])
        self.assertEqual(builder.exception_calls[1][0], ["ID:10 | ID:20"])
        self.assertEqual(builder.record_calls[0][0], ["10"])
        self.assertEqual(builder.record_calls[1][0], ["20"])
        self.assertEqual(app.nb.selected, "build")

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
        app = SimpleNamespace(
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
        )
        app._guess_database_label_for_tag = lambda tag: App._guess_database_label_for_tag(app, tag)
        app._build_tag_groups = lambda: App._build_tag_groups(app)

        groups = App._get_effective_groups(app)

        self.assertEqual([group["name"] for group in groups], ["aocasa", "datico"])
        self.assertEqual(groups[0]["database_label"], "aocasa.mdb")
        self.assertEqual(groups[1]["database_label"], "Datico.MDB")
        self.assertEqual(len(groups[1]["conditions"]), 2)

    def test_prepare_condition_for_storage_normalizes_periodic_review(self):
        app = SimpleNamespace(
            _database_label_for_condition=lambda cond: App._database_label_for_condition(app, cond),
            current_db_label="Datico.mdb",
            db=SimpleNamespace(connected=False, db_path=""),
            _register_database_reference=lambda _label, _path="": "",
        )

        prepared = App._prepare_condition_for_storage(app, {
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
        app = SimpleNamespace(
            _database_label_for_condition=lambda cond: App._database_label_for_condition(app, cond),
            current_db_label="",
            db=SimpleNamespace(connected=False, db_path=""),
            _register_database_reference=lambda _label, _path="": "",
        )

        prepared = App._prepare_condition_for_storage(app, {
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


class ConditionManagerV6Tests(unittest.TestCase):
    def test_sorted_store_indices_can_order_by_name(self):
        manager = SimpleNamespace(
            store=SimpleNamespace(items=[
                {"name": "Zeta", "tag": "beta"},
                {"name": "Alfa", "tag": "gamma"},
                {"name": "Beta", "tag": "alfa"},
            ]),
            var_sort=DummyVar("Nome"),
        )

        indices = ui_components.ConditionManager._sorted_store_indices(manager)

        self.assertEqual(indices, [1, 2, 0])

    def test_sorted_store_indices_can_order_by_category(self):
        manager = SimpleNamespace(
            store=SimpleNamespace(items=[
                {"name": "Zeta", "tag": "beta"},
                {"name": "Alfa", "tag": "gamma"},
                {"name": "Beta", "tag": "alfa"},
            ]),
            var_sort=DummyVar("Categoria"),
        )

        indices = ui_components.ConditionManager._sorted_store_indices(manager)

        self.assertEqual(indices, [2, 0, 1])


if __name__ == "__main__":
    unittest.main()
