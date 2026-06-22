import threading
import logging
import csv
import os
from datetime import datetime
from tkinter import messagebox, filedialog, simpledialog

logger = logging.getLogger("AccessDBTool.ResultController")


class ResultController:
    def __init__(self, state):
        self.state = state
        self._on_results_callback = None
        self._on_results_found_callback = None  # chiamata quando count > 0 (es. per auto-switch tab)
        self._export_csv_callback = None
        self._edit_record_callback = None
        self._bulk_replace_callback = None
        self._add_to_exclusions_callback = None
        self._open_in_builder_callback = None

    def set_results_callback(self, callback):
        self._on_results_callback = callback

    def set_results_found_callback(self, callback):
        """Callback chiamato quando i risultati contengono record (per auto-switch a report)."""
        self._on_results_found_callback = callback

    def set_export_csv_callback(self, callback):
        self._export_csv_callback = callback

    def set_edit_record_callback(self, callback):
        self._edit_record_callback = callback

    def set_bulk_replace_callback(self, callback):
        self._bulk_replace_callback = callback

    def set_add_to_exclusions_callback(self, callback):
        self._add_to_exclusions_callback = callback

    def set_open_in_builder_callback(self, callback):
        self._open_in_builder_callback = callback

    def validate_active_builder(self):
        if self.state.active_builder and hasattr(self.state.active_builder, "validate"):
            ok, msg = self.state.active_builder.validate()
            if not ok:
                self.state.status.set(msg)
                messagebox.showwarning("Configurazione incompleta", msg)
                return False
        return True

    def run_current(self, display_cols=None):
        if not self.state.db.connected:
            return messagebox.showwarning("!", "Apri DB")
        ctype = self.state.active_ctype
        if not ctype:
            return messagebox.showwarning("!", "Seleziona tipo analisi")
        if not self.validate_active_builder():
            return
        cond = {
            "type": ctype,
            "name": "Analisi Manuale",
            "tables": self.state.sel_tables,
            "columns": display_cols or [],
            "display_columns": display_cols or [],
        }
        if self.state.active_builder:
            cond.update(self.state.active_builder.get_config())
        threading.Thread(target=self._execute_task, args=(cond,), daemon=True).start()

    def _execute_task(self, cond):
        self.state.status.set("Esecuzione in corso...")
        try:
            res = self.state.executor.run(cond)
            if isinstance(res, dict):
                res["_condition"] = cond
                res["_condition_type"] = cond.get("type")
            self._show_results(res)
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    def _show_results(self, res):
        self.state.current_result = res
        if self._on_results_callback:
            self._on_results_callback(res)
        count = res.get("count", 0) if isinstance(res, dict) else 0
        if count == 0:
            self.state.status.set("Esecuzione completata — nessun problema trovato.")
            # Mostra un messagebox OK sul thread principale (posticipato via after)
            try:
                master = self.state.status.master
                if master:
                    master.after(100, lambda: messagebox.showinfo(
                        "OK", "Nessun problema trovato in questo controllo."))
            except Exception:
                pass
        else:
            self.state.status.set(f"Risultati caricati ({count} record).")
            # Auto-switch al report / dashboard per mostrare i risultati
            if self._on_results_found_callback:
                try:
                    master = self.state.status.master
                    if master:
                        master.after(100, self._on_results_found_callback)
                except Exception:
                    pass

    def result_supports_direct_update(self):
        res = self.state.current_result
        if not res or not res.get("source_table"):
            return False
        cols = res.get("columns", [])
        blocked = {"Tab1", "Tab2", "Key1", "Key2", "Val1", "Val2", "Sim%"}
        return not any(str(c).endswith(("_1", "_2")) or c in blocked for c in cols)

    def _current_result_condition_type(self):
        if self.state.current_result and isinstance(self.state.current_result, dict):
            return self.state.current_result.get("_condition_type", "")
        return self.state.active_ctype

    def extract_similarity_exception_payload(self, cols, selected_rows, key_col=""):
        """Splits selected similarity-result rows into the four exclusion modes.

        Returns dict with keys pair_values, pair_records, left_records, right_records.
        Pure: takes the visible column names, the selected rows (lists of values)
        and the builder's key column, so it can be unit-tested without Tk.
        """
        payload = {"pair_values": [], "pair_records": [], "left_records": [], "right_records": []}
        if not cols or not selected_rows:
            return payload
        left_idx = [i for i, n in enumerate(cols) if str(n).endswith("_1")]
        right_idx = [i for i, n in enumerate(cols) if str(n).endswith("_2")]
        lk = left_idx[0] if left_idx else (0 if cols else -1)
        lv = left_idx[1] if len(left_idx) > 1 else (1 if len(cols) > 1 else -1)
        rk = right_idx[0] if right_idx else (2 if len(cols) > 2 else -1)
        rv = right_idx[1] if len(right_idx) > 1 else (3 if len(cols) > 3 else -1)
        seen = {k: set() for k in payload}
        for vals in selected_rows:
            left_key = str(vals[lk]).strip() if 0 <= lk < len(vals) else ""
            left_val = str(vals[lv]).strip() if 0 <= lv < len(vals) else ""
            right_key = str(vals[rk]).strip() if 0 <= rk < len(vals) else ""
            right_val = str(vals[rv]).strip() if 0 <= rv < len(vals) else ""
            pair_values = f"{left_val} | {right_val}" if left_val and right_val else ""
            # pair_records: preferisce la colonna chiave (ID) del builder; se
            # manca, fallback sui valori key grezzi senza prefisso (cosi' la
            # modalita' 'coppia di record' non e' silenziosamente vuota quando
            # key_column non e' impostata nel builder).
            if key_col and left_key and right_key:
                pair_records = f"{key_col}:{left_key} | {key_col}:{right_key}"
            elif left_key and right_key:
                pair_records = f"{left_key} | {right_key}"
            else:
                pair_records = ""
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

    def add_similarity_exceptions(self, mode, cols, selected_rows, key_col, builder):
        """Applies one similarity exclusion mode to the active builder. Returns count added."""
        payload = self.extract_similarity_exception_payload(cols, selected_rows, key_col)
        vals = payload.get(mode, [])
        if not vals or builder is None:
            logger.info(
                "add_similarity_exceptions: mode=%s key_col=%r rows=%d cols=%s "
                "-> nessun valore estratto per la modalita'",
                mode, key_col, len(selected_rows or []), cols,
            )
            return 0
        if mode in ("pair_values", "pair_records"):
            cnt = builder.add_exceptions(vals)
        elif hasattr(builder, "add_record_exclusions"):
            cnt = builder.add_record_exclusions(vals, column=key_col or None)
        else:
            cnt = builder.add_exceptions(vals, column=key_col or None)
        logger.info(
            "add_similarity_exceptions: mode=%s key_col=%r vals=%d aggiunte=%d (es. %s)",
            mode, key_col, len(vals), cnt, vals[:2],
        )
        return cnt

    def add_exceptions_from_rows(self, cols, selected_rows, builder, target_column=""):
        """Non-fuzzy path: collects one value per selected row into the builder exceptions."""
        if builder is None or not selected_rows:
            return 0
        target = target_column
        if not target and hasattr(builder, "get_exception_column"):
            target = builder.get_exception_column()
        vals_to_add = []
        for vals in selected_rows:
            if not vals:
                continue
            if target and target in cols:
                val = str(vals[cols.index(target)]).strip()
            else:
                val = str(vals[0]).strip()
            if val:
                vals_to_add.append(val)
        if not vals_to_add:
            return 0
        return builder.add_exceptions(vals_to_add, column=target or None)

    def apply_pending_exclusion(self, pending, builder):
        """Applica un'esclusione 'in sospeso' (catturata dai risultati in
        dashboard) a un builder appena ricostruito nel tab Controlli.
        Ritorna il numero di esclusioni aggiunte."""
        if not pending or builder is None:
            return 0
        kind = pending.get("kind")
        cols = pending.get("cols", [])
        rows = pending.get("rows", [])
        if kind == "similarity":
            return self.add_similarity_exceptions(
                pending.get("mode", ""), cols, rows,
                pending.get("key_col", ""), builder,
            )
        return self.add_exceptions_from_rows(
            cols, rows, builder, pending.get("target", ""),
        )

    def resolve_non_fuzzy_exception_target(self, clicked_col=""):
        if not self.state.current_result:
            return ""
        ctype = self._current_result_condition_type()
        if ctype == "similarity_check":
            return ""
        cols = self.state.current_result.get("columns", [])
        if clicked_col and clicked_col in cols:
            return clicked_col
        return cols[0] if cols else ""

    def export_csv(self):
        if not self.state.current_result:
            return
        path = filedialog.asksaveasfilename(
            title="Esporta risultati",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh, delimiter=";")
                w.writerow(self.state.current_result["columns"])
                w.writerows(self.state.current_result["rows"])
            self.state.status.set(f"Esportato: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Errore export", str(e))

    def apply_bulk_replace(self, dialog_result, visible_indices):
        """Applies a bulk column replace against the source table.

        Casts both the new value and each PK through db.cast_value before the
        UPDATE so types match the Access schema. Returns number of rows updated.
        Pure DB logic: the view supplies the collected dialog result and the list
        of currently-visible (filtered) row indices.

        Ritorna -1 (sentinella) se la colonna chiave (PK) non e' identificabile
        con certezza: in tal caso l'update viene RIFIUTATO per evitare di
        aggiornare in massa righe sbagliate. Il chiamante (view) interpreta -1
        come "PK ambigua, nessuna modifica applicata".
        """
        res = self.state.current_result
        db = self.state.db
        if not res or not dialog_result:
            return 0
        cols = res.get("columns", [])
        rows = res.get("rows", [])
        col = dialog_result["column"]
        val = dialog_result["value"]
        # Nessun fallback su cols[0]: se non riconosciamo una vera PK, rifiutiamo.
        pk_col = next((c for c in cols if str(c).lower() in ("id", "pk", "codice", "code", "key")), None)
        if pk_col is None:
            logger.warning("Bulk replace rifiutato: colonna chiave (PK) non identificabile tra %s", cols)
            return -1
        table = res.get("source_table")
        if not table and self.state.active_builder:
            cfg = self.state.active_builder.get_config()
            table = cfg.get("table") or cfg.get("source_table")
        if not table:
            return 0
        pk_idx = cols.index(pk_col)
        table_cols = set(db.columns(table))
        sql_col = col[:-2] if (str(col).endswith(("_1", "_2")) and col not in table_cols) else col
        sql_pk = pk_col[:-2] if (str(pk_col).endswith(("_1", "_2")) and pk_col not in table_cols) else pk_col
        if sql_col not in table_cols or sql_pk not in table_cols:
            return 0
        # Raccolta delle coppie (valore, pk) tipizzate; un solo commit via bulk_update.
        pairs = []
        for idx in visible_indices:
            if idx < 0 or idx >= len(rows):
                continue
            pk_val = rows[idx][pk_idx]
            if pk_val is None:
                continue
            try:
                typed_value = db.cast_value(table, sql_col, val)
                typed_pk = db.cast_value(table, sql_pk, pk_val)
                pairs.append((typed_value, typed_pk))
            except Exception as e:
                logger.error("Errore tipizzazione record %s su %s: %s", pk_val, table, e)
        if not pairs:
            return 0
        updated = db.bulk_update(table, sql_col, sql_pk, pairs)
        return updated
