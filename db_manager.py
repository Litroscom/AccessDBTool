import os
import pyodbc
import threading
import logging

logger = logging.getLogger("AccessDBTool.DatabaseManager")

class DatabaseManager:
    def __init__(self):
        self.conn = None
        self.db_path = ""
        self.tables = []
        self.table_columns = {}
        self.table_pks = {}
        self._lock = threading.Lock()

    @staticmethod
    def _qi(name):
        """Quote a SQL identifier safely for Access (escape closing bracket)."""
        return "[" + str(name).replace("]", "]]") + "]"

    @property
    def connected(self):
        # Proprietà economica e senza side-effect: nessun I/O nel getter.
        return self.conn is not None

    def connect(self, path):
        path = os.path.abspath(os.path.normpath(path))
        if not os.path.exists(path):
            logger.error(f"File non trovato: {path}")
            raise FileNotFoundError("File non trovato:\n" + path)
        
        available = pyodbc.drivers()
        drivers_to_try = []
        for d in available:
            dl = d.lower()
            if "access" in dl and "*.mdb" in dl and "text" not in dl and "dbase" not in dl:
                drivers_to_try.append(d)
        
        if not drivers_to_try:
            logger.error("Nessun driver Access ODBC installato.")
            raise ConnectionError(
                "Nessun driver Access ODBC installato!\nDriver disponibili: " + str(available))
        
        last_err = None
        for drv in drivers_to_try:
            try:
                cs = "DRIVER={" + drv + "};DBQ=" + path + ";"
                self.conn = pyodbc.connect(cs)
                self.db_path = path
                self._discover()
                logger.info(f"Connesso con successo a: {path} utilizzando {drv}")
                return True
            except Exception as e:
                last_err = e
        
        logger.error(f"Impossibile aprire {path}: {last_err}")
        raise ConnectionError(
            "Impossibile aprire: " + path + "\nDriver provati: " + str(drivers_to_try) +
            "\nErrore: " + str(last_err))

    def disconnect(self):
        with self._lock:
            if self.conn:
                try:
                    self.conn.close()
                    logger.info("Database scollegato.")
                except Exception as e:
                    logger.warning(f"Errore durante la disconnessione: {e}")
            self.conn = None
            self.db_path = ""
            self.tables = []
            self.table_columns = {}
            self.table_pks = {}

    @staticmethod
    def _is_user_table(name, table_type=""):
        """True per tabelle utente da mostrare, incluse le tabelle COLLEGATE
        (linked) e le query salvate. Esclude solo le tabelle di sistema."""
        n = str(name or "")
        if n.startswith("MSys") or n.startswith("~"):
            return False
        t = str(table_type or "").strip().upper()
        if t in ("SYSTEM TABLE", "ACCESS TABLE"):
            return False
        return True

    def _discover(self):
        self.tables = []
        self.table_columns = {}
        self.table_pks = {}
        try:
            cur = self.conn.cursor()
            # Nessun filtro su tableType: includiamo anche le tabelle COLLEGATE
            # (linked), che alcuni driver Access riportano con type diverso da
            # "TABLE". Escludiamo solo le tabelle di sistema.
            for row in cur.tables():
                name = row.table_name
                ttype = getattr(row, "table_type", "")
                if not self._is_user_table(name, ttype):
                    continue
                self.tables.append(name)
            self.tables.sort()
            
            for table in self.tables:
                self.table_columns[table] = self._get_columns(table)
                self.table_pks[table] = self._get_primary_keys(table)
            logger.info(f"Scoperte {len(self.tables)} tabelle.")
        except Exception as e:
            logger.error(f"Errore durante il discovery delle tabelle: {e}")

    def _get_primary_keys(self, table):
        """Colonne della chiave primaria reale della tabella (via ODBC).
        Lista vuota se il driver non la espone."""
        pks = []
        try:
            cur = self.conn.cursor()
            for row in cur.primaryKeys(table=table):
                name = getattr(row, "column_name", None)
                if name is None and len(row) > 3:
                    name = row[3]  # COLUMN_NAME nello standard ODBC
                if name:
                    pks.append(name)
        except Exception as e:
            logger.debug(f"Chiave primaria non disponibile per [{table}]: {e}")
        return pks

    def primary_keys(self, table):
        return list(self.table_pks.get(table, []))

    def _get_columns(self, table):
        cols = []
        try:
            cur_t = self.conn.cursor()
            cur_t.execute("SELECT TOP 1 * FROM " + self._qi(table))
            if cur_t.description:
                for d in cur_t.description:
                    type_str = d[1].__name__ if hasattr(d[1], '__name__') else str(d[1])
                    cols.append({
                        "name": d[0],
                        "type": type_str,
                        "size": d[3] if len(d) > 3 and d[3] is not None else 0,
                        "nullable": d[6] if len(d) > 6 else True,
                    })
        except Exception as e:
            logger.warning(f"Impossibile ottenere colonne (metodo SELECT) per [{table}]: {e}")

        if not cols:
            try:
                cur = self.conn.cursor()
                for c in cur.columns(table=table):
                    cols.append({
                        "name": c.column_name, "type": c.type_name,
                        "size": c.column_size, "nullable": c.nullable,
                    })
            except Exception as e:
                logger.warning(f"Impossibile ottenere colonne (metodo .columns()) per [{table}]: {e}")
        return cols

    def columns(self, table):
        return [c["name"] for c in self.table_columns.get(table, [])]

    def fetch(self, sql, params=None):
        with self._lock:
            if self.conn is None:
                raise ConnectionError("Nessuna connessione al database attiva. Aprire un database prima di eseguire query.")
            try:
                cur = self.conn.cursor()
                cur.execute(sql, params or [])
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    return cols, [list(r) for r in cur.fetchall()]
                return [], []
            except Exception as e:
                logger.error(f"Errore durante fetch SQL [{sql}]: {e}")
                raise

    def execute(self, sql, params=None):
        with self._lock:
            if self.conn is None:
                raise ConnectionError("Nessuna connessione al database attiva. Aprire un database prima di eseguire query.")
            try:
                cur = self.conn.cursor()
                cur.execute(sql, params or [])
                self.conn.commit()
                return cur.rowcount
            except Exception as e:
                logger.error(f"Errore durante esecuzione SQL [{sql}]: {e}")
                raise

    def cast_value(self, table, col_name, value):
        """Converte un valore stringa (es. da Treeview) al tipo Python corretto
        basandosi sui metadati della colonna, per evitare errori ODBC di tipo."""
        if value is None:
            return None
        val_s = str(value).strip()
        if val_s == "":
            return None

        col_meta = None
        for c in self.table_columns.get(table, []):
            if c["name"] == col_name:
                col_meta = c
                break
        if col_meta is None:
            logger.debug(f"cast_value: metadati mancanti per {table}.{col_name}, valore ritornato senza conversione.")
            return value  # Nessun metadato, ritorna così com'è

        type_str = col_meta["type"].lower()

        # Tipi interi
        int_types = {"int", "long", "short", "byte", "integer", "counter",
                     "autoincrement", "smallint", "bigint", "tinyint"}
        # Tipi decimali/float
        float_types = {"float", "double", "single", "real", "numeric",
                       "decimal", "currency", "money"}
        # Tipi booleani
        bool_types = {"bit", "boolean", "bool", "yesno"}

        if type_str in int_types:
            try:
                return int(float(val_s.replace(",", ".")))
            except (ValueError, TypeError):
                return value
        elif type_str in float_types:
            try:
                return float(val_s.replace(",", "."))
            except (ValueError, TypeError):
                return value
        elif type_str in bool_types:
            v_lower = val_s.lower()
            if v_lower in ("true", "1", "vero", "sì", "si", "yes", "-1"):
                return True
            elif v_lower in ("false", "0", "falso", "no"):
                return False
            return value
        else:
            # Tipi testo/date → ritorna stringa
            return val_s

    def update_record_safe(self, table, key_dict, data_dict):
        """Aggiorna UN SOLO record con garanzia di unicità.

        key_dict identifica il record (chiave primaria reale o chiave univoca).
        Prima di scrivere verifica che la chiave selezioni ESATTAMENTE 1 record;
        se ne seleziona 0 o più di 1 solleva ValueError e NON scrive nulla.
        Conteggio + UPDATE avvengono nella stessa transazione, sotto lock, con
        un solo commit. Ritorna le righe aggiornate (1) o 0 se non c'è nulla da
        modificare.
        """
        if not key_dict:
            raise ValueError("Impossibile identificare il record (nessuna chiave): modifica annullata.")

        # Solo colonne REALI della tabella: una colonna del risultato che non
        # esiste nella tabella (computata, alias, frutto di join) verrebbe
        # interpretata da Access come parametro -> "Parametri insufficienti"
        # (-3010). Il confronto e' case-insensitive (Access non distingue le
        # maiuscole nei nomi colonna) e usa sempre il nome CANONICO della
        # tabella. Se i metadati colonne non sono noti non filtriamo, per non
        # perdere modifiche legittime.
        known_cols = list(self.columns(table))
        known_map = {str(c).strip().lower(): c for c in known_cols}
        key_lower = {str(k).strip().lower() for k in key_dict}
        set_cols, set_vals, skipped = [], [], []
        for k, v in data_dict.items():
            if str(k).strip().lower() in key_lower:
                continue
            if known_map:
                canonical = known_map.get(str(k).strip().lower())
                if canonical is None:
                    skipped.append(k)
                    continue
                col_name = canonical
            else:
                col_name = k
            set_cols.append(f"{self._qi(col_name)} = ?")
            set_vals.append(v)
        if not set_cols:
            if skipped:
                logger.warning(
                    "update_record_safe: nessuna colonna aggiornabile su [%s]; "
                    "campi ignorati (non colonne reali): %s; colonne tabella: %s",
                    table, skipped, known_cols,
                )
            return 0

        key_clause = " AND ".join(f"{self._qi(k)} = ?" for k in key_dict)
        key_vals = list(key_dict.values())

        with self._lock:
            if self.conn is None:
                raise ConnectionError("Nessuna connessione al database attiva. Aprire un database prima di eseguire query.")
            cur = self.conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {self._qi(table)} WHERE {key_clause}", key_vals)
            row = cur.fetchone()
            count = int(row[0]) if row else 0
            if count != 1:
                raise ValueError(
                    f"Modifica annullata: la chiave identifica {count} record (atteso esattamente 1). "
                    "Nessuna modifica è stata applicata al database."
                )
            update_sql = f"UPDATE {self._qi(table)} SET {', '.join(set_cols)} WHERE {key_clause}"
            try:
                cur.execute(update_sql, set_vals + key_vals)
                self.conn.commit()
                return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 1
            except Exception as e:
                try:
                    self.conn.rollback()
                except Exception as rb_err:
                    logger.warning(f"Errore durante il rollback di update_record_safe: {rb_err}")
                logger.error(
                    "Errore update_record_safe su [%s]: %s | SQL: %s | colonne tabella note: %s",
                    table, e, update_sql, sorted(known_cols),
                )
                raise

    def bulk_update(self, table, set_col, pk_col, pairs):
        """pairs = list of (typed_value, typed_pk). Single transaction, one commit.
        Returns number of rows updated. Rolls back on any error and re-raises."""
        if not pairs:
            return 0
        sql = f"UPDATE {self._qi(table)} SET {self._qi(set_col)} = ? WHERE {self._qi(pk_col)} = ?"
        with self._lock:
            if self.conn is None:
                raise ConnectionError("Nessuna connessione al database attiva. Aprire un database prima di eseguire query.")
            try:
                cur = self.conn.cursor()
                updated = 0
                for typed_value, typed_pk in pairs:
                    cur.execute(sql, (typed_value, typed_pk))
                    # rowcount può essere -1 con alcuni driver: in tal caso conta comunque la riga
                    updated += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 1
                self.conn.commit()
                return updated
            except Exception as e:
                try:
                    self.conn.rollback()
                except Exception as rb_err:
                    logger.warning(f"Errore durante il rollback di bulk_update: {rb_err}")
                logger.error(f"Errore durante bulk_update su [{table}]: {e}")
                raise
