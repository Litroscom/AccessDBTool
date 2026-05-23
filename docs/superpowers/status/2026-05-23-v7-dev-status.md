# AccessDBTool v7 — Stato di Sviluppo

**Data:** 2026-05-23  
**Branch:** `feature/v7-ui` (basato su `master` v6)  
**Stato:** 7/7 task completati + fix post-test

## Cosa è stato fatto

| # | Task | Commit | File |
|---|------|--------|------|
| 1 | Setup ttkbootstrap + tema Superhero | `5650fe8` | `theme_config.py`, `requirements.txt` |
| 2 | Sidebar icon-based + 3 tab nav | `05652f7` | `access_db_tool.py`, `access_db_tool.pyw` |
| 3 | DatabaseView (info, insight, registry, tabelle) | `b82c9fb` | `views/database_view.py` |
| 4 | ConditionManager ridisegnato (split, search, sort) | `c5216e7` | `views/condition_manager_view.py` |
| 5 | BuilderView (pill nav, libreria, azioni fisse) | `155c976` | `views/builder_view.py` |
| 6 | DashboardView (griglia, filtri, risultati live, progress) | `2d05372` | `views/dashboard_view.py` |
| 7 | Polish finale, version bump, menu styling | `68980eb`, `a79497e`, `27770e1`, `299444a` | `constants.py`, fix vari |

## Fix aggiuntivi (post-test)

- **Dashboard tag colors**: righe running/error/ok ora usano sfondo scuro e testo chiaro (compatibile Superhero)
- **Menu bar**: stile scuro (`#2B3E50`) coerente con il tema
- **Version bump**: `APP_VERSION = "7.0"` (vs `"6.0"` su master)

## Struttura nuovi file

```
theme_config.py                 → Setup tema Superhero + helper colori
views/__init__.py               → Package marker
views/database_view.py          → Tab 1: info DB, insight, registry, tabelle
views/builder_view.py           → Tab 2: builder a pill, libreria, gruppi
views/dashboard_view.py         → Tab 3: dashboard unificata con progress
views/condition_manager_view.py → Dialog gestione condizioni ridisegnato
```

## File invariati (backend)

`engines.py`, `db_manager.py`, `storage.py`, `monitor_engine.py`, `data_profiler.py`, `logger_config.py`, `ui_components.py` (parzialmente), `build_portable.py`, `pyinstaller_hooks/`, `tests/`

## Come buildare portable

Su Windows con driver ODBC Access:

```batch
git checkout feature/v7-ui
pip install pyinstaller ttkbootstrap
python build_portable.py
```

Output: `dist/AccessDBToolPortable_v7_0/`

## Note

- `access_db_tool.py` e `access_db_tool.pyw` mantenuti sincronizzati (stesse modifiche)
- Il tema Superhero è impostato via `theme_config.setup_theme()` chiamato in `App.__init__`
- La vecchia UI v5 (metodi `_build_tab_*`, `_build_left_panel`, `_configure_v5_theme`) è ancora presente come dead code ma non viene chiamata
- `access_db_tool.pyw` non può essere testato su Linux (no tkinter), va testato su Windows
