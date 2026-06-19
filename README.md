# Access DB Quality Control Tool

Strumento desktop (Tkinter) per il controllo qualità di database Microsoft Access tramite ODBC.
Permette di definire condizioni di validazione, eseguirle in batch su più database, monitorare i risultati e gestire una libreria di controlli riutilizzabili.

- **Versione:** 7.4 (vedi `constants.APP_VERSION`)
- **Build date:** 2026-06-17
- **Requisito runtime:** driver ODBC Microsoft Access installato sul PC target.

## Avvio

```bat
Avvia_Tool.vbs
```

Lo script lancia `pythonw.exe access_db_tool.pyw` (entry point, senza finestra console).

In alternativa, da terminale:

```bat
python access_db_tool.pyw
```

## Architettura (v7)

Architettura modulare MVC con stato condiviso e controller dependency-injected.

```
access_db_tool.pyw      Entry point sottile (~335 righe), orchestratore App(tk.Tk)
app/
  state.py              AppState: dataclass di stato condiviso
  controllers/          Logica applicativa
    app_controller.py   Tab switching, monitor poll, start/stop monitor
    db_controller.py    DB, registry, profiler, risoluzione path
    library_controller.py  CRUD condizioni, export/import, gruppi, tag
    result_controller.py   Esecuzione, export CSV, edit record, bulk replace
    batch_controller.py    Batch multi-db, progress, log, cancel
views/
  builder_view.py       Costruttore condizioni (accordion)
  dashboard_view.py     Dashboard split + progress + log + filtri
  results_view.py       Action bar risultati
  database_view.py      Gestione database (Treeview)
  condition_manager_view.py  Dialog gestione libreria condizioni
```

### Moduli core (root)

| Modulo | Ruolo |
|--------|-------|
| `engines.py` | `ConditionExecutor`, `SimilarityEngine` — motore di esecuzione condizioni |
| `db_manager.py` | `DatabaseManager` — connessioni ODBC e accesso dati |
| `storage.py` | `ConditionStore`, `MonitorLog`, `GroupStore`, `DatabaseRegistry` — persistenza JSON |
| `monitor_engine.py` | `MonitorEngine` — monitoraggio periodico |
| `data_profiler.py` | `DataProfiler` — profilazione colonne/dati |
| `ui_components.py` | Builder e dialog Tkinter riutilizzabili |
| `ui_helpers.py`, `theme_config.py` | Helper UI e tema |
| `constants.py` | Versione, percorsi file, tipi di condizione, operatori |
| `logger_config.py` | Setup logging |

> **Nota:** la migrazione MVC v7 è in corso. Parte della logica UI risiede ancora in `ui_components.py` (file monolitico) e verrà progressivamente spostata nelle view.

## File di stato (runtime)

Generati accanto all'eseguibile/sorgente (pattern portable, `_BASE_DIR` in `constants.py`). Sono in `.gitignore`:

- `saved_conditions.json`
- `condition_groups.json`
- `database_registry.json`
- `monitor_log.json`
- `app.log`

## Build portable

```bat
python build_portable.py
```

Usa PyInstaller (modalità `--onedir --windowed`), include i pacchetti in `_vendor/` e gli hook in `pyinstaller_hooks/`, e produce la distribuzione in `dist/`. Il file `.spec` viene rigenerato a ogni build (è in `.gitignore`).

## Test

```bat
python -m pytest tests/
```

`tests/test_logic_verification.py` verifica la logica dei motori di esecuzione.
