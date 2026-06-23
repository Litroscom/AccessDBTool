import os
import sys

APP_VERSION   = "7.4"
APP_BUILD_DATE = "2026-06-23"
APP_TITLE = f"Access DB Quality Control Tool  v{APP_VERSION}  -  agg. {APP_BUILD_DATE}"


def _resolve_runtime_dir():
    """Restituisce la cartella persistente da usare sia in sorgente sia da exe."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


_BASE_DIR = _resolve_runtime_dir()
CONDITIONS_FILE = os.path.join(_BASE_DIR, "saved_conditions.json")
MONITOR_LOG_FILE = os.path.join(_BASE_DIR, "monitor_log.json")
GROUPS_FILE = os.path.join(_BASE_DIR, "condition_groups.json")
DATABASES_FILE = os.path.join(_BASE_DIR, "database_registry.json")
LOG_FILE = os.path.join(_BASE_DIR, "app.log")

CONDITION_TYPES = {
    "cross_table_existence": "Esistenza cross-tabella",
    "duplicate_check":       "Ricerca duplicati esatti",
    "similarity_check":      "Ricerca somiglianze (fuzzy)",
    "value_comparison":      "Confronto valori (multi-condizione)",
    "concat_similarity":     "Accoda colonne + somiglianze",
    "formula_condition":     "Condizione formula SQL",
    "linked_table_intersection": "Incrocio Tabelle con Filtri Duali",
    "format_validation":     "Validazione Formato (Wizard)",
    "daily_coverage_check":  "Controllo Copertura Giornaliera",
    "mandatory_record_check": "Controllo Requisito Settimanale",
    "row_cross_column_check":  "Coerenza Colonne (stessa riga)",
    "aggregate_threshold_check": "Controllo Soglia Aggregata",
    "lookup_validation":       "Dizionario Obbligato (Lookup)",
    "dependent_condition_check": "Condizione Dipendente (SE...ALLORA)",
}

OPERATORS = {
    "=":           "Uguale a",
    "<>":          "Diverso da",
    ">":           "Maggiore di",
    ">=":          "Maggiore o uguale a",
    "<":           "Minore di",
    "<=":          "Minore o uguale a",
    "LIKE":        "Contiene (LIKE)",
    "NOT LIKE":    "Non contiene",
    "REGEXP":        "Corrisponde a (Regex)",
    "NOT REGEXP":    "Non corrisponde (Regex)",
    "IS NULL":       "È Vuoto",
    "IS NOT NULL": "Non e nullo",
}

LOGIC_OPS = ["AND", "OR"]
