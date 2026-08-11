import re
import unicodedata
import logging
from collections import defaultdict
from difflib import SequenceMatcher
import constants

try:
    from rapidfuzz import fuzz as rfuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

logger = logging.getLogger("AccessDBTool.Engines")


from db_manager import DatabaseManager

# Quota un identificatore SQL in modo sicuro per Access (escape della parentesi chiusa).
# Delegato a DatabaseManager._qi per evitare duplicazione.
_qi = DatabaseManager._qi

class SimilarityEngine:
    @staticmethod
    def ratio(a, b):
        if not a or not b:
            return 0.0
        sa = str(a).strip().upper()
        sb = str(b).strip().upper()
        if sa == sb:
            return 100.0
        if HAS_RAPIDFUZZ:
            return rfuzz.ratio(sa, sb)
        return SequenceMatcher(None, sa, sb).ratio() * 100

    @staticmethod
    def italian_phonetic(s):
        if not s:
            return ""
        t = unicodedata.normalize("NFD", str(s).upper())
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")

        replacements = [
            (r"SCHI",   "SKI"), (r"SCHE",   "SKE"), (r"SCIA",   "SHA"),
            (r"SCIO",   "SHO"), (r"SCIU",   "SHU"), (r"SCE",    "SHE"),
            (r"SCI",    "SHI"), (r"GNI",    "NI"),  (r"GNE",    "NE"),
            (r"GNA",    "NA"),  (r"GNO",    "NO"),  (r"GNU",    "NU"),
            (r"GN",     "N"),   (r"GLI",    "LI"),  (r"GL",     "L"),
            (r"CHI",    "KI"),  (r"CHE",    "KE"),  (r"CH",     "K"),
            (r"GHI",    "GI"),  (r"GHE",    "GE"),  (r"CE",     "CHE"),
            (r"CI",     "CHI"), (r"GE",     "JE"),  (r"GI",     "JI"),
            (r"PH",     "F"),   (r"TH",     "T"),   (r"CK",     "K"),
            (r"QUE",    "K"),   (r"QU",     "KW"),  (r"SZ",     "S"),
            (r"TS",     "Z"),   (r"W",      "V"),   (r"Y",      "I"),
            (r"X",      "KS"),  (r"Z",      "S"),   (r"Q",      "K"),
        ]
        for pattern, repl in replacements:
            t = t.replace(pattern, repl)

        t = re.sub(r"C(?=[^HAEIOU ]|$)", "K", t)
        t = re.sub(r"(?<=[AEIOU])H(?=[AEIOU])", "", t)
        t = re.sub(r"\bH", "", t)
        t = re.sub(r"([BCDFGHJKLMNPQRSTVXZ])\1+", r"\1", t)
        t = re.sub(r"([AEIOU])\1+", r"\1", t)
        t = re.sub(r" +", " ", t).strip()
        return t

    @staticmethod
    def find_duplicates(data, check_phonetic=False):
        groups = defaultdict(list)
        for k, v in data:
            if v is not None:
                val = str(v).strip().upper()
                key = SimilarityEngine.italian_phonetic(val) if check_phonetic else val
                groups[key].append((k, v))
        return {g: items for g, items in groups.items() if len(items) > 1}

    @staticmethod
    def find_similar(data, threshold=80, exceptions=None, progress_cb=None,
                     check_containment=False, check_prefix=False, check_phonetic=False,
                     min_prefix=3, stop_event=None):
        exc_single = set()
        exc_pairs = set()
        exc_key_pairs = set()   # coppie di chiavi ID specifiche (formato "IDcol:val | IDcol:val")
        exc_keys = set()        # singoli ID record da escludere (es. "39716" o "ID:39716")
        if exceptions:
            for e in exceptions:
                s = str(e).strip()
                if " | " in s:
                    parts = [p.strip() for p in s.split("|", 1)]
                    if len(parts) == 2 and ":" in parts[0] and ":" in parts[1]:
                        # Formato chiave: "IDcol:val | IDcol:val"  → esclude coppia di record specifici
                        v1 = parts[0].split(":", 1)[1].strip().upper()
                        v2 = parts[1].split(":", 1)[1].strip().upper()
                        exc_key_pairs.add(tuple(sorted([v1, v2])))
                    else:
                        p_up = sorted([p.strip().upper() for p in parts])
                        exc_pairs.add(tuple(p_up))
                elif ":" in s:
                    # Singolo ID record: "ID:39716"
                    exc_keys.add(s.split(":", 1)[1].strip().upper())
                elif s.isdigit():
                    # Singolo ID record numerico (molto comune nelle condizioni importate)
                    exc_keys.add(s.upper())
                else:
                    exc_single.add(s.strip().upper())

        need_tokens = check_containment or check_prefix
        items = []
        seen_uniq = set()
        for k, v in data:
            if v and str(v).strip():
                val = str(v).strip()
                ui = (k, val)
                if ui in seen_uniq: continue
                seen_uniq.add(ui)
                items.append({
                    "key": k, "val": val, "upper": val.upper(), "len": len(val),
                    "tokens": set(val.upper().split()) if need_tokens else None,
                    "phonetic": SimilarityEngine.italian_phonetic(val) if check_phonetic else None,
                })

        if len(items) > 50000:
            logger.warning(f"find_similar: {len(items)} stringhe, possibile lentezza O(n^2)")

        # OTTIMIZZAZIONE: ordina per lunghezza stringa.
        # Permette di interrompere il ciclo interno (break) appena la differenza
        # di lunghezza supera la soglia, perché tutti i successivi sono ancora più
        # lunghi. Riduce da O(n²) a O(n·k) dove k = stringhe di lunghezza simile.
        items.sort(key=lambda x: x["len"])

        n = len(items)
        results = []
        seen_pairs = set()
        len_tol = (1 - threshold / 100)
        comparisons = 0

        for i in range(n):
            if stop_event and stop_event.is_set():
                logger.info(f"find_similar interrotto dall'utente dopo {comparisons} confronti.")
                break

            it1 = items[i]
            # Lunghezza max del partner entro la tolleranza di lunghezza
            # Se len_tol=0.2 e len=10, max_j_len=12.5 → stringhe > 12 chars skippate
            max_j_len = it1["len"] / (1 - len_tol) if len_tol < 1 else float('inf')

            if progress_cb and i % 200 == 0:
                progress_cb(f"Analisi {i + 1}/{n} stringhe…")

            for j in range(i + 1, n):
                comparisons += 1
                if stop_event and comparisons % 50000 == 0 and stop_event.is_set():
                    break

                it2 = items[j]

                # EARLY BREAK: lista ordinata per lunghezza, se it2 è troppo lungo
                # TUTTI i successivi lo saranno. Funziona solo quando non servono
                # check di contenimento/prefisso (che ignorano la lunghezza).
                if not need_tokens and it2["len"] > max_j_len:
                    break

                if it1["key"] == it2["key"]: continue

                u1, u2 = it1["upper"], it2["upper"]
                if u1 in exc_single or u2 in exc_single: continue
                pair = tuple(sorted([u1, u2]))
                if pair in exc_pairs: continue
                # Controllo esclusione per singoli ID record
                k1_str = str(it1["key"]).upper()
                k2_str = str(it2["key"]).upper()
                if exc_keys and (k1_str in exc_keys or k2_str in exc_keys): continue
                # Controllo esclusione per coppia di ID record
                if exc_key_pairs:
                    kpair = tuple(sorted([k1_str, k2_str]))
                    if kpair in exc_key_pairs: continue
                if u1 == u2: continue

                is_containment = False
                if check_containment:
                    t1, t2 = it1["tokens"], it2["tokens"]
                    if t1 and t2 and (t1.issubset(t2) or t2.issubset(t1)):
                        is_containment = True

                if not is_containment:
                    l1, l2 = it1["len"], it2["len"]
                    if abs(l1 - l2) / max(l1, l2) > len_tol:
                        if not check_prefix: continue
                        t1, t2 = it1["tokens"], it2["tokens"]
                        if t1 and t2:
                            is_candidate, _ = SimilarityEngine._check_prefix_error(u1, u2, t1, t2, min_prefix=min_prefix)
                            if is_candidate:
                                sim_val = SimilarityEngine.ratio(u1, u2)
                                m1, m2 = (it1, it2) if u1 < u2 else (it2, it1)
                                pair_key = (m1["key"], m2["key"])
                                results.append({
                                    "key1": m1["key"], "val1": m1["val"],
                                    "key2": m2["key"], "val2": m2["val"],
                                    "sim": round(sim_val, 1), "prefix": True,
                                })
                                seen_pairs.add(pair_key)
                        continue

                sim = SimilarityEngine.ratio(u1, u2)
                if is_containment and sim < 100: sim = max(sim, 99.9)
                m1, m2 = (it1, it2) if u1 < u2 else (it2, it1)
                pair_key = (m1["key"], m2["key"])

                if sim >= threshold:
                    results.append({"key1": m1["key"], "val1": m1["val"], "key2": m2["key"], "val2": m2["val"], "sim": round(sim, 1)})
                    seen_pairs.add(pair_key)
                elif check_prefix:
                    t1, t2 = it1["tokens"], it2["tokens"]
                    if t1 and t2:
                        is_candidate, _ = SimilarityEngine._check_prefix_error(u1, u2, t1, t2, min_prefix=min_prefix)
                        if is_candidate:
                            results.append({"key1": m1["key"], "val1": m1["val"], "key2": m2["key"], "val2": m2["val"], "sim": round(sim, 1), "prefix": True})
                            seen_pairs.add(pair_key)

        # Fase 2: Matching fonetico con raggruppamento hash-based O(n)
        # Molto più veloce che controllare ogni coppia nel loop O(n²),
        # e trova anche match fonetici tra stringhe di lunghezza molto diversa
        # (che il vecchio codice perdeva a causa del filtro lunghezza).
        if check_phonetic:
            phonetic_groups = defaultdict(list)
            for it in items:
                if it["phonetic"]:
                    phonetic_groups[it["phonetic"]].append(it)
            for group_items in phonetic_groups.values():
                if len(group_items) < 2:
                    continue
                for gi in range(len(group_items)):
                    for gj in range(gi + 1, len(group_items)):
                        g1, g2 = group_items[gi], group_items[gj]
                        u1, u2 = g1["upper"], g2["upper"]
                        if g1["key"] == g2["key"]: continue
                        if u1 == u2: continue
                        if u1 in exc_single or u2 in exc_single: continue
                        exc_pair = tuple(sorted([u1, u2]))
                        if exc_pair in exc_pairs: continue
                        if exc_key_pairs:
                            kpair = tuple(sorted([str(g1["key"]).upper(), str(g2["key"]).upper()]))
                            if kpair in exc_key_pairs: continue
                        m1, m2 = (g1, g2) if u1 < u2 else (g2, g1)
                        pair_key = (m1["key"], m2["key"])
                        if pair_key not in seen_pairs:
                            sim = SimilarityEngine.ratio(u1, u2)
                            results.append({
                                "key1": m1["key"], "val1": m1["val"],
                                "key2": m2["key"], "val2": m2["val"],
                                "sim": round(sim, 1), "phonetic": True
                            })
                            seen_pairs.add(pair_key)

        logger.info(f"find_similar: {comparisons} confronti effettuati, {len(results)} risultati.")
        results.sort(key=lambda x: (0 if x.get("phonetic") else (-1 if x.get("prefix") else 0), -x["sim"]))
        return results

    @staticmethod
    def _check_prefix_error(u1, u2, tokens1, tokens2, min_prefix=3):
        shared_tokens = tokens1 & tokens2
        is_candidate = False
        n = min(len(u1), len(u2))
        mp = max(2, int(min_prefix))  # sicurezza: almeno 2 caratteri
        if n >= mp and u1[:mp] == u2[:mp] and u1 != u2:
            is_candidate = True
        return is_candidate, bool(shared_tokens)


