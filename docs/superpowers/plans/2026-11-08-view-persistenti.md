# View persistenti Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminare la distruzione/ricostruzione delle view a ogni cambio tab, così la navigazione scende sotto i 50 ms e lo stato (builder in corso, callback registrate) sopravvive alle pagine.

**Architecture:** `App` diventa proprietaria di un registro `self.views` di view vive, create pigramente alla prima visita e mai distrutte. Il cambio tab è `pack_forget()` della view attiva + `pack()` della destinazione. Tutto il wiring coi controller avviene alla creazione della view (una volta sola), non a ogni switch; allo switch restano solo hook `refresh()` idempotenti.

**Tech Stack:** Python 3.14, tkinter + ttkbootstrap 2.2.7, unittest, SQLite-free (ODBC solo a runtime con Access).

**Spec:** `docs/superpowers/specs/2026-11-08-view-persistenti-design.md`

## Global Constraints

- Branch di lavoro: `fix/view-persistenti` (già creato da `beta`).
- ttkbootstrap 2.x: **una sola root viva per processo**. Nei test la `App` si crea una volta per classe (`setUpClass`) e non si distrugge.
- Il codice delle view importa `ttkbootstrap as ttk` (mai `from tkinter import ttk`).
- I builder si creano **direttamente nel parent finale**; mai `pack(in_=...)`.
- Quoting identificatori ODBC invariato (`_qi`): nessuna query toccata da questo piano.
- Suite esistente da mantenere verde: `python -m unittest tests.test_logic_verification tests.smoke_qa` (131 + 16 test).
- Nessun dato dei DB in `D:\daticirc\se\` deve essere stampato, copiato o esportato.
- Comandi eseguiti dalla root del repo: `C:\Users\Lenovo\AccessDBTool`.

## Review Focus

1. **Cambio tab mentre un batch sta girando**: il log del batch deve finire nella Dashboard viva, senza eccezioni Tcl e senza righe duplicate o widget orfani.
2. **DB aperto dopo che le view esistono già**: le view create senza DB devono aggiornarsi e mostrare tabelle/colonne del DB appena aperto, senza richiedere un riavvio.
3. **Chiusura del DB con tab Controlli popolato**: nessuna eccezione, nessuna tabella stantia nel builder.
4. **Doppio click in Dashboard mentre il tab attivo è già Controlli**: nessuna seconda copia della view impacchettata (`pack_slaves()` resta 1).
5. **Chiusura del DB (o uscita) con 4 view vive e monitor attivo**: `stop_monitor()` + `close_db()` completano senza toccare view distrutte.

---

### Task 1: Registro delle view vive e cambio tab senza ricostruzione

**Files:**
- Create: `tests/test_view_lifecycle.py`
- Modify: `access_db_tool.pyw:85-105` (attributi in `__init__`), `access_db_tool.pyw:333-341` (`_switch_tab`), `access_db_tool.pyw:341-400` (`_wire_view_callbacks` → factory)
- Modify: `app/controllers/app_controller.py:34-70` (`switch_tab`)

**Interfaces:**
- Consumes: niente dai task precedenti.
- Produces:
  - `App.views: dict[str, ttk.Frame]`
  - `App._wired: set[str]`
  - `App._create_view(self, tab_id: str) -> ttk.Frame | None`
  - `App._switch_tab(self, tab_id: str) -> None` (firma invariata)
  - `AppController.set_active_nav(self, tab_id: str, nav_buttons: dict) -> None`
  - `AppController.switch_tab` viene **rimosso** (nessun altro chiamante).

- [ ] **Step 1: Write the failing test**

`tests/test_view_lifecycle.py`, con la stessa convenzione di root di `tests/smoke_qa.py` (root persistente di modulo):

```python
"""Test del ciclo di vita delle view: cambio tab senza ricostruzione."""
import os
import sys
import types
import unittest

sys.modules.setdefault("pyodbc", types.SimpleNamespace(drivers=lambda: []))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tkinter as tk
import ttkbootstrap as _ttkbstrap

_ROOT = tk.Tk()
_ROOT.withdraw()
_ttkbstrap.Style(theme="litera")


class ViewLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import access_db_tool
        cls.app = access_db_tool.App()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.app.app_ctrl.stop_monitor()
        cls.app.db_ctrl.close_db()

    def test_switch_tab_reuses_same_view_instance(self):
        app = self.app
        app._switch_tab("controls")
        first = app.views["controls"]
        app._switch_tab("dashboard")
        app._switch_tab("controls")
        self.assertIs(app.views["controls"], first)
        self.assertIs(app.current_view, first)

    def test_all_four_views_alive_after_full_cycle(self):
        app = self.app
        for tab in ("db", "controls", "dashboard", "monitor"):
            app._switch_tab(tab)
        self.assertEqual(set(app.views), {"db", "controls", "dashboard", "monitor"})

    def test_only_one_view_packed(self):
        app = self.app
        for tab in ("controls", "dashboard", "monitor", "db", "controls"):
            app._switch_tab(tab)
            self.assertEqual(len(app.main_panel.pack_slaves()), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_view_lifecycle -v`
Expected: FAIL con `AttributeError: 'App' object has no attribute 'views'`

- [ ] **Step 3: Implementare il registro**

In `App.__init__`, sostituire `self.current_view = None` con:

```python
self.views = {}
self.current_view = None
self.current_view_id = None
self._wired = set()
```

In `AppController`, sostituire `switch_tab` con la sola gestione della navigazione:

```python
def set_active_nav(self, tab_id, nav_buttons):
    for btn_tab, btn in nav_buttons.items():
        btn.configure(bootstyle="primary" if btn_tab == tab_id else "secondary-outline")
```

In `App`, la factory (spostata da `_wire_view_callbacks`) e lo switch:

```python
def _switch_tab(self, tab_id):
    if self.current_view_id is not None:
        self.views[self.current_view_id].pack_forget()
    view = self.views.get(tab_id)
    if view is None:
        view = self._create_view(tab_id)
        if view is None:
            return
        self.views[tab_id] = view
        self._wire_view_once(tab_id, view)
    view.pack(fill=tk.BOTH, expand=True)
    self.current_view_id = tab_id
    self.current_view = view
    self.app_ctrl.set_active_nav(tab_id, self.nav_buttons)
    self.lbl_page_title.config(text=self._PAGE_TITLES.get(tab_id, ""))
    self._refresh_header_db()
    hook = getattr(view, "refresh", None)
    if hook is not None:
        hook()

def _wire_view_once(self, tab_id, view):
    """Wiring coi controller, eseguito alla creazione della view (una volta sola).
    Corpo = l'attuale `_wire_view_callbacks`, con in testa:
        if tab_id in self._wired: return
    e in coda `self._wired.add(tab_id)`."""
```

La factory `_create_view` (corpo = il ramo di costruzione dell'attuale `switch_tab` di `AppController`, che viene rimosso) istanzia le view **con tutti i controller come argomenti di costruttore** (le firme esistono già): `DatabaseView(main_panel, state, db_ctrl)`, `BuilderView(main_panel, state, db_ctrl, library_controller=self.library_ctrl, result_controller=self.result_ctrl)`, `DashboardView(main_panel, state, db_ctrl, library_controller=self.library_ctrl, batch_controller=self.batch_ctrl, result_controller=self.result_ctrl)`, `MonitorView(main_panel, state, self)`. `state.active_builder = None` **non** viene più azzerato qui.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_view_lifecycle -v`
Expected: PASS (3 test)

- [ ] **Step 5: Commit**

```bash
git add access_db_tool.pyw app/controllers/app_controller.py tests/test_view_lifecycle.py
git commit -m "refactor(v8): view persistenti, cambio tab senza ricostruzione"
```

---

### Task 2: Wiring una volta sola e hook `refresh()` uniformi

**Files:**
- Modify: `access_db_tool.pyw` (`_wire_view_once`: togliere le registrazioni che la view fa già nel proprio costruttore)
- Modify: `views/dashboard_view.py:139` (`_refresh` → alias pubblico `refresh`)
- Modify: `views/monitor_view.py:76` (`_refresh_state_label` → alias pubblico `refresh`)
- Test: `tests/test_view_lifecycle.py`

**Interfaces:**
- Consumes: `App.views`, `App._wired`, `App._wire_view_once` (Task 1).
- Produces: `DashboardView.refresh()`, `MonitorView.refresh()` (alias pubblici).

- [ ] **Step 1: Write the failing test** (aggiungere alla classe esistente)

```python
    def test_results_callbacks_do_not_grow_on_tab_switch(self):
        app = self.app
        app._switch_tab("controls")
        app._switch_tab("dashboard")
        before = len(app.result_ctrl._on_results_callbacks)
        self.assertGreaterEqual(before, 1)
        for i in range(10):
            app._switch_tab("controls" if i % 2 else "dashboard")
        self.assertEqual(len(app.result_ctrl._on_results_callbacks), before)

    def test_refresh_hook_runs_once_per_show(self):
        app = self.app
        app._switch_tab("dashboard")
        view = app.views["dashboard"]
        calls = []
        original = view.refresh
        view.refresh = lambda: (calls.append(1), original())
        try:
            app._switch_tab("controls")
            app._switch_tab("dashboard")
        finally:
            view.refresh = original
        self.assertEqual(len(calls), 1)

    def test_batch_log_during_tab_switch_lands_on_live_dashboard(self):
        app = self.app
        app._switch_tab("controls")
        app.batch_ctrl._on_log("messaggio di prova")
        app.update()
        dash = app.views["dashboard"]
        self.assertIn("messaggio di prova", dash.log_text.get("1.0", "end"))
        self.assertEqual(len(app.main_panel.pack_slaves()), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_view_lifecycle -v`
Expected: FAIL — `AttributeError: 'DashboardView' object has no attribute 'refresh'` e callback che crescono

- [ ] **Step 3: Implementare**

In `views/dashboard_view.py`, dopo `_refresh`:

```python
def refresh(self):
    """Hook pubblico chiamato dall'App quando la pagina torna visibile."""
    self._refresh()
```

In `views/monitor_view.py`, dopo `_refresh_state_label`:

```python
def refresh(self):
    """Hook pubblico chiamato dall'App quando la pagina torna visibile."""
    self._refresh_state_label()
```

In `_wire_view_once` restano solo le registrazioni che la view **non** fa da sé: per `db` i tre setter (`set_load_insight_callback`, `set_db_changed_callback`, `set_profiler_done_callback`), per `dashboard` `set_open_in_builder_callback`, per `monitor` `self.app_ctrl.set_monitor_row_callback(view.add_row)`, per `controls` `result_ctrl.set_results_callback(lambda res, v=view: v.after(0, v.show_results, res))`. **Va rimossa** la `set_results_callback` sul tab `dashboard`: `DashboardView.__init__` la registra già (`dashboard_view.py:135-137`), e registrarla due volte duplicherebbe l'aggiornamento. Idem per le tre `batch_ctrl.set_*_callback`, già fatte nel costruttore della Dashboard.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_view_lifecycle -v`
Expected: PASS (6 test)

- [ ] **Step 5: Commit**

```bash
git add access_db_tool.pyw views/dashboard_view.py views/monitor_view.py tests/test_view_lifecycle.py
git commit -m "refactor(v8): wiring view una volta sola + hook refresh pubblici"
```

---

### Task 3: Lo stato del builder sopravvive al cambio tab

**Files:**
- Modify: `access_db_tool.pyw` (`_open_cond_in_builder`, `_auto_show_results`, `_close_db`, `_run_profiler_from_view` — usare `self.views` invece di `self.current_view`)
- Test: `tests/test_view_lifecycle.py`

**Interfaces:**
- Consumes: `App.views` (Task 1).
- Produces: `App._open_cond_in_builder(self, cond, pending=None) -> None` invariata nella firma, ma indirizzata a `self.views["controls"]`.

- [ ] **Step 1: Write the failing test**

```python
    def test_active_builder_survives_tab_switch(self):
        app = self.app
        app._switch_tab("controls")
        view = app.views["controls"]
        view.load_condition({
            "type": "similarity_check", "name": "QA Sim", "table": "Clienti",
            "column": "Nome", "key_column": "ID", "threshold": 80,
        })
        builder = app.state.active_builder
        self.assertIsNotNone(builder)
        app._switch_tab("dashboard")
        app._switch_tab("controls")
        self.assertIs(app.state.active_builder, builder)

    def test_open_in_builder_twice_keeps_single_packed_view(self):
        app = self.app
        cond = {"type": "value_comparison", "name": "QA Val", "table": "Clienti"}
        app._switch_tab("controls")
        app._open_cond_in_builder(cond)
        app._open_cond_in_builder(cond)
        self.assertEqual(len(app.main_panel.pack_slaves()), 1)
        self.assertIs(app.current_view, app.views["controls"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_view_lifecycle -v`
Expected: FAIL — `assertIs` sul builder fallisce (viene azzerato dallo switch)

- [ ] **Step 3: Implementare**

Rimuovere l'azzeramento residuo di `state.active_builder` dai percorsi di cambio tab. `_open_cond_in_builder` deve fare `self._switch_tab("controls")` e poi usare `view = self.views["controls"]` invece di `self.current_view`. `_auto_show_results` deve indirizzare a `self.views.get("controls")`. Gli shortcut (`_run_profiler_from_view`, `_close_db`) restano sul tab attivo ma leggono `self.views.get(self.current_view_id)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_view_lifecycle -v`
Expected: PASS (8 test)

- [ ] **Step 5: Commit**

```bash
git add access_db_tool.pyw tests/test_view_lifecycle.py
git commit -m "fix(v8): il builder in corso sopravvive al cambio tab"
```

---

### Task 4: Gestore Condizioni collegato alla view viva

**Files:**
- Modify: `app/controllers/library_controller.py:212-214` (`open_manager`) e nuovo metodo `load_condition_in_view`
- Modify: `access_db_tool.pyw` (registrazione del loader in `__init__`)
- Test: `tests/test_view_lifecycle.py`

**Interfaces:**
- Consumes: `App._open_cond_in_builder` (Task 3).
- Produces:
  - `LibraryController.set_view_loader(self, callback) -> None`
  - `LibraryController.set_view_refresher(self, callback) -> None`
  - `LibraryController.load_condition_in_view(self, cond: dict) -> None`

- [ ] **Step 1: Write the failing test**

```python
    def test_manager_load_reaches_live_view(self):
        app = self.app
        app._switch_tab("dashboard")
        view = app.views["controls"]
        received = []
        original = view.load_condition
        view.load_condition = lambda cond: received.append(cond)
        cond = {"type": "value_comparison", "name": "QA Gestore", "table": "Clienti"}
        try:
            app.library_ctrl.load_condition_in_view(cond)
        finally:
            view.load_condition = original
        self.assertEqual(len(received), 1)
        self.assertEqual(app.state.var_saved.get(), "QA Gestore")
        self.assertIs(app.current_view, app.views["controls"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_view_lifecycle -v`
Expected: FAIL — `AttributeError: 'LibraryController' object has no attribute 'load_condition_in_view'`

- [ ] **Step 3: Implementare**

`load_condition_in_view` chiama la logica esistente e poi inoltra alla view:

```python
def load_condition_in_view(self, cond):
    """Carica una condizione e la apre nella view viva (Gestore Condizioni,
    dashboard, libreria). Sostituisce il percorso che si fermava allo stato."""
    self.load_cond_into_builder(cond)
    if self._view_loader is not None:
        self._view_loader(cond)
```

`open_manager` passa `self.load_condition_in_view` come callback di caricamento e `self._view_refresher or (lambda: None)` come callback di refresh, al posto di `lambda: None` e `self.load_cond_into_builder`. In `App.__init__`: `self.library_ctrl.set_view_loader(self._open_cond_in_builder)` e `self.library_ctrl.set_view_refresher(lambda: self.views["controls"].refresh_lib() if "controls" in self.views else None)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_view_lifecycle -v`
Expected: PASS (9 test)

- [ ] **Step 5: Commit**

```bash
git add app/controllers/library_controller.py access_db_tool.pyw tests/test_view_lifecycle.py
git commit -m "fix(v8): Carica dal Gestore Condizioni popola la view viva"
```

---

### Task 5: Cambio/Chiusura DB propaga il refresh alle view vive

**Files:**
- Modify: `access_db_tool.pyw` (`_on_active_db_switched`, `_close_db`, nuovo `_refresh_live_views`)
- Test: `tests/test_view_lifecycle.py`

**Interfaces:**
- Consumes: `App.views` (Task 1), `refresh()` pubblici (Task 2).
- Produces: `App._refresh_live_views(self) -> None`.

- [ ] **Step 1: Write the failing test**

```python
    def test_active_db_switch_refreshes_every_live_view(self):
        app = self.app
        for tab in ("db", "controls", "dashboard", "monitor"):
            app._switch_tab(tab)
        called, originals = [], {}
        for name, view in app.views.items():
            originals[name] = view.refresh
            view.refresh = (lambda n=name: called.append(n))
        try:
            app._on_active_db_switched()
        finally:
            for name, fn in originals.items():
                app.views[name].refresh = fn
        self.assertEqual(set(called), {"db", "controls", "dashboard", "monitor"})

    def test_close_db_with_live_views_does_not_raise(self):
        app = self.app
        app._switch_tab("controls")
        app.app_ctrl.stop_monitor()
        app.db_ctrl.close_db()
        app._refresh_live_views()
        self.assertEqual(len(app.main_panel.pack_slaves()), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_view_lifecycle -v`
Expected: FAIL — `AttributeError: 'App' object has no attribute '_refresh_live_views'`

- [ ] **Step 3: Implementare**

```python
def _refresh_live_views(self):
    """Notifica le view già costruite che lo stato del DB è cambiato."""
    for view in list(self.views.values()):
        hook = getattr(view, "refresh", None)
        if hook is None:
            continue
        try:
            hook()
        except Exception:
            logger.exception("Refresh della view fallito dopo cambio DB")
```

Chiamarla in coda a `_on_active_db_switched` (dopo `stop_monitor`) e in `_close_db` al posto del singolo `self.current_view.refresh()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_view_lifecycle -v`
Expected: PASS (11 test)

- [ ] **Step 5: Commit**

```bash
git add access_db_tool.pyw tests/test_view_lifecycle.py
git commit -m "fix(v8): apertura/chiusura DB aggiorna tutte le view vive"
```

---

### Task 6: Verifica finale — prestazioni e regressione

**Files:**
- Create: `tests/bench_tabs.py`
- Modify: nessuno

**Interfaces:**
- Consumes: tutto quanto sopra.
- Produces: script di misura riproducibile.

- [ ] **Step 1: Committare lo script di misura**

`tests/bench_tabs.py` (script, non test: il nome non inizia con `test_`):

```python
"""Misura il tempo di cambio tab. Uso: python tests/bench_tabs.py"""
import os
import sys
import time
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
logging.disable(logging.CRITICAL)

import access_db_tool

app = access_db_tool.App()
app.update()
for tab in ["controls", "dashboard", "monitor", "db", "controls", "dashboard", "db"]:
    t0 = time.perf_counter()
    app._switch_tab(tab)
    app.update()
    print(f"{tab:10} {(time.perf_counter() - t0) * 1000:8.1f} ms")
app.destroy()
```

- [ ] **Step 2: Misurare**

Run: `python tests/bench_tabs.py`
Expected: la **seconda** visita a ogni tab sotto **50 ms** (baseline pre-modifica: 170-594 ms). Se un tab resta sopra, la sua `refresh()` sta ricostruendo widget: va ridotta a un aggiornamento in place.

- [ ] **Step 3: Suite completa**

Run: `python -m unittest tests.test_logic_verification tests.smoke_qa tests.test_view_lifecycle -v`
Expected: 131 + 16 + 11 test, tutti PASS.

- [ ] **Step 4: Smoke manuale su DB reale (in sola lettura)**

Run: `python access_db_tool.pyw`, poi aprire `D:\daticirc\se\Datico.MDB`, eseguire un controllo, passare tra i 4 tab.
Expected: nessun ritardo percepibile, configurazione intatta dopo il giro dei tab, nessun errore in `app.log`. **Nessun dato estratto o citato.**

- [ ] **Step 5: Commit**

```bash
git add tests/bench_tabs.py
git commit -m "test(v8): script di misura del cambio tab"
```
