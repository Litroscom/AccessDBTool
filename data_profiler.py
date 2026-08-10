# -*- coding: utf-8 -*-
import re
from itertools import combinations

class DataProfiler:
    """
    Analizza i dati e la struttura di un database Access per suggerire
    controlli di validita (duplicati, somiglianze, check incrociati).
    """
    def __init__(self, db_manager):
        self.db = db_manager
        
        # Dizionario di regole per il Data Sampling e Name Matching
        self.RULES = {
            "diffusore_univoco": {
                "regex": None,
                "hints": ["diffusor"],
                "suggestion_type": "similarity_check",
                "title": "Controllo Errori Diffusori (Similarità)",
                "desc": "Trovata colonna Diffusori. Essendo nomi univoci, è utile cercare refusi, errori di battitura o omonimie sfuggite ai normali controlli.",
                "config_template": {"type": "similarity_check", "threshold": 85, "check_phonetic": True, "check_prefix": True}
            },
            "telefono": {
                "regex": r"^\+?\d{8,15}$", 
                "hints": ["telefono", "cellulare", "mobile"],
                "suggestion_type": "duplicate_check", 
                "title": "Controllo Doppioni Numeri di Telefono",
                "desc": "Trovata colonna Telefoni. Vuoi cercare numerazioni esatte duplicate?",
                "config_template": {"type": "duplicate_check", "check_phonetic": False}
            }
        }

    def analyze(self):
        """Scansiona tabelle e genera suggerimenti automatici, restituisce lista di dizionari (insights)."""
        suggestions = []
        if not self.db or not self.db.connected:
            return suggestions
            
        # 1. Analisi delle singole colonne per Tipo Dato (Fuzzy / Duplicati)
        _TEXT_TYPES = {
            "str", "varchar", "nvarchar", "text", "memo", "longtext",
            "ntext", "char", "nchar", "longchar", "tinytext", "mediumtext",
            "wchar", "varchar2", "character varying",
        }

        def _is_text_type(t):
            # Normalizza (minuscole, senza eventuale lunghezza "VarChar(255)")
            # e confronta in modo case-insensitive: prima il match case-sensitive
            # su 'Text'/'VarChar' ecc. falliva e ignorava quasi tutte le colonne
            # testo riportate dai driver ODBC.
            base = str(t or "").split("(")[0].strip().lower()
            return base in _TEXT_TYPES

        for table, columns in self.db.table_columns.items():
            text_cols = [c['name'] for c in columns if _is_text_type(c['type'])]
            
            for col in text_cols:
                # Esegui campionamento
                sample_data = self._get_sample(table, col, limit=50)
                matched_rule = None
                
                # Check RegEx sui dati campionati
                for rule_name, rule_def in self.RULES.items():
                    if rule_def["regex"] and sample_data:
                        pattern = re.compile(rule_def["regex"])
                        matches = sum(1 for val in sample_data if pattern.match(str(val).strip()))
                        if len(sample_data) > 0 and (matches / len(sample_data)) >= 0.8: # 80% dei dati matcha la regex
                            matched_rule = rule_name
                            break
                            
                # Se la RegEx non ha prodotto risultati, tenta con l'euristica sul nome colonna
                if not matched_rule:
                    col_lower = col.lower()
                    for rule_name, rule_def in self.RULES.items():
                        if any(hint in col_lower for hint in rule_def["hints"]):
                            matched_rule = rule_name
                            break
                
                # Genera il suggerimento se una regola ha matchato
                if matched_rule:
                    rule = self.RULES[matched_rule]
                    cfg = rule["config_template"].copy()
                    cfg["name"] = f"Auto: {rule['title']} in {table}.{col}"
                    cfg["table"] = table
                    cfg["column"] = col
                    cfg["key_column"] = self._guess_primary_key(columns) or col
                    
                    suggestions.append({
                        "title": f"{rule['title']} ({table})",
                        "desc": rule["desc"],
                        "action": rule["suggestion_type"],
                        "config": cfg,
                        "table": table,
                        "column": col
                    })

        # 2. Ricerca Relazioni Cross-Tabella (es. ID in comune, IDdiff)
        cross_suggestions = self._find_cross_table_links()
        suggestions.extend(cross_suggestions)
        
        # 3. Regole di Business Specifiche dell'Utente
        custom_suggestions = self._find_custom_business_rules()
        suggestions.extend(custom_suggestions)

        return suggestions

    def _get_sample(self, table, column, limit=50):
        """Estrae un campione di dati non nulli da una tabella."""
        try:
            qi = self.db._qi
            sql = f"SELECT TOP {limit} {qi(column)} FROM {qi(table)} WHERE {qi(column)} IS NOT NULL AND {qi(column)} <> ''"
            _, rows = self.db.fetch(sql)
            return [r[0] for r in rows if r[0] is not None]
        except Exception:
            return []

    def _guess_primary_key(self, columns):
        """Tenta di indovinare la chiave primaria di una tabella basandosi sui nomi."""
        col_names = [c["name"] for c in columns]
        # Tentativo 1: Esattamente 'ID'
        for c in col_names:
            if c.upper() == 'ID': return c
        # Tentativo 2: Contiene 'ID' all'inizio
        for c in col_names:
            if c.upper().startswith('ID'): return c
        # Nessuna trovata chiaramente
        return None

    def _find_cross_table_links(self):
        """Cerca colonne 'ID' simili tra le tabelle per suggerire check di orfanità."""
        suggestions = []
        tables = list(self.db.table_columns.keys())
        
        for t1, t2 in combinations(tables, 2):
            cols1 = {c["name"].upper(): c["name"] for c in self.db.table_columns[t1]}
            cols2 = {c["name"].upper(): c["name"] for c in self.db.table_columns[t2]}
            
            # Cerca colonne con lo stesso nome che 'sembrino' chiavi esterne (ID_Cliente, IDdiff, etc)
            common = set(cols1.keys()).intersection(set(cols2.keys()))
            for col_upper in common:
                # Escludiamo "ID" generico che quasi tutte le tabelle Access hanno come PK autoincrementante
                if col_upper not in ('ID', 'ID_UNICO', 'INDEX') and ('ID' in col_upper or 'COD' in col_upper or 'DIFFUSOR' in col_upper):
                    k1 = cols1[col_upper]
                    k2 = cols2[col_upper]
                    
                    # Genera suggerimento: Trovata relazione, vuoi controllare se ci sono record in t1 mancant in t2?
                    cfg1 = {
                        "type": "cross_table_existence",
                        "name": f"Auto: Coerenza {k1} tra {t1} e {t2}",
                        "source_table": t1,
                        "key_source": k1,
                        "conditions": [{"column": k1, "operator": "IS NOT NULL", "value": "", "logic": "AND"}],
                        "destinations": [{"table": t2, "key": k2}],
                        "dest_logic": "NESSUNA"
                    }
                    suggestions.append({
                        "title": f"Incrocio Tabelle: {t1} ↔ {t2}",
                        "desc": f"La colonna [{k1}] è presente in entrambe le tabelle. Vuoi controllare se esistono record in {t1} orfani di corrispondenze in {t2}?",
                        "action": "cross_table_existence",
                        "config": cfg1,
                        "table": t1,
                        "column": k1
                    })
                    break # Fai solo un suggerimento per coppia di tabelle
                    
        return suggestions

    def _find_custom_business_rules(self):
        """Implementa le 5 regole di business altamente specifiche richieste dall'utente."""
        suggestions = []
        tables = list(self.db.table_columns.keys())
        
        # Helper per cercare il nome esatto/simile di una tabella
        def get_table(hints):
            for t in tables:
                t_lower = t.lower()
                if any(h in t_lower for h in hints):
                    return t
            return None
            
        def has_columns(table, col_hints):
            if not table: return False
            col_names = [c["name"].lower() for c in self.db.table_columns[table]]
            for hint in col_hints:
                if not any(hint in c for c in col_names):
                    return False
            return True
            
        def get_real_col(table, hint):
            col_names = [c["name"] for c in self.db.table_columns[table]]
            for c in col_names:
                if hint in c.lower():
                    return c
            return None

        # Identifica le tabelle
        t_diff = get_table(["diffusor"])
        if not t_diff: return [] # Senza la tabella principale non possiamo fare nulla
        
        key_diff = self._guess_primary_key(self.db.table_columns[t_diff]) or get_real_col(t_diff, "diffusor")
        if not key_diff: return []

        t_cq = get_table(["casa", "quartiere", "cq"])
        t_vol = get_table(["volontariato"])
        t_fab = get_table(["fabbrica"])
        t_inv = get_table(["invito", "tel"])
        
        import datetime
        mesi = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
        mese_corrente = mesi[datetime.datetime.now().month - 1]

        # Regola 1: Naanno=25/26 e namese=mese_corrente -> almeno un'iniziativa in casa-quartiere
        if has_columns(t_diff, ["naanno", "namese"]) and t_cq:
            c_naanno = get_real_col(t_diff, "naanno")
            c_namese = get_real_col(t_diff, "namese")
            key_cq = self._guess_primary_key(self.db.table_columns[t_cq]) or key_diff
            
            cfg = {
                "type": "cross_table_existence",
                "name": f"CQ Assente per {mese_corrente} (Naanno)",
                "source_table": t_diff,
                "key_source": key_diff,
                "conditions": [
                    {"column": c_naanno, "operator": "=", "value": "25/26", "logic": "AND"},
                    {"column": c_namese, "operator": "=", "value": mese_corrente, "logic": "AND"}
                ],
                "destinations": [{"table": t_cq, "key": key_cq}],
                "dest_logic": "TUTTE" # Vogliamo trovare chi Manca (orfani), quindi chi NON e in questa destinazione
            }
            suggestions.append({
                "title": "Controllo Iniziative: Casa-Quartiere (Mese corrente)",
                "desc": f"Cerca i diffusori con {c_naanno}='25/26' e {c_namese}='{mese_corrente}' che però NON hanno alcuna iniziativa nella tabella '{t_cq}'.",
                "action": "cross_table_existence",
                "config": cfg,
                "table": t_diff, "column": c_naanno
            })

        # Regola 2: NaannoTot=25/26 e nameseTot=mese_corrente -> almeno un'iniziativa tra cq, vol, fab, inv
        if has_columns(t_diff, ["naannotot", "namesetot"]):
            dests = []
            if t_cq: dests.append({"table": t_cq, "key": self._guess_primary_key(self.db.table_columns[t_cq]) or key_diff})
            if t_vol: dests.append({"table": t_vol, "key": self._guess_primary_key(self.db.table_columns[t_vol]) or key_diff})
            if t_fab: dests.append({"table": t_fab, "key": self._guess_primary_key(self.db.table_columns[t_fab]) or key_diff})
            if t_inv: dests.append({"table": t_inv, "key": self._guess_primary_key(self.db.table_columns[t_inv]) or key_diff})
            
            if dests:
                c_naannotot = get_real_col(t_diff, "naannotot")
                c_namesetot = get_real_col(t_diff, "namesetot")
                
                cfg = {
                    "type": "cross_table_existence",
                    "name": f"Iniziativa Assente per {mese_corrente} (NaannoTot)",
                    "source_table": t_diff,
                    "key_source": key_diff,
                    "conditions": [
                        {"column": c_naannotot, "operator": "=", "value": "25/26", "logic": "AND"},
                        {"column": c_namesetot, "operator": "=", "value": mese_corrente, "logic": "AND"}
                    ],
                    "destinations": dests,
                    "dest_logic": "TUTTE" # Troviamo chi NON E in ALMENO UNA, cioe in NESSUNA (mancante da tutte)
                }
                suggestions.append({
                    "title": "Controllo Iniziative Totali (Mese corrente)",
                    "desc": f"Cerca i diffusori con {c_naannotot}='25/26' e {c_namesetot}='{mese_corrente}' che NON sono presenti in NESSUNA delle tabelle iniziative (" + ", ".join([d["table"] for d in dests]) + ").",
                    "action": "cross_table_existence",
                    "config": cfg,
                    "table": t_diff, "column": c_naannotot
                })

        # Regola 3: Coerenza cellula e struttura (Gv/Gcq)
        if has_columns(t_diff, ["cellula", "struttura"]):
            c_cell = get_real_col(t_diff, "cellula")
            c_strut = get_real_col(t_diff, "struttura")
            
            # Qui servirebbe una formula custom o due check value_comparison separati.
            # Facciamo una formula_condition che cattura le incongruenze
            formula = f"([{c_cell}] LIKE '*Gv*' AND [{c_strut}] <> '2') OR (([{c_cell}] LIKE '*Gcq*' OR [{c_cell}] LIKE '*Gq*') AND [{c_strut}] <> '1')"
            
            cfg = {
                "type": "formula_condition",
                "name": "Incoerenza Cellula/Struttura",
                "table": t_diff,
                "formula": formula,
            }
            suggestions.append({
                "title": "Coerenza Cellula e Struttura",
                "desc": f"Verifica che se la Cellula e Gv, la struttura sia 2. Se la Cellula e Gcq/Gq, la struttura sia 1. Trova le incongruenze.",
                "action": "formula_condition",
                "config": cfg,
                "table": t_diff, "column": c_cell
            })

        # Regola 4 e 5: primo passo pratico -> case (cq) o servizi (vol)
        if has_columns(t_diff, ["primo", "passo", "pratico"]):
            c_ppp = get_real_col(t_diff, "primo passo pratico") or get_real_col(t_diff, "passo")
            if c_ppp:
                if t_cq:
                    cfg_case = {
                        "type": "cross_table_existence",
                        "name": "Manca passo Case (CQ)",
                        "source_table": t_diff,
                        "key_source": key_diff,
                        "conditions": [{"column": c_ppp, "operator": "=", "value": "case", "logic": "AND"}],
                        "destinations": [{"table": t_cq, "key": self._guess_primary_key(self.db.table_columns[t_cq]) or key_diff}],
                        "dest_logic": "TUTTE"
                    }
                    suggestions.append({
                        "title": "Passo Pratico: Case (Assente)",
                        "desc": f"Cerca i diffusori con '{c_ppp}' = 'case' ma senza nessuna corrispondenza nella tabella '{t_cq}'.",
                        "action": "cross_table_existence", "config": cfg_case, "table": t_diff, "column": c_ppp
                    })
                
                if t_vol:
                    cfg_serv = {
                        "type": "cross_table_existence",
                        "name": "Manca passo Servizi (Vol)",
                        "source_table": t_diff,
                        "key_source": key_diff,
                        "conditions": [{"column": c_ppp, "operator": "=", "value": "servizi", "logic": "AND"}],
                        "destinations": [{"table": t_vol, "key": self._guess_primary_key(self.db.table_columns[t_vol]) or key_diff}],
                        "dest_logic": "TUTTE"
                    }
                    suggestions.append({
                        "title": "Passo Pratico: Servizi (Assente)",
                        "desc": f"Cerca i diffusori con '{c_ppp}' = 'servizi' ma senza nessuna corrispondenza nella tabella '{t_vol}'.",
                        "action": "cross_table_existence", "config": cfg_serv, "table": t_diff, "column": c_ppp
                    })

        return suggestions