class ConditionExecutor:
    def __init__(self, db):
        self.db = db

    def run(self, cond, progress_cb=None):
        dispatch = {
            "cross_table_existence": self._cross_existence,
            "duplicate_check":       self._duplicates,
            "similarity_check":      self._similarity,
            "value_comparison":      self._comparison,
            "concat_similarity":     self._concat_sim,
            "formula_condition":     self._formula,
            "linked_table_intersection": self._linked_intersection,
            "format_validation":     self._comparison,
            "daily_coverage_check":  self._daily_coverage,
            "mandatory_record_check": self._mandatory_record_check,
            "row_cross_column_check":    self._row_cross_column,
            "aggregate_threshold_check": self._aggregate_threshold,
            "aggregate_multi_table_threshold": self._aggregate_multi_table,
            "lookup_validation":         self._lookup_validation,
            "dependent_condition_check": self._dependent_condition,
        }
        fn = dispatch.get(cond.get("type"))
        if fn is None:
            return self._error("Tipo sconosciuto: " + str(cond.get("type")))
        try:
            return fn(cond, progress_cb)
        except Exception as e:
            logger.error(f"Errore durante l'esecuzione della condizione {cond.get('name')}: {e}")
            return self._error(str(e))

    def _error(self, msg):
        # 'is_error' distingue gli errori reali dai risultati vuoti: senza
        # questo marker, monitor e dashboard mostravano un controllo fallito
        # (SQL, parametri…) come "OK" perché count==0.
        return {"title": "ERRORE", "description": msg, "columns": ["Errore"],
                "rows": [[msg]], "count": 0, "source_table": "", "is_error": True}

    def _result(self, title, desc, cols, rows, table):
        return {"title": title, "description": desc, "columns": cols, "rows": rows, "count": len(rows), "source_table": table}

    def _build_where(self, conditions, alias="", skip_regex=False):
        """Costruisce una WHERE rispettando la precedenza SQL (AND prima di OR).

        La logica e' memorizzata sulla riga successiva alla prima: ``A OR B
        AND C`` deve quindi diventare ``A OR (B AND C)``, non ``(A OR B)
        AND C``.  Raggruppare esplicitamente le clausole rende il risultato
        uguale sia su Access sia nel filtro Python usato per le regex.
        """
        and_groups, current_group, params = [], [], []
        prefix = alias + "." if alias else ""
        for cond in conditions:
            col, op, val = cond["column"], cond["operator"], cond.get("value", "")
            if skip_regex and op in ("REGEXP", "NOT REGEXP"):
                continue
            
            val_s = str(val)
            if op in ("IS NULL", "IS NOT NULL"):
                clause = prefix + _qi(col) + " " + op
            else:
                current_op = op
                # Supporto Jolly (*)
                if "*" in val_s:
                    # Preserva NOT LIKE quando l'operatore originale è NOT LIKE
                    current_op = "NOT LIKE" if op == "NOT LIKE" else "LIKE"
                    val_s = val_s.replace("*", "%")
                elif op == "LIKE":
                    val_s = "%" + val_s + "%"
                elif op == "NOT LIKE":
                    val_s = "%" + val_s + "%"
                
                val_param = val_s
                
                clause = prefix + _qi(col) + " " + current_op + " ?"
                params.append(val_param)
            
            if not current_group:
                current_group.append(clause)
                continue

            # La UI permette solo AND/OR, ma le condizioni possono anche
            # provenire da un file JSON importato: non interpolare mai altro
            # testo nella query.
            logic = str(cond.get("logic", "AND") or "AND").upper()
            if logic == "OR":
                and_groups.append(current_group)
                current_group = [clause]
            else:
                current_group.append(clause)

        if current_group:
            and_groups.append(current_group)
        if not and_groups:
            return "", params

        group_sql = ["(" + " AND ".join(group) + ")" for group in and_groups]
        where_expr = " OR ".join(group_sql)
        if len(group_sql) > 1:
            where_expr = "(" + where_expr + ")"
        return where_expr, params

    def _build_condition_clause(self, conditions, exclude_conditions=None, alias="", skip_regex=False):
        where_parts = []
        params = []
        include_where, include_params = self._build_where(conditions or [], alias, skip_regex)
        exclude_where, exclude_params = self._build_where(exclude_conditions or [], alias, skip_regex)
        if include_where:
            where_parts.append("(" + include_where + ")")
            params.extend(include_params)
        if exclude_where:
            where_parts.append("NOT (" + exclude_where + ")")
            params.extend(exclude_params)
        return " AND ".join(where_parts), params


    def _build_select(self, display_cols, alias=""):
        if not display_cols: return alias + ".*" if alias else "*"
        prefix = alias + "." if alias else ""
        return ", ".join([prefix + _qi(dc) for dc in display_cols])

    def _condition_columns(self, *condition_groups):
        cols = []
        seen = set()
        for group in condition_groups:
            for cond in group or []:
                col = cond.get("column")
                if col and col not in seen:
                    seen.add(col)
                    cols.append(col)
        return cols

    def _merge_select_columns(self, display_cols, required_cols):
        if not display_cols:
            return []
        merged = list(display_cols)
        for col in required_cols:
            if col and col not in merged:
                merged.append(col)
        return merged

    def _project_result_columns(self, cols, rows, output_cols):
        if not output_cols or cols == output_cols:
            return cols, rows
        if any(col not in cols for col in output_cols):
            return cols, rows
        indexes = [cols.index(col) for col in output_cols]
        projected_rows = [[row[i] for i in indexes] for row in rows]
        return output_cols, projected_rows

    def _describe_conditions(self, conditions):
        """Riepilogo leggibile con gli stessi raggruppamenti della WHERE."""
        groups, current_group = [], []
        for cond in conditions or []:
            col, op, val = cond["column"], cond["operator"], cond.get("value", "")
            part = "[" + col + "] " + op if op in ("IS NULL", "IS NOT NULL") else "[" + col + "] " + op + " " + str(val)
            if not current_group:
                current_group.append(part)
            elif str(cond.get("logic", "AND") or "AND").upper() == "OR":
                groups.append(current_group)
                current_group = [part]
            else:
                current_group.append(part)
        if current_group:
            groups.append(current_group)
        rendered = ["(" + " AND ".join(group) + ")" for group in groups]
        return " OR ".join(rendered)

    def _describe_condition_sets(self, conditions, exclude_conditions=None):
        include_desc = self._describe_conditions(conditions or [])
        exclude_desc = self._describe_conditions(exclude_conditions or [])
        if include_desc and exclude_desc:
            return include_desc + " | ESCLUSI: " + exclude_desc
        return include_desc or ("ESCLUSI: " + exclude_desc if exclude_desc else "")

    def _safe_alias(self, name):
        # Sostituiamo ogni carattere non alfanumerico con _ per un alias SQL valido
        return "t_" + re.sub(r"[^a-zA-Z0-9]", "_", name)

    def _cross_existence(self, c, _cb):
        t1, k1 = c["source_table"], c["key_source"]
        conditions = c.get("conditions", [])
        exclude_conditions = c.get("exclude_conditions", [])
        destinations = c.get("destinations", [])
        dest_logic, display_cols = c.get("dest_logic", "ALMENO_UNA"), c.get("display_columns", [])
        
        # Retrocompatibilità
        if not conditions:
            col, val = c.get("source_column", ""), c.get("source_value", "").strip()
            if val: conditions = [{"column": col, "operator": "=", "value": val, "logic": "AND"}]
            elif col: conditions = [{"column": col, "operator": "IS NOT NULL", "value": "", "logic": "AND"}]
        if not destinations and c.get("target_table"):
            destinations = [{"table": c["target_table"], "key": c.get("key_target", "")}]

        where_str, params = self._build_condition_clause(conditions, exclude_conditions, "s")
        select_str = self._build_select(display_cols, "s")
        if not destinations:
            return self._error(
                "Nessuna tabella destinazione configurata per il controllo "
                "cross-tabella. Aggiungi almeno una destinazione nel builder."
            )
        exists_parts = [f"EXISTS (SELECT 1 FROM {_qi(d['table'])} AS {self._safe_alias(d['table'])} WHERE {self._safe_alias(d['table'])}.{_qi(d['key'])} = s.{_qi(k1)})" for d in destinations]

        if dest_logic == "ALMENO_UNA": combined, desc_prefix = "NOT (" + " OR ".join(exists_parts) + ")", "NON presente in nessuna tra: "
        elif dest_logic == "TUTTE": combined, desc_prefix = "(" + " OR ".join(["NOT " + ep for ep in exists_parts]) + ")", "Mancante da almeno una tra: "
        elif dest_logic == "NESSUNA": combined, desc_prefix = "(" + " OR ".join(exists_parts) + ")", "Presente in almeno una tra: "
        else: combined, desc_prefix = "NOT (" + " OR ".join(exists_parts) + ")", "NON presente in: "

        where_clause = f"({where_str}) AND {combined}" if where_str else combined
        sql = f"SELECT {select_str} FROM {_qi(t1)} AS s WHERE {where_clause}"
        cols, rows = self.db.fetch(sql, params or None)
        desc = self._describe_condition_sets(conditions, exclude_conditions) + " -> " + desc_prefix + ", ".join([d["table"] for d in destinations])
        return self._result(f"Cross: {t1} -> {len(destinations)} tabelle", desc, cols if cols else [k1], rows, t1)

    def _duplicates(self, c, _cb):
        table = c.get("table")
        col = c.get("column")
        if not table or not col:
            return self._error("Parametri mancanti per i duplicati: tabella e colonna sono richiesti.")
        
        key = c.get("key_column", col)
        display_cols, check_phonetic = c.get("display_columns", []), c.get("check_phonetic", False)
        exc = set(e.strip().upper() for e in c.get("exceptions", []) if e.strip())
        conditions = c.get("conditions", [])
        exclude_conditions = c.get("exclude_conditions", [])

        sql = f"SELECT {_qi(key)}, {_qi(col)} FROM {_qi(table)} WHERE {_qi(col)} IS NOT NULL"
        params = []
        if conditions or exclude_conditions:
            extra_where, extra_params = self._build_condition_clause(conditions, exclude_conditions)
            if extra_where:
                sql += " AND " + extra_where
                params.extend(extra_params)
        _, rows = self.db.fetch(sql, params if params else None)
        dupes = SimilarityEngine.find_duplicates([(r[0], r[1]) for r in rows], check_phonetic=check_phonetic)
        if exc: dupes = {k: v for k, v in dupes.items() if k.strip().upper() not in exc}

        if display_cols and dupes:
            # Escludi chiavi None: un IN (?) con None non matcha mai e
            # produrrebbe risultati vuoti nonostante i duplicati esistano.
            dupe_keys = [
                item[0] for items in dupes.values() for item in items
                if item[0] is not None
            ]
            if dupe_keys:
                placeholders = ", ".join(["?" for _ in dupe_keys])
                sql = f"SELECT {self._build_select(display_cols)} FROM {_qi(table)} WHERE {_qi(key)} IN ({placeholders})"
                cols, rows = self.db.fetch(sql, dupe_keys)
                title = ("Duplicati fonetici: " if check_phonetic else "Duplicati esatti: ") + table + "." + col
                return self._result(title, "Sound-Alike" if check_phonetic else "Esatti", cols, rows, table)

        out = sorted([[item[0], item[1], len(items)] for items in dupes.values() for item in items], key=lambda x: str(x[1]).upper())
        title = ("Duplicati fonetici: " if check_phonetic else "Duplicati: ") + table + "." + col
        return self._result(title, "Sound-Alike" if check_phonetic else "Esatti", [key, col, "Occorrenze"], out, table)

    def _similarity(self, c, cb):
        table = c["table"]
        col = c["column"]
        key = c.get("key_column", col)
        thresh, exc, display_cols = c.get("threshold", 80), set(c.get("exceptions", [])), c.get("display_columns", [])
        check_cont, check_prefix, check_phonetic = c.get("check_containment", False), c.get("check_prefix", False), c.get("check_phonetic", False)
        min_prefix = c.get("min_prefix", 3)
        
        sql, params = f"SELECT {_qi(key)}, {_qi(col)} FROM {_qi(table)} WHERE {_qi(col)} IS NOT NULL", []
        conditions = c.get("conditions", [])
        exclude_conditions = c.get("exclude_conditions", [])
        if conditions or exclude_conditions:
            where_str, cond_params = self._build_condition_clause(conditions, exclude_conditions)
            if where_str: sql += " AND (" + where_str + ")"; params.extend(cond_params)

        _, rows = self.db.fetch(sql, params if params else None)
        matches = SimilarityEngine.find_similar([(r[0], r[1]) for r in rows], thresh, exc, cb, check_containment=check_cont, check_prefix=check_prefix, check_phonetic=check_phonetic, min_prefix=min_prefix)

        if display_cols and matches:
            key_list = list(set([m["key1"] for m in matches] + [m["key2"] for m in matches]))
            placeholders = ", ".join(["?" for _ in key_list])
            sql = f"SELECT {_qi(key)}, {self._build_select(display_cols)} FROM {_qi(table)} WHERE {_qi(key)} IN ({placeholders})"
            try:
                _, extra_rows = self.db.fetch(sql, key_list)
                extra_map = {str(r[0]): [r[i+1] for i, dc in enumerate(display_cols) if dc != key and dc != col] for r in extra_rows}
                out = []
                for m in matches:
                    row = [m["key1"], m["val1"]] + extra_map.get(str(m["key1"]), []) + [m["key2"], m["val2"]] + extra_map.get(str(m["key2"]), [])
                    sim_display = str(m["sim"]) + (" [F]" if m.get("phonetic") else (" [P]" if m.get("prefix") else ""))
                    row.append(sim_display); out.append(row)
                
                headers = [key + "_1", col + "_1"] + [dc + "_1" for dc in display_cols if dc != key and dc != col] + [key + "_2", col + "_2"] + [dc + "_2" for dc in display_cols if dc != key and dc != col] + ["Sim%"]
                return self._result(f"Somiglianze: {table}.{col} (>={thresh}%)", f"{len(out)} coppie", headers, out, table)
            except Exception: pass

        out = [[m["key1"], m["val1"], m["key2"], m["val2"], str(m["sim"]) + (" [F]" if m.get("phonetic") else (" [P]" if m.get("prefix") else ""))] for m in matches]
        return self._result(f"Somiglianze: {table}.{col} (>={thresh}%)", f"{len(out)} coppie", [key + "_1", col + "_1", key + "_2", col + "_2", "Sim%"], out, table)

    def _eval_condition_python(self, val_db, operator, val_cond):
        """Valuta una singola condizione lato Python (per filtro client-side)."""
        val_db_s = str(val_db).strip() if val_db is not None else ""
        val_cond_s = str(val_cond).strip()

        if operator == "IS NULL":
            return val_db is None or val_db_s == ""
        elif operator == "IS NOT NULL":
            return val_db is not None and val_db_s != ""
        elif operator in ("REGEXP", "NOT REGEXP"):
            try:
                is_match = bool(re.search(val_cond_s, val_db_s, re.IGNORECASE))
            except Exception:
                is_match = False
            return (not is_match) if operator == "NOT REGEXP" else is_match
        elif operator == "LIKE":
            # Semantica allineata al path SQL (_build_where): %val% = substring,
            # quindi usiamo re.search (non fullmatch). I metacaratteri regex del
            # valore utente devono restare LETTERALI: escape prima, poi solo i
            # wildcard LIKE % e _ (che re.escape NON tocca) diventano regex.
            pattern = re.escape(val_cond_s).replace("%", ".*").replace("_", ".")
            try:
                return bool(re.search(pattern, val_db_s, re.IGNORECASE))
            except Exception:
                return False
        elif operator == "NOT LIKE":
            pattern = re.escape(val_cond_s).replace("%", ".*").replace("_", ".")
            try:
                return not bool(re.search(pattern, val_db_s, re.IGNORECASE))
            except Exception:
                return True
        else:
            # Operatori di confronto: =, <>, >, >=, <, <=
            # Prova confronto numerico, fallback a stringa
            try:
                ndb = float(val_db_s.replace(",", "."))
                ncond = float(val_cond_s.replace(",", "."))
                if operator == "=": return ndb == ncond
                elif operator == "<>": return ndb != ncond
                elif operator == ">": return ndb > ncond
                elif operator == ">=": return ndb >= ncond
                elif operator == "<": return ndb < ncond
                elif operator == "<=": return ndb <= ncond
            except (ValueError, TypeError):
                pass
            # Fallback stringa (case-insensitive)
            db_up = val_db_s.upper()
            cond_up = val_cond_s.upper()
            if operator == "=": return db_up == cond_up
            elif operator == "<>": return db_up != cond_up
            elif operator == ">": return db_up > cond_up
            elif operator == ">=": return db_up >= cond_up
            elif operator == "<": return db_up < cond_up
            elif operator == "<=": return db_up <= cond_up
        return False

    def _apply_conditions_python(self, row, cols, conditions):
        """Valuta un set di condizioni AND/OR su una riga lato Python."""
        # Valuta ogni condizione singolarmente
        results = []
        logics = []
        for c in conditions:
            col_name = c["column"]
            col_idx = cols.index(col_name) if col_name in cols else -1
            val_db = row[col_idx] if col_idx >= 0 else None
            val_cond = c.get("value", "")
            op = c["operator"]
            # Gestione jolly (*) -> LIKE / NOT LIKE
            if "*" in str(val_cond) and op not in ("REGEXP", "NOT REGEXP", "IS NULL", "IS NOT NULL"):
                if op != "NOT LIKE":
                    op = "LIKE"
                val_cond = str(val_cond).replace("*", "%")
            elif op == "LIKE" and "%" not in str(val_cond):
                val_cond = "%" + str(val_cond) + "%"
            elif op == "NOT LIKE" and "%" not in str(val_cond):
                val_cond = "%" + str(val_cond) + "%"
            match = self._eval_condition_python(val_db, op, val_cond)
            results.append(match)
            logics.append(c.get("logic", "AND"))

        if not results:
            return True
        # Stessa precedenza della WHERE SQL: AND prima di OR.
        or_groups = []
        current_group = results[0]
        for i in range(1, len(results)):
            if str(logics[i] or "AND").upper() == "OR":
                or_groups.append(current_group)
                current_group = results[i]
            else:
                current_group = current_group and results[i]
        or_groups.append(current_group)
        return any(or_groups)

    def _row_matches_condition_sets(self, row, cols, conditions=None, exclude_conditions=None):
        include_conditions = conditions or []
        exclusion_conditions = exclude_conditions or []
        if include_conditions and not self._apply_conditions_python(row, cols, include_conditions):
            return False
        if exclusion_conditions and self._apply_conditions_python(row, cols, exclusion_conditions):
            return False
        return True

    def _comparison(self, cond, _cb):
        table = cond.get("table", "")
        conditions = cond.get("conditions", [])
        exclude_conditions = cond.get("exclude_conditions", [])
        display_cols = cond.get("display_columns") or cond.get("columns", [])
        if not table: return self._error("Nessuna tabella selezionata")

        query_cols = self._merge_select_columns(
            display_cols,
            self._condition_columns(conditions, exclude_conditions),
        )
        sel = self._build_select(query_cols or display_cols)

        # Gestione REGEXP: Access non ha supporto nativo.
        # Filtriamo lato Python se presente.
        all_conditions = conditions + exclude_conditions
        has_regex = any(c["operator"] in ("REGEXP", "NOT REGEXP") for c in all_conditions)
        has_or = any(c.get("logic") == "OR" for c in all_conditions)

        if has_regex:
            # Se ci sono OR, dobbiamo scaricare tutto e filtrare interamente in Python
            # Se è solo AND, scarichiamo filtrati dai campi non-regex e raffiniamo
            if has_or:
                # Scarichiamo tutto, filtriamo tutto lato Python
                query = f"SELECT {sel} FROM {_qi(table)}"
                cols, rows = self.db.fetch(query)

                rows = [
                    row for row in rows
                    if self._row_matches_condition_sets(row, cols, conditions, exclude_conditions)
                ]
            else:
                # AND-only: filtra i non-regex via SQL, poi i regex in Python
                where, params = self._build_where(conditions, skip_regex=True)
                query = f"SELECT {sel} FROM {_qi(table)}"
                if where: query += f" WHERE {where}"
                cols, rows = self.db.fetch(query, params)

                rows = [
                    row for row in rows
                    if self._row_matches_condition_sets(row, cols, conditions, exclude_conditions)
                ]
        else:
            where, params = self._build_condition_clause(conditions, exclude_conditions)
            query = f"SELECT {sel} FROM {_qi(table)}"
            if where: query += f" WHERE {where}"
            cols, rows = self.db.fetch(query, params)

        cols, rows = self._project_result_columns(cols, rows, display_cols)

        title = "Ricerca Avanzata"
        desc = f"Tabella: {table} | Filtri: " + self._describe_condition_sets(conditions, exclude_conditions)
        return self._result(title, desc, cols, rows, table)

    # Separatore interno sicuro per chiavi composite (non appare mai nei dati utente)
    _KEY_SEP = "\x00"

    def _concat_sim(self, c, cb):
        # Gestione flessibile parametri (sources vs columns)
        table_main = c.get("table")
        column_list = c.get("columns", [])
        key_main = c.get("key_column")

        sources = c.get("sources", [])
        if not sources and table_main and column_list:
            # Convertiamo il formato piatto del builder in quello strutturato dell'engine
            sources = [{"table": table_main, "column": col, "key_column": key_main} for col in column_list]

        if not sources:
            return self._error("Nessuna colonna o tabella specificata per la ricerca concatenata.")

        sep = self._KEY_SEP
        thresh, exc = c.get("threshold", 80), set(c.get("exceptions", []))
        all_data = []
        conditions = c.get("conditions", [])
        exclude_conditions = c.get("exclude_conditions", [])
        for s in sources:
            t = s["table"]
            col = s["column"]
            key = s.get("key_column", col)
            sql = f"SELECT {_qi(key)}, {_qi(col)} FROM {_qi(t)} WHERE {_qi(col)} IS NOT NULL"
            extra_params = []
            if conditions or exclude_conditions:
                extra_where, extra_params = self._build_condition_clause(conditions, exclude_conditions)
                if extra_where:
                    sql += " AND " + extra_where
            try:
                _, rows = self.db.fetch(sql, extra_params if extra_params else None)
                # Salta record senza chiave: "Tab\x00None" non sarebbe
                # identificabile né mostrabile in modo sensato.
                for r in rows:
                    if r[0] is None:
                        continue
                    all_data.append((f"{t}{sep}{r[0]}", r[1]))
            except Exception as e:
                return self._error(f"Errore caricamento dati per {t}.{col}: {e}")

        matches = SimilarityEngine.find_similar(all_data, thresh, exc, cb, check_phonetic=c.get("check_phonetic", False))
        out = []
        for m in matches:
            p1, p2 = m["key1"].split(sep, 1), m["key2"].split(sep, 1)
            sim = str(m["sim"]) + (" [F]" if m.get("phonetic") else (" [P]" if m.get("prefix") else ""))
            out.append([p1[0], p1[1], m["val1"], p2[0], p2[1], m["val2"], sim])
        return self._result(f"ConcatSim (>={thresh}%)", f"{len(out)} coppie", ["Tab1", "Key1", "Val1", "Tab2", "Key2", "Val2", "Sim%"], out, sources[0]["table"] if sources else "")

    def _formula(self, c, _cb):
        table = c.get("table") or (c.get("tables", [""])[0] if c.get("tables") else "")
        display_cols = c.get("display_columns") or c.get("columns", [])
        formula = c.get("formula", "").strip()
        if not table or not formula:
            return self._error("Tabella o Formula mancante.")

        # Esclusioni: i record che soddisfano queste condizioni NON vengono
        # segnalati. Si traducono in "AND NOT (...)" sulla WHERE della formula.
        where = f"({formula})"
        params = []
        exclude_conditions = c.get("exclude_conditions", [])
        if exclude_conditions:
            excl_clause, excl_params = self._build_condition_clause([], exclude_conditions)
            if excl_clause:
                where += " AND " + excl_clause
                params.extend(excl_params)

        sql = f"SELECT {self._build_select(display_cols)} FROM {_qi(table)} WHERE {where}"
        try:
            cols, rows = self.db.fetch(sql, params if params else None)
            desc = f"WHERE {formula}"
            if exclude_conditions:
                desc += " | escl: " + self._describe_conditions(exclude_conditions)
            return self._result(f"Formula: {table}", desc, cols, rows, table)
        except Exception as e:
            msg = f"Errore nella formula SQL: {e}\n\nQuery: {sql}"
            logger.error(msg)
            return self._error(msg)

    def _linked_intersection(self, c, _cb):
        """Trova record in Tab1 (con filtri) che hanno riscontro in Tab2 (con filtri)."""
        t1 = c.get("table")
        k1 = c.get("link_key_src")
        t2 = c.get("dest_table")
        k2 = c.get("link_key_dest") or k1
        conds1 = c.get("conditions", [])
        excl_conds1 = c.get("exclude_conditions", [])
        conds2 = c.get("dest_conditions", [])
        excl_conds2 = c.get("exclude_dest_conditions", [])
        display_cols = c.get("display_columns") or c.get("columns", [])

        if not t1 or not t2: return self._error("Selezionare entrambe le tabelle.")
        if not k1: return self._error("Specificare la chiave di collegamento per la Tabella 1.")

        # Alias sicuri per evitare ambiguità e gestire nomi tabella con caratteri speciali
        a1, a2 = "t1", "t2"
        
        where1, params1 = self._build_condition_clause(conds1, excl_conds1, alias=a1)
        where2, params2 = self._build_condition_clause(conds2, excl_conds2, alias=a2)
        
        sel = self._build_select(display_cols, alias=a1)
        
        # Costruzione query con alias espliciti
        sql = f"SELECT {sel} FROM {_qi(t1)} AS {a1} WHERE "
        
        # Filtri tabella principale
        where_parts = []
        if where1:
            where_parts.append(f"({where1})")
        
        # Subquery con collegamento su chiavi
        # t2.[k2] = t1.[k1]
        sub_sql = f"EXISTS (SELECT 1 FROM {_qi(t2)} AS {a2} WHERE {a2}.{_qi(k2)} = {a1}.{_qi(k1)}"
        if where2:
            sub_sql += f" AND ({where2})"
        sub_sql += ")"

        where_parts.append(sub_sql)
        sql += " AND ".join(where_parts)
        
        params = params1 + params2
        
        # Log dettagliato per debug errori SQL
        logger.info(f"Eseguo Intersezione: {sql} | Parametri: {params}")
        
        try:
            cols, rows = self.db.fetch(sql, params)
            title = f"Intersezione: {t1} ↔ {t2}"
            desc = (
                f"Tab1: {self._describe_condition_sets(conds1, excl_conds1)} | "
                f"Join: {k1}={k2} | "
                f"Tab2: {self._describe_condition_sets(conds2, excl_conds2)}"
            )
            return self._result(title, desc, cols, rows, t1)
        except Exception as e:
            # Arricchiamo l'errore con la query incriminata per facilitare la diagnosi lato utente
            msg = f"{str(e)}\n\nQuery: {sql}"
            logger.error(f"Errore SQL Intersezione: {msg}")
            return self._error(msg)
            
    def _daily_coverage(self, c, _cb):
        import datetime
        t1 = c.get("table")
        col_day = c.get("day_column")
        expected_count = int(c.get("expected_count", 7))
        start_date_str = c.get("start_date", "").strip()
        
        conds = c.get("conditions", [])
        excl_conds = c.get("exclude_conditions", [])
        
        if not t1 or not col_day:
            return self._error("Tabella e Colonna Giorno richieste.")
            
        where, params = self._build_condition_clause(conds, excl_conds)
        sql = f"SELECT DISTINCT {_qi(col_day)} FROM {_qi(t1)} WHERE {_qi(col_day)} IS NOT NULL"
        if where:
            sql += f" AND {where}"
            
        try:
            _, rows = self.db.fetch(sql, params if params else None)
            found_dates = set()
            for r in rows:
                val = r[0]
                if isinstance(val, datetime.datetime):
                    found_dates.add(val.date())
                else:
                    parsed_date = None
                    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
                        try:
                            parsed_date = datetime.datetime.strptime(str(val).split(" ")[0], fmt).date()
                            break
                        except (ValueError, TypeError):
                            continue
                    if parsed_date is not None:
                        found_dates.add(parsed_date)
                    else:
                        # Valore data non riconoscibile: NON aggiungerlo come
                        # stringa, altrimenti il confronto con i date attesi
                        # fallirebbe sempre generando "giorni mancanti" fittizi.
                        logger.warning(
                            "daily_coverage: valore giorno non riconosciuto in [%s].[%s]: %r",
                            t1, col_day, val,
                        )
        except Exception as e:
            return self._error(f"Errore SQL: {e}")
            
        out_rows = []
        if start_date_str:
            try:
                start_dt = datetime.datetime.strptime(start_date_str, "%d/%m/%Y").date()
                expected_dates = [start_dt + datetime.timedelta(days=i) for i in range(expected_count)]
                missing_days = [d.strftime("%d/%m/%Y") for d in expected_dates if d not in found_dates]
            except Exception as e:
                return self._error(f"Errore parsing Data Inizio '{start_date_str}'. Formato atteso gg/mm/aaaa.")
        else:
            missing_days = []
            if len(found_dates) < expected_count:
                missing_days = [f"Solo {len(found_dates)} giorni presenti su {expected_count} attesi"]

        mese_vals = [cond.get("value", "") for cond in conds if cond.get("column") == c.get("month_column")]
        sett_vals = [cond.get("value", "") for cond in conds if cond.get("column") == c.get("week_column")]
        mese = mese_vals[-1] if mese_vals else ""
        sett = sett_vals[-1] if sett_vals else ""

        for md in missing_days:
            row = [md]
            if mese: row.append(mese)
            if sett: row.append(sett)
            out_rows.append(row)
            
        cols = ["Giorno Mancante / Avviso"]
        if c.get("month_column"): cols.append("Mese")
        if c.get("week_column"): cols.append("Settimana")
        
        desc = self._describe_condition_sets(conds, excl_conds)
        return self._result(f"Copertura Mancante ({len(out_rows)} eventi)", desc, cols, out_rows, t1)
        
    def _mandatory_record_check(self, c, _cb):
        t1 = c.get("table")
        conds1 = c.get("conditions", [])
        excl_conds1 = c.get("exclude_conditions", [])
        
        t2 = c.get("dest_table")
        conds2 = c.get("dest_conditions", [])
        excl_conds2 = c.get("exclude_dest_conditions", [])
        k1 = c.get("link_key_src")
        k2 = c.get("link_key_dest") or k1
        
        if not t1: return self._error("Tabella sorgente mancante.")
        
        a1, a2 = "t1", "t2"
        where1, params1 = self._build_condition_clause(conds1, excl_conds1, alias=a1)
        
        # We only need to check if AT LEAST ONE record exists.
        sql = f"SELECT TOP 1 1 FROM {_qi(t1)} AS {a1}"
        where_parts = []
        if where1:
            where_parts.append(f"({where1})")
            
        params = list(params1)
            
        if t2:
            if not k1: return self._error("Chiave di collegamento src mancante per la destinazione.")
            where2, params2 = self._build_condition_clause(conds2, excl_conds2, alias=a2)
            sub_sql = f"EXISTS (SELECT 1 FROM {_qi(t2)} AS {a2} WHERE {a2}.{_qi(k2)} = {a1}.{_qi(k1)}"
            if where2:
                sub_sql += f" AND ({where2})"
            sub_sql += ")"
            where_parts.append(sub_sql)
            params.extend(params2)
            
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)
            
        try:
            _, rows = self.db.fetch(sql, params)
            if len(rows) == 0:
                # Requisito NON soddisfatto > mostro un alert
                msg = "Requisito settimanale obbligatorio NON soddisfatto! Nessun record trovato corrispondente ai parametri."
                return self._result("REQUISITO MANCANTE", self._describe_condition_sets(conds1, excl_conds1), ["Alert", "Dettaglio"], [["Mancanza Rilevata", msg]], t1)
            else:
                # Requisito soddisfatto > array vuoto
                # Return empty correctly.
                return self._result("Requisito OK", "Il record obbligatorio è presente.", ["Stato"], [], t1)
                
        except Exception as e:
            return self._error(f"Errore SQL: {str(e)}\n\nQuery: {sql}")

    # ------------------------------------------------------------------ #
    #  CONTROLLI AVANZATI v5                                                #
    # ------------------------------------------------------------------ #

    def _dependent_condition(self, c, _cb):
        """Controllo SE...ALLORA: segnala le righe dove l'antecedente è vero
        ma il conseguente è falso (= violazione della regola workflow)."""
        table = c.get("table", "")
        antecedent = c.get("antecedent", [])
        consequent = c.get("consequent", [])
        display_cols = c.get("display_columns") or c.get("columns", [])

        if not table:
            return self._error("Nessuna tabella selezionata.")
        if not antecedent:
            return self._error("Definire almeno una condizione SE (antecedente).")
        if not consequent:
            return self._error("Definire almeno una condizione ALLORA (conseguente).")

        query_cols = self._merge_select_columns(
            display_cols,
            self._condition_columns(antecedent, consequent),
        )
        sel = self._build_select(query_cols or display_cols)

        all_conds = antecedent + consequent
        has_regex = any(c2["operator"] in ("REGEXP", "NOT REGEXP") for c2 in all_conds)

        if has_regex:
            # Fallback Python completo
            query = f"SELECT {sel} FROM {_qi(table)}"
            cols, rows = self.db.fetch(query)
            out = []
            for row in rows:
                ante_ok = self._apply_conditions_python(row, cols, antecedent)
                cons_ok = self._apply_conditions_python(row, cols, consequent)
                if ante_ok and not cons_ok:
                    out.append(row)
        else:
            ante_where, ante_params = self._build_where(antecedent)
            cons_where, cons_params = self._build_where(consequent)
            # Violazione = ante_ok AND NOT cons_ok
            where = f"({ante_where}) AND NOT ({cons_where})"
            query = f"SELECT {sel} FROM {_qi(table)} WHERE {where}"
            params = ante_params + cons_params
            cols, out = self.db.fetch(query, params)

        cols, out = self._project_result_columns(cols, out, display_cols)

        se_desc = self._describe_conditions(antecedent)
        allora_desc = self._describe_conditions(consequent)
        desc = f"SE [{se_desc}] ALLORA [{allora_desc}]"
        return self._result(f"SE...ALLORA: {table}", desc, cols if cols else display_cols, out, table)

    def _row_cross_column(self, c, _cb):
        """Confronta due colonne della stessa riga e segnala le violazioni.
        Esempio: DataScadenza DEVE essere >= DataRegistrazione."""
        table = c.get("table", "")
        left_col = c.get("left_column", "")
        operator = c.get("operator", ">=")
        right_col = c.get("right_column", "")
        ignore_nulls = c.get("ignore_nulls", True)
        display_cols = c.get("display_columns") or c.get("columns", [])
        conditions = c.get("conditions", [])
        exclude_conditions = c.get("exclude_conditions", [])

        if not table or not left_col or not right_col:
            return self._error("Tabella, Colonna Sinistra e Colonna Destra sono obbligatorie.")

        valid_ops = {"=", "<>", ">", ">=", "<", "<="}
        if operator not in valid_ops:
            return self._error(f"Operatore non valido: {operator}. Usa uno tra: {', '.join(valid_ops)}")

        sel = self._build_select(display_cols)

        # Costruzione WHERE: segnala le righe che VIOLANO la regola
        # Violazione = NOT (left OP right)
        negation = {"=": "<>", "<>": "=", ">": "<=", ">=": "<", "<": ">=", "<=": ">"}
        neg_op = negation[operator]

        where_parts = []
        params = []

        if ignore_nulls:
            where_parts.append(f"{_qi(left_col)} IS NOT NULL AND {_qi(right_col)} IS NOT NULL")

        where_parts.append(f"{_qi(left_col)} {neg_op} {_qi(right_col)}")

        extra_where, extra_params = self._build_condition_clause(conditions, exclude_conditions)
        if extra_where:
            where_parts.append(extra_where)
            params.extend(extra_params)

        where = " AND ".join(f"({p})" for p in where_parts)
        query = f"SELECT {sel} FROM {_qi(table)} WHERE {where}"

        try:
            cols, rows = self.db.fetch(query, params if params else None)
        except Exception as e:
            return self._error(f"Errore SQL: {e}\n\nQuery: {query}")

        desc = f"Violazione: [{left_col}] {operator} [{right_col}]"
        if conditions or exclude_conditions:
            desc += " | " + self._describe_condition_sets(conditions, exclude_conditions)
        return self._result(f"Coerenza colonne: {table}", desc, cols if cols else display_cols, rows, table)

    def _lookup_validation(self, c, _cb):
        """Trova i record dove il valore di una colonna NON appartiene
        al dizionario di valori ammessi. Suggerisce il valore più simile."""
        table = c.get("table", "")
        column = c.get("column", "")
        allowed_values = c.get("allowed_values", [])
        case_insensitive = c.get("case_insensitive", True)
        trim = c.get("trim", True)
        ignore_empty = c.get("ignore_empty", True)
        suggest_similar = c.get("suggest_similar", True)
        sim_threshold = c.get("similarity_threshold", 60)
        display_cols = c.get("display_columns") or c.get("columns", [])
        conditions = c.get("conditions", [])
        exclude_conditions = c.get("exclude_conditions", [])

        if not table or not column:
            return self._error("Tabella e Colonna sono obbligatorie.")
        if not allowed_values:
            return self._error("Specificare almeno un valore ammesso nel dizionario.")

        # Costruisci il set di lookup normalizzato
        def normalize(v):
            s = str(v)
            if trim: s = s.strip()
            if case_insensitive: s = s.upper()
            return s

        allowed_set = {normalize(v) for v in allowed_values}

        # Carica colonne da mostrare (include sempre la colonna controllata)
        all_display = list(display_cols) if display_cols else []
        if column not in all_display:
            all_display = [column] + all_display

        sel = self._build_select(all_display)
        query = f"SELECT {sel} FROM {_qi(table)}"

        where_parts = []
        params = []
        if ignore_empty:
            where_parts.append(f"{_qi(column)} IS NOT NULL")
        extra_where, extra_params = self._build_condition_clause(conditions, exclude_conditions)
        if extra_where:
            where_parts.append(extra_where)
            params.extend(extra_params)
        if where_parts:
            query += " WHERE " + " AND ".join(f"({p})" for p in where_parts)

        try:
            cols, rows = self.db.fetch(query, params if params else None)
        except Exception as e:
            return self._error(f"Errore SQL: {e}\n\nQuery: {query}")

        col_idx = cols.index(column) if column in cols else 0

        out = []
        for row in rows:
            raw_val = row[col_idx]
            if raw_val is None:
                continue
            norm_val = normalize(raw_val)
            if ignore_empty and norm_val == "":
                continue
            if norm_val in allowed_set:
                continue  # Valore valido, non segnalare

            # Valore non nel dizionario: calcola suggerimento
            suggestion = ""
            best_sim = 0.0
            if suggest_similar:
                for av in allowed_values:
                    s = SimilarityEngine.ratio(norm_val, normalize(av))
                    if s > best_sim:
                        best_sim = s
                        suggestion = av
                if best_sim < sim_threshold:
                    suggestion = "(nessun suggerimento)"
                    best_sim = 0.0

            if suggest_similar:
                out.append(list(row) + [suggestion, f"{best_sim:.1f}%"])
            else:
                out.append(list(row))

        if suggest_similar:
            result_cols = cols + ["Suggerimento", "Similarità"]
        else:
            result_cols = cols

        allowed_preview = ", ".join(str(v) for v in allowed_values[:5])
        if len(allowed_values) > 5:
            allowed_preview += f"... (+{len(allowed_values)-5})"
        desc = f"[{column}] non in dizionario: [{allowed_preview}]"
        return self._result(f"Lookup: {table}.{column}", desc, result_cols, out, table)

    def _aggregate_threshold(self, c, _cb):
        """Raggruppa per le colonne specificate, applica una funzione aggregata
        e segnala i gruppi che superano (o violano) la soglia impostata."""
        table = c.get("table", "")
        group_by = c.get("group_by", [])
        agg_function = c.get("agg_function", "SUM").upper()
        agg_column = c.get("agg_column", "")
        operator = c.get("operator", ">")
        threshold = c.get("threshold", 0)
        conditions = c.get("conditions", [])
        exclude_conditions = c.get("exclude_conditions", [])

        if not table:
            return self._error("Nessuna tabella selezionata.")
        if not group_by:
            return self._error("Specificare almeno una colonna per il raggruppamento.")
        if agg_function not in ("SUM", "COUNT", "AVG", "MIN", "MAX"):
            return self._error(f"Funzione aggregata non valida: {agg_function}")
        if agg_function != "COUNT" and not agg_column:
            return self._error("Specificare la colonna da aggregare (richiesta per SUM/AVG/MIN/MAX).")

        valid_ops = {"=", "<>", ">", ">=", "<", "<="}
        is_range = str(operator).strip().lower() in ("tra", "between")
        if not is_range and operator not in valid_ops:
            return self._error(f"Operatore non valido: {operator}")

        # Costruzione SELECT
        group_cols_sql = ", ".join(_qi(g) for g in group_by)
        if agg_function == "COUNT":
            agg_expr = "COUNT(*)"
        else:
            agg_expr = f"{agg_function}({_qi(agg_column)})"

        sel = f"{group_cols_sql}, {agg_expr} AS AggVal"

        # WHERE (pre-filtri)
        where_str, params = self._build_condition_clause(conditions, exclude_conditions)
        query = f"SELECT {sel} FROM {_qi(table)}"
        if where_str:
            query += f" WHERE {where_str}"

        if is_range:
            low = threshold
            high = c.get("threshold_max", threshold)
            try:
                if float(high) < float(low):
                    low, high = high, low
            except (TypeError, ValueError):
                pass
            query += f" GROUP BY {group_cols_sql} HAVING {agg_expr} BETWEEN ? AND ?"
            params.extend([low, high])
            having_desc = f"{agg_function}({agg_column or '*'}) tra {low} e {high}"
        else:
            query += f" GROUP BY {group_cols_sql} HAVING {agg_expr} {operator} ?"
            params.append(threshold)
            having_desc = f"{agg_function}({agg_column or '*'}) {operator} {threshold}"

        try:
            cols, rows = self.db.fetch(query, params)
        except Exception as e:
            return self._error(f"Errore SQL: {e}\n\nQuery: {query}")

        result_cols = list(group_by) + [f"{agg_function}({agg_column or '*'})"]
        desc = (
            f"Raggruppa per [{', '.join(group_by)}] | {having_desc}"
        )
        if conditions or exclude_conditions:
            desc += " | " + self._describe_condition_sets(conditions, exclude_conditions)
        return self._result(f"Soglia aggregata: {table}", desc, result_cols, rows, table)

    def _aggregate_multi_table(self, c, _cb):
        """Somma (o aggrega) un valore per gruppo unendo PIU' tabelle dello stesso
        database, anche con nomi colonna diversi. Ogni sorgente mappa la propria
        colonna gruppo e valore, normalizzate via alias; i filtri (WHERE) sono
        globali (stessi nomi colonna in tutte le tabelle) e applicati a ciascuna
        sorgente. Confronto finale con soglia singola o intervallo ('tra')."""
        sources = c.get("sources", [])
        agg_function = c.get("agg_function", "SUM").upper()
        operator = c.get("operator", ">")
        threshold = c.get("threshold", 0)
        conditions = c.get("conditions", [])
        exclude_conditions = c.get("exclude_conditions", [])

        if not sources:
            return self._error("Specificare almeno una tabella sorgente.")
        if agg_function not in ("SUM", "COUNT", "AVG", "MIN", "MAX"):
            return self._error(f"Funzione aggregata non valida: {agg_function}")
        is_count = agg_function == "COUNT"
        for s in sources:
            if not s.get("table") or not s.get("group_col"):
                return self._error("Ogni sorgente richiede tabella e colonna gruppo.")
            if not is_count and not s.get("value_col"):
                return self._error("Ogni sorgente richiede la colonna valore (per SUM/AVG/MIN/MAX).")

        # Filtri globali: stessi nomi colonna in tutte le tabelle -> stessa clausola
        where_str, where_params = self._build_condition_clause(conditions, exclude_conditions)

        subs, params = [], []
        for s in sources:
            if is_count:
                sub = f"SELECT {_qi(s['group_col'])} AS grp FROM {_qi(s['table'])}"
            else:
                sub = f"SELECT {_qi(s['group_col'])} AS grp, {_qi(s['value_col'])} AS val FROM {_qi(s['table'])}"
            if where_str:
                sub += f" WHERE {where_str}"
                params.extend(where_params)
            subs.append(sub)

        union = " UNION ALL ".join(subs)
        agg_expr = "COUNT(*)" if is_count else f"{agg_function}(val)"
        query = f"SELECT grp, {agg_expr} AS AggVal FROM ({union}) AS u GROUP BY grp"

        is_range = str(operator).strip().lower() in ("tra", "between")
        if is_range:
            low = threshold
            high = c.get("threshold_max", threshold)
            try:
                if float(high) < float(low):
                    low, high = high, low
            except (TypeError, ValueError):
                pass
            query += f" HAVING {agg_expr} BETWEEN ? AND ?"
            params.extend([low, high])
            having_desc = f"{agg_function} tra {low} e {high}"
        else:
            valid_ops = {"=", "<>", ">", ">=", "<", "<="}
            if operator not in valid_ops:
                return self._error(f"Operatore non valido: {operator}")
            query += f" HAVING {agg_expr} {operator} ?"
            params.append(threshold)
            having_desc = f"{agg_function} {operator} {threshold}"

        try:
            cols, rows = self.db.fetch(query, params)
        except Exception as e:
            return self._error(f"Errore SQL: {e}\n\nQuery: {query}")

        group_label = sources[0].get("group_col", "Gruppo")
        result_cols = [group_label, f"{agg_function}({'*' if is_count else 'valore'})"]
        tables_desc = ", ".join(s.get("table", "") for s in sources)
        desc = f"Somma multi-tabella [{tables_desc}] | {having_desc}"
        if conditions or exclude_conditions:
            desc += " | " + self._describe_condition_sets(conditions, exclude_conditions)
        return self._result("Soglia aggregata multi-tabella", desc, result_cols, rows,
                            sources[0].get("table", ""))
