# AccessDBTool v7 — UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Riprogettare l'interfaccia utente della AccessDBTool con ttkbootstrap, layout fluido e 3 tab principali.

**Architecture:** Refactoring progressivo partendo dal tema/struttura, poi componente per componente, senza toccare backend (engines, db_manager, storage restano invariati).

**Tech Stack:** Python 3, tkinter, ttkbootstrap, unittest

**Branch:** `feature/v7-ui` (da `main`/`master`, senza toccare v6)

---

## File Structure

### Nuovi file
| File | Responsabilità |
|---|---|
| `theme_config.py` | Configurazione tema ttkbootstrap (Superhero) |
| `views/__init__.py` | Package views |
| `views/database_view.py` | Tab Database: info DB, insight, registry, tabelle |
| `views/builder_view.py` | Tab Controlli: builder a pill, libreria, gruppi |
| `views/dashboard_view.py` | Tab Dashboard: esecuzione, risultati live, progress |
| `views/condition_manager_view.py` | Dialog Condition Manager ridisegnato (split) |

### File modificati
| File | Cosa cambia |
|---|---|
| `access_db_tool.py` | App.__init__: tema ttkbootstrap, sidebar icon-based, 3 tab, nuovo layout |
| `access_db_tool.pyw` | Stesse modifiche del .py (mantenere sincronizzato) |
| `ui_components.py` | Alleggerito: builder/dashboard/manager migrano in views/ |
| `requirements.txt` | Aggiunta ttkbootstrap (se non presente) |

### File invariati
`engines.py`, `db_manager.py`, `storage.py`, `monitor_engine.py`, `data_profiler.py`, `logger_config.py`, `constants.py`, `build_portable.py`

---

## Task 1: Setup branch, dipendenze, tema base

**Files:**
- Create: `theme_config.py`
- Modify: `access_db_tool.py`, `access_db_tool.pyw`
- Create: `requirements.txt` (se non esiste)

- [ ] **Step 1: Crea il branch**

```bash
cd "/mnt/c/Users/CO/Desktop/Progetti Antigravity/AccessDBTool/AccessDBTool_v6.0"
git checkout -b feature/v7-ui
```

- [ ] **Step 2: Installa ttkbootstrap**

```bash
pip install ttkbootstrap
```

- [ ] **Step 3: Crea `requirements.txt`**

```
pyodbc
rapidfuzz
ttkbootstrap
```

- [ ] **Step 4: Crea `theme_config.py`**

```python
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

THEME_NAME = "superhero"

def setup_theme(app):
    style = ttk.Style(theme=THEME_NAME)
    style.configure("success.TLabel", foreground="#00b894")
    style.configure("danger.TLabel", foreground="#E85D75")
    style.configure("warning.TLabel", foreground="#fdcb6e")
    return style
```

- [ ] **Step 5: Modifica `access_db_tool.py` — import tema e init**

Sostituire l'import dello `style` tkinter nativo con ttkbootstrap:

```python
# In cima, dopo gli import esistenti
import theme_config
```

Nell'`__init__` di `App`, dopo la creazione del `StringVar` status:

```python
self.style = theme_config.setup_theme(self)
# Salta _configure_v5_theme() — verrà rimosso dopo
```

Non rimuovere ancora `_configure_v5_theme()` (serve per i componenti non ancora migrati).

- [ ] **Step 6: Verifica che l'app si avvii**

```bash
python3 -c "import sys; sys.path.insert(0, '.'); import theme_config; print('OK:', theme_config.THEME_NAME)"
```

- [ ] **Step 7: Commit**

```bash
git add theme_config.py requirements.txt access_db_tool.py access_db_tool.pyw
git commit -m "feat(v7): add ttkbootstrap theme base"
```

---

## Task 2: Nuovo layout principale — sidebar icon-based + 3 tab

**Files:**
- Modify: `access_db_tool.py`
- Create: `views/__init__.py`

- [ ] **Step 1: Crea `views/__init__.py`**

```python
# Package per le viste v7
```

- [ ] **Step 2: Riscrivi `_build_layout()` in `access_db_tool.py`**

Sostituire la struttura a PanedWindow + 5 Notebook tab con:

```python
def _build_layout(self):
    for w in self.main_container.winfo_children():
        w.destroy()

    # Main horizontal: sidebar + content
    main_frame = ttk.Frame(self.main_container)
    main_frame.pack(fill=tk.BOTH, expand=True)

    # Sidebar icon-based (~44px)
    self.sidebar = ttk.Frame(main_frame, width=48, style="dark.TFrame")
    self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
    self.sidebar.pack_propagate(False)

    # Content area: tab navigation + pannello principale
    content_frame = ttk.Frame(main_frame)
    content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # Barra navigazione tab (pill)
    self.nav_bar = ttk.Frame(content_frame)
    self.nav_bar.pack(fill=tk.X, padx=8, pady=(8, 0))

    # Crea i 3 bottoni navigazione
    self.nav_buttons = {}
    for nav_id, label, icon in [
        ("db", "Database", "🗄"),
        ("controls", "Controlli", "⚙"),
        ("dashboard", "Dashboard", "📊"),
    ]:
        btn = ttk.Button(
            self.nav_bar, text=f"{icon} {label}",
            command=lambda nid=nav_id: self._switch_tab(nid),
            bootstyle="secondary-outline",
        )
        btn.pack(side=tk.LEFT, padx=2)
        self.nav_buttons[nav_id] = btn

    # Pannello principale che cambia contenuto
    self.main_panel = ttk.Frame(content_frame, padding=8)
    self.main_panel.pack(fill=tk.BOTH, expand=True)

    # Panel controllo info DB (collassabile, a destra)
    self.info_panel = ttk.Frame(content_frame, width=220)
    # visibile solo quando serve

    # Status bar
    self._build_status_bar(self.main_container)

    # Mostra tab iniziale
    self._switch_tab("db")
```

- [ ] **Step 3: Aggiungi metodo `_switch_tab()`**

```python
def _switch_tab(self, tab_id):
    for btn in self.nav_buttons.values():
        btn.configure(bootstyle="secondary-outline")
    self.nav_buttons[tab_id].configure(bootstyle="primary")

    for w in self.main_panel.winfo_children():
        w.destroy()

    if tab_id == "db":
        from views.database_view import DatabaseView
        self.current_view = DatabaseView(self.main_panel, self)
    elif tab_id == "controls":
        from views.builder_view import BuilderView
        self.current_view = BuilderView(self.main_panel, self)
    elif tab_id == "dashboard":
        from views.dashboard_view import DashboardView
        self.current_view = DashboardView(self.main_panel, self)

    self.current_view.pack(fill=tk.BOTH, expand=True)
```

- [ ] **Step 5: Riscrivi `_build_status_bar()`**

```python
def _build_status_bar(self, parent):
    sb = ttk.Frame(parent, bootstyle="dark")
    sb.pack(fill=tk.X, side=tk.BOTTOM)
    self.status_label = ttk.Label(
        sb, textvariable=self.status,
        bootstyle="inverse-dark", padding=(8, 4)
    )
    self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
    self.mon_indicator = ttk.Label(
        sb, text=" MONITOR OFF ",
        bootstyle="inverse-danger", padding=(8, 2)
    )
    self.mon_indicator.pack(side=tk.RIGHT)
```

- [ ] **Step 6: Adatta `__init__` per il nuovo layout**

In `App.__init__`, dopo `self._build_menu()` e `self._bind_global_shortcuts()`:

```python
self._build_layout()  # invece di self._show_home()
self._poll_monitor()
```

Commentare `self._show_home()` (la home sarà la tab Database).

- [ ] **Step 7: Commit**

```bash
git add views/__init__.py access_db_tool.py access_db_tool.pyw
git commit -m "feat(v7): new icon sidebar + 3-tab navigation layout"
```

---

## Task 3: DatabaseView — info DB, insight, registry, tabelle

**Files:**
- Create: `views/database_view.py`
- Modify: `access_db_tool.py`

- [ ] **Step 1: Crea `views/database_view.py`**

```python
import tkinter as tk
from tkinter import ttk
import logging

logger = logging.getLogger("AccessDBTool.DatabaseView")

class DatabaseView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        # Layout orizzontale: sinistra (info+insight) | destra (registry+tabelle)
        left = ttk.Frame(self)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        right = ttk.Frame(self, width=300)
        right.pack(side=tk.RIGHT, fill=tk.BOTH)
        right.pack_propagate(False)

        # --- Sinistra: Info DB + Insight ---
        db_frame = ttk.LabelFrame(left, text="Database Connesso", padding=8, bootstyle="info")
        db_frame.pack(fill=tk.X, pady=(0, 8))

        self.lbl_db_name = ttk.Label(db_frame, text="Nessun DB", font=("", 12, "bold"))
        self.lbl_db_name.pack(anchor=tk.W)
        self.lbl_db_path = ttk.Label(db_frame, text="", font=("", 9))
        self.lbl_db_path.pack(anchor=tk.W)
        self.lbl_db_tables = ttk.Label(db_frame, text="")
        self.lbl_db_tables.pack(anchor=tk.W)

        btn_frame = ttk.Frame(db_frame)
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_frame, text="Apri Database...", command=self.app._open_db,
                   bootstyle="primary").pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Chiudi", command=self.app._close_db,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=2)

        # Insight
        insight_frame = ttk.LabelFrame(left, text="Insight Automatici", padding=8)
        insight_frame.pack(fill=tk.BOTH, expand=True)

        self.ins_tree = ttk.Treeview(
            insight_frame, show="headings",
            columns=["title", "desc", "action"], height=8
        )
        self.ins_tree.heading("title", text="Suggerimento")
        self.ins_tree.heading("desc", text="Descrizione")
        self.ins_tree.heading("action", text="Tipo")
        self.ins_tree.column("title", width=200)
        self.ins_tree.column("desc", width=400)
        self.ins_tree.column("action", width=120)
        self.ins_tree.pack(fill=tk.BOTH, expand=True)
        self.ins_tree.bind("<Double-1>", self.app._load_insight)
        self.current_insights = []

        ttk.Button(insight_frame, text="Genera Insight",
                   command=self.app._run_profiler,
                   bootstyle="info-outline").pack(anchor=tk.W, pady=(4, 0))

        # --- Destra: Registry + Tabelle ---
        reg_frame = ttk.LabelFrame(right, text="Database Collegati", padding=8)
        reg_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.db_registry_tree = ttk.Treeview(
            reg_frame, columns=("label", "state"), show="headings", height=5
        )
        self.db_registry_tree.heading("label", text="Database")
        self.db_registry_tree.heading("state", text="Stato")
        self.db_registry_tree.column("label", width=160)
        self.db_registry_tree.column("state", width=90, anchor=tk.CENTER)
        self.db_registry_tree.pack(fill=tk.BOTH, expand=True)
        self.db_registry_tree.bind("<<TreeviewSelect>>", self._on_registry_select)
        self.lbl_registry_path = ttk.Label(reg_frame, text="", font=("", 8))
        self.lbl_registry_path.pack(fill=tk.X, pady=(4, 0))

        # Tabelle
        tab_frame = ttk.LabelFrame(right, text="Tabelle", padding=8)
        tab_frame.pack(fill=tk.BOTH, expand=True)

        scroll = ttk.Scrollbar(tab_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.lst_tables = tk.Listbox(
            tab_frame, yscrollcommand=scroll.set,
            font=("Consolas", 10), selectmode=tk.MULTIPLE
        )
        self.lst_tables.pack(fill=tk.BOTH, expand=True)
        scroll.config(command=self.lst_tables.yview)
        self.lst_tables.bind("<<ListboxSelect>>", self.app._on_table_sel)

    def refresh(self):
        """Aggiorna la UI con lo stato corrente del DB."""
        if self.app.db.connected:
            label = self.app.current_db_label or "DB connesso"
            self.lbl_db_name.config(text=label)
            self.lbl_db_path.config(text=str(self.app.db.db_path))
            self.lbl_db_tables.config(
                text=f"{len(self.app.db.tables)} tabelle trovate"
            )
        else:
            self.lbl_db_name.config(text="Nessun DB")
            self.lbl_db_path.config(text="")
            self.lbl_db_tables.config(text="")
        self._refresh_registry()
        self._refresh_tables()

    def _refresh_registry(self):
        self.db_registry_tree.delete(*self.db_registry_tree.get_children())
        current_path = str(getattr(self.app.db, "db_path", "") or "")
        for entry in self.app.db_registry.entries():
            label = entry.get("label", "")
            path = entry.get("path", "")
            path_exists = bool(path and os.path.exists(path))
            if self.app.db.connected and current_path and os.path.normcase(path) == os.path.normcase(current_path):
                state = "APERTO"
            elif path_exists:
                state = "PRONTO"
            else:
                state = "DA RICOLLEGARE"
            self.db_registry_tree.insert("", tk.END, iid=label, values=(label, state))

    def _refresh_tables(self):
        self.lst_tables.delete(0, tk.END)
        if self.app.db.connected:
            for table in self.app.db.tables:
                self.lst_tables.insert(tk.END, table)

    def _on_registry_select(self, _evt=None):
        sel = self.db_registry_tree.selection()
        if not sel:
            return
        label = sel[0]
        path = self.app.db_registry.get_path(label)
        self.lbl_registry_path.config(text=path or "Percorso non associato.")
```

- [ ] **Step 2: Aggancia `DatabaseView` in `access_db_tool.py`**

In `_switch_tab`, quando `tab_id == "db"`:

```python
from views.database_view import DatabaseView
self.current_view = DatabaseView(self.main_panel, self)
self.current_view.refresh()
```

- [ ] **Step 3: Sostituisci i riferimenti alla UI vecchia con i nuovi widget**

In `_sync_open_database_ui()` e `_refresh_database_registry_ui()`, aggiungere chiamate a `self.current_view.refresh()` se la vista corrente è `DatabaseView`.

- [ ] **Step 4: Commit**

```bash
git add views/database_view.py access_db_tool.py access_db_tool.pyw
git commit -m "feat(v7): DatabaseView with info, insight, registry, tables"
```

---

## Task 4: BuilderView — tab builder a pill

**Files:**
- Create: `views/builder_view.py`
- Modify: `access_db_tool.py`
- Modify: `ui_components.py` (spostare/riusare builder components esistenti)

- [ ] **Step 1: Crea `views/builder_view.py`**

```python
import tkinter as tk
from tkinter import ttk
import logging

logger = logging.getLogger("AccessDBTool.BuilderView")

class BuilderView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._sections = {}  # dict di frame/sezioni
        self._active_section = None
        self._build_ui()

    def _build_ui(self):
        # Top bar: tipo analisi, tag, database
        top = ttk.Frame(self)
        top.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(top, text="Tipo Analisi:", font=("", 9, "bold")).pack(side=tk.LEFT)
        self.cmb_ctype = ttk.Combobox(
            top, values=list(constants.CONDITION_TYPES.values()),
            state="readonly", width=35
        )
        self.cmb_ctype.pack(side=tk.LEFT, padx=8)
        self.cmb_ctype.bind("<<ComboboxSelected>>", self._on_ctype_change)

        ttk.Label(top, text="Tag:", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(20, 4))
        self.var_tag = tk.StringVar(value="Tutti")
        self.cmb_tag = ttk.Combobox(
            top, textvariable=self.var_tag, state="readonly", width=18
        )
        self.cmb_tag.pack(side=tk.LEFT, padx=4)

        ttk.Label(top, text="DB:", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(20, 4))
        self.var_db = tk.StringVar()
        self.cmb_db = ttk.Combobox(
            top, textvariable=self.var_db, state="readonly", width=20
        )
        self.cmb_db.pack(side=tk.LEFT, padx=4)

        # Navigazione a pill
        self.nav_sections = ttk.Frame(self)
        self.nav_sections.pack(fill=tk.X, pady=(0, 6))

        self.pill_buttons = {}
        for sid, slabel in [
            ("base", "Base"),
            ("filtri", "Filtri"),
            ("esclusioni", "Esclusioni"),
            ("report", "Colonne Report"),
            ("periodicita", "Periodicità"),
        ]:
            btn = ttk.Button(
                self.nav_sections, text=slabel,
                command=lambda s=sid: self._show_section(s),
                bootstyle="secondary-outline",
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.pill_buttons[sid] = btn

        # Area contenuto sezione attiva
        self.section_content = ttk.Frame(self, relief=tk.SUNKEN, borderwidth=1)
        self.section_content.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        # Area libreria (sotto)
        lib_frame = ttk.LabelFrame(self, text="Libreria", padding=6)
        lib_frame.pack(fill=tk.X)

        self.cmb_lib = ttk.Combobox(lib_frame, state="readonly", width=40)
        self.cmb_lib.pack(side=tk.LEFT, padx=4)
        ttk.Button(lib_frame, text="Carica",
                   command=self._load_from_lib,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)
        ttk.Button(lib_frame, text="Gestisci...",
                   command=self.app._open_manager,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)
        ttk.Button(lib_frame, text="Gruppi...",
                   command=self._open_groups,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        # Bottoni azione fissi in basso
        action_bar = ttk.Frame(self)
        action_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(action_bar, text="Pulisci",
                   command=self.app._clear_builder,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="💾 Salva in Libreria",
                   command=self.app._save_to_lib,
                   bootstyle="success").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="♻ Aggiorna Salvata",
                   command=self.app._update_to_lib,
                   bootstyle="warning").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="▶ Esegui Controllo",
                   command=self.app._run_current,
                   bootstyle="danger").pack(side=tk.RIGHT, padx=2)

    def _on_ctype_change(self, _evt=None):
        ctype_name = self.cmb_ctype.get()
        rev = {v: k for k, v in constants.CONDITION_TYPES.items()}
        self.app._active_ctype = rev.get(ctype_name)
        self.app._update_builder_fields()
        self._show_section("base")

    def _show_section(self, section_id):
        for sid, btn in self.pill_buttons.items():
            btn.configure(bootstyle="secondary-outline")
        self.pill_buttons[section_id].configure(bootstyle="primary")
        self._active_section = section_id

        for w in self.section_content.winfo_children():
            w.destroy()

        if section_id == "base":
            self._build_section_base()
        elif section_id == "filtri":
            self._build_section_filtri()
        elif section_id == "esclusioni":
            self._build_section_esclusioni()
        elif section_id == "report":
            self._build_section_report()
        elif section_id == "periodicita":
            self._build_section_periodicita()

    def _build_section_base(self):
        """Mostra i campi base del builder attivo."""
        if hasattr(self.app, "frm_dyn") and self.app.active_builder:
            # Re-pack del builder esistente nell'area sezione
            self.app.active_builder.pack(in_=self.section_content, fill=tk.BOTH, expand=True)
        else:
            ttk.Label(self.section_content, text="Seleziona un tipo analisi per iniziare.").pack()

    def _build_section_filtri(self):
        ttk.Label(self.section_content, text="Filtri condizioni (in arrivo)").pack()

    def _build_section_esclusioni(self):
        ttk.Label(self.section_content, text="Esclusioni (in arrivo)").pack()

    def _build_section_report(self):
        """Selettore colonne di report."""
        if hasattr(self.app, "col_selector"):
            self.app.col_selector.pack(in_=self.section_content, fill=tk.X, pady=5)

    def _build_section_periodicita(self):
        ttk.Label(self.section_content, text="Configurazione periodicità (in arrivo)").pack()

    def _load_from_lib(self):
        self.app._load_from_lib()

    def _open_groups(self):
        from ui_components import GroupSelector
        GroupSelector(...)  # sarà rifatto come vista dedicata

    def refresh_lib(self):
        names = self.app.store.names()
        self.cmb_lib["values"] = names
        if self.app.var_saved.get() not in names:
            self.app.var_saved.set("")
```

- [ ] **Step 2: Aggancia BuilderView in `access_db_tool.py`**

In `_switch_tab` per `tab_id == "controls"`:

```python
from views.builder_view import BuilderView
self.current_view = BuilderView(self.main_panel, self)
```

Adattare `_refresh_lib` per chiamare anche `self.current_view.refresh_lib()` se la vista attiva è BuilderView.

- [ ] **Step 3: Commit**

```bash
git add views/builder_view.py access_db_tool.py access_db_tool.pyw
git commit -m "feat(v7): BuilderView with pill navigation and fixed action bar"
```

---

## Task 5: Condition Manager ridisegnato

**Files:**
- Create: `views/condition_manager_view.py`
- Modify: `access_db_tool.py`
- Modify: `ui_components.py` (chiamare nuovo dialog invece del vecchio)

- [ ] **Step 1: Crea `views/condition_manager_view.py`**

```python
import tkinter as tk
from tkinter import ttk, messagebox
import logging

logger = logging.getLogger("AccessDBTool.ConditionManagerView")

class ConditionManagerDialog(tk.Toplevel):
    def __init__(self, parent, store, on_refresh, on_load):
        super().__init__(parent)
        self.store = store
        self.on_refresh = on_refresh
        self.on_load = on_load
        self.title("Gestione Condizioni — AccessDBTool v7")
        self.geometry("800x500")
        self.minsize(600, 350)

        self._build_ui()
        self._populate()

    def _build_ui(self):
        # Barra superiore: ricerca + filtro + ordinamento
        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="🔍").pack(side=tk.LEFT, padx=(0, 4))
        self.var_search = tk.StringVar()
        self.entry_search = ttk.Entry(toolbar, textvariable=self.var_search, width=30)
        self.entry_search.pack(side=tk.LEFT, padx=4)
        self.entry_search.bind("<KeyRelease>", lambda _: self._populate())

        ttk.Label(toolbar, text="Ordina:").pack(side=tk.LEFT, padx=(20, 4))
        self.var_sort = tk.StringVar(value="Nome")
        self.cmb_sort = ttk.Combobox(
            toolbar, textvariable=self.var_sort,
            values=["Nome", "Categoria", "Database", "Data"],
            state="readonly", width=12
        )
        self.cmb_sort.pack(side=tk.LEFT, padx=4)
        self.cmb_sort.bind("<<ComboboxSelected>>", lambda _: self._populate())

        ttk.Label(toolbar, text="Filtro:").pack(side=tk.LEFT, padx=(20, 4))
        self.var_filter = tk.StringVar(value="Tutti")
        self.cmb_filter = ttk.Combobox(
            toolbar, textvariable=self.var_filter,
            values=["Tutti"], state="readonly", width=14
        )
        self.cmb_filter.pack(side=tk.LEFT, padx=4)
        self.cmb_filter.bind("<<ComboboxSelected>>", lambda _: self._populate())

        ttk.Button(toolbar, text="📋 Esporta",
                   command=self._export_selected,
                   bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="📂 Importa",
                   command=self._import,
                   bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=2)

        # Split principale: lista | dettaglio
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Lista condizioni
        list_frame = ttk.Frame(paned, padding=4)
        paned.add(list_frame, weight=1)

        self.list_tree = ttk.Treeview(
            list_frame, columns=("name", "tag", "db"),
            show="headings", selectmode="browse"
        )
        self.list_tree.heading("name", text="Nome")
        self.list_tree.heading("tag", text="Tag")
        self.list_tree.heading("db", text="Database")
        self.list_tree.column("name", width=180)
        self.list_tree.column("tag", width=100)
        self.list_tree.column("db", width=130)

        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.list_tree.yview)
        self.list_tree.configure(yscrollcommand=scroll.set)
        self.list_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_tree.bind("<<TreeviewSelect>>", self._on_select)

        # Dettaglio condizione
        detail_frame = ttk.Frame(paned, padding=8)
        paned.add(detail_frame, weight=1)

        self.detail_name = ttk.Label(detail_frame, text="", font=("", 12, "bold"))
        self.detail_name.pack(anchor=tk.W)

        self.detail_info = ttk.Frame(detail_frame)
        self.detail_info.pack(fill=tk.X, pady=6)

        self._detail_labels = {}
        for field, label in [
            ("type", "Tipo analisi:"),
            ("tag", "Tag/Macrosettore:"),
            ("db", "Database:"),
            ("table", "Tabella:"),
            ("period", "Periodicità:"),
            ("saved_at", "Salvato il:"),
        ]:
            row = ttk.Frame(self.detail_info)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=label, width=14, font=("", 9, "bold")).pack(side=tk.LEFT)
            lbl = ttk.Label(row, text="")
            lbl.pack(side=tk.LEFT, padx=4)
            self._detail_labels[field] = lbl

        # Bottoni azione dettaglio
        action_frame = ttk.Frame(detail_frame)
        action_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(action_frame, text="✏ Modifica", command=self._edit,
                   bootstyle="primary").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="📋 Duplica", command=self._duplicate,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="🗑 Elimina", command=self._delete,
                   bootstyle="danger").pack(side=tk.LEFT, padx=2)

        # Footer con conteggio
        footer = ttk.Frame(self, padding=6)
        footer.pack(fill=tk.X)
        self.lbl_count = ttk.Label(footer, text="", bootstyle="info")
        self.lbl_count.pack(side=tk.LEFT)

    def _populate(self):
        self.list_tree.delete(*self.list_tree.get_children())
        query = self.var_search.get().strip().lower()
        sort_by = self.var_sort.get()
        filter_tag = self.var_filter.get().strip()

        items = list(self.store.items)
        if filter_tag and filter_tag != "Tutti":
            items = [c for c in items if c.get("tag", "").strip() == filter_tag]
        if query:
            items = [
                c for c in items
                if query in c.get("name", "").lower()
                or query in c.get("tag", "").lower()
            ]

        if sort_by == "Nome":
            items.sort(key=lambda c: c.get("name", "").lower())
        elif sort_by == "Categoria":
            items.sort(key=lambda c: (c.get("tag", "").lower(), c.get("name", "").lower()))
        elif sort_by == "Database":
            items.sort(key=lambda c: (c.get("database_label", "").lower(), c.get("name", "").lower()))
        elif sort_by == "Data":
            items.sort(key=lambda c: c.get("saved_at", ""), reverse=True)

        for idx, cond in enumerate(items):
            self.list_tree.insert(
                "", tk.END, iid=str(idx),
                values=(
                    cond.get("name", ""),
                    cond.get("tag", ""),
                    cond.get("database_label", ""),
                )
            )

        # Aggiorna filtri tag
        all_tags = self.store.tags()
        self.cmb_filter["values"] = ["Tutti"] + all_tags

        self.lbl_count.config(text=f"{len(items)} condizioni su {len(self.store.items)}")

    def _on_select(self, _evt=None):
        sel = self.list_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        items = self._current_items()
        if idx >= len(items):
            return
        cond = items[idx]
        self._show_detail(cond)

    def _current_items(self):
        return self.store.items  # filtro già applicato in _populate

    def _show_detail(self, cond):
        self.detail_name.config(text=cond.get("name", ""))
        type_key = cond.get("type", "")
        type_label = constants.CONDITION_TYPES.get(type_key, type_key)
        self._detail_labels["type"].config(text=type_label)
        self._detail_labels["tag"].config(text=cond.get("tag", "") or "-")
        self._detail_labels["db"].config(text=cond.get("database_label", "") or "-")
        self._detail_labels["table"].config(text=cond.get("table", "") or "-")
        cycle = cond.get("periodic_review_cycle", "")
        if cond.get("periodic_review_enabled") and cycle:
            self._detail_labels["period"].config(text=f"{cycle.capitalize()} (da aggiornare)")
        else:
            self._detail_labels["period"].config(text="-")
        self._detail_labels["saved_at"].config(text=cond.get("saved_at", "") or "-")

    def _edit(self):
        sel = self.list_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        items = self._current_items()
        if idx >= len(items):
            return
        self.on_load(items[idx])
        self.destroy()

    def _duplicate(self):
        sel = self.list_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        items = self._current_items()
        if idx >= len(items):
            return
        cond = dict(items[idx])
        cond["name"] = cond.get("name", "") + " (copia)"
        self.store.add(cond)
        self._populate()
        self.on_refresh()

    def _delete(self):
        sel = self.list_tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("Conferma", "Eliminare la condizione selezionata?"):
            return
        idx = int(sel[0])
        items = self._current_items()
        global_idx = self.store.items.index(items[idx])
        self.store.delete(global_idx)
        self._populate()
        self.on_refresh()

    def _export_selected(self):
        from access_db_tool import App
        App._export_conditions(self, self.store.items)

    def _import(self):
        self.app._import_conditions()
        self._populate()
```

- [ ] **Step 2: Sostituisci chiamata in `access_db_tool.py:_open_manager`**

```python
def _open_manager(self):
    from views.condition_manager_view import ConditionManagerDialog
    ConditionManagerDialog(self, self.store, self._refresh_lib, self._load_cond_into_builder)
```

- [ ] **Step 3: Commit**

```bash
git add views/condition_manager_view.py access_db_tool.py access_db_tool.pyw
git commit -m "feat(v7): redesigned ConditionManager with split layout, search, sort"
```

---

## Task 6: DashboardView unificata

**Files:**
- Create: `views/dashboard_view.py`
- Modify: `access_db_tool.py`

- [ ] **Step 1: Crea `views/dashboard_view.py`**

```python
import tkinter as tk
from tkinter import ttk
import threading
import logging

logger = logging.getLogger("AccessDBTool.DashboardView")

class DashboardView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        # Filtri rapidi
        filters = ttk.Frame(self, padding=6)
        filters.pack(fill=tk.X)

        ttk.Label(filters, text="📂 DB:").pack(side=tk.LEFT)
        self.var_db_filter = tk.StringVar(value="Tutti")
        self.cmb_db = ttk.Combobox(
            filters, textvariable=self.var_db_filter,
            values=["Tutti"], state="readonly", width=18
        )
        self.cmb_db.pack(side=tk.LEFT, padx=4)
        self.cmb_db.bind("<<ComboboxSelected>>", lambda _: self._refresh())

        ttk.Label(filters, text="🏷 Tag:").pack(side=tk.LEFT, padx=(12, 4))
        self.var_tag_filter = tk.StringVar(value="Tutti")
        self.cmb_macro = ttk.Combobox(
            filters, textvariable=self.var_tag_filter,
            values=["Tutti"], state="readonly", width=18
        )
        self.cmb_macro.pack(side=tk.LEFT, padx=4)
        self.cmb_macro.bind("<<ComboboxSelected>>", lambda _: self._refresh())

        ttk.Checkbutton(filters, text="Solo anomalie",
                        variable=tk.BooleanVar(value=False),
                        command=self._refresh).pack(side=tk.LEFT, padx=(12, 4))

        self.var_search_text = tk.StringVar()
        self.entry_search = ttk.Entry(filters, textvariable=self.var_search_text, width=20)
        self.entry_search.pack(side=tk.LEFT, padx=4)
        self.entry_search.bind("<KeyRelease>", lambda _: self._refresh())

        # Bottoni azione
        ttk.Button(filters, text="▶ Esegui Selezionato",
                   command=self._run_selected,
                   bootstyle="warning-outline").pack(side=tk.RIGHT, padx=2)
        ttk.Button(filters, text="▶ Esegui Tutti",
                   command=self._run_all,
                   bootstyle="danger").pack(side=tk.RIGHT, padx=2)

        # Griglia controlli (tabella compatta)
        tree_frame = ttk.Frame(self, padding=4)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.dash_tree = ttk.Treeview(
            tree_frame,
            columns=["id", "group", "db", "name", "period", "tag", "type", "count", "status"],
            show="headings", height=10,
        )
        self.dash_tree.heading("id", text="#"); self.dash_tree.column("id", width=30, anchor=tk.CENTER)
        self.dash_tree.heading("group", text="Gruppo"); self.dash_tree.column("group", width=120)
        self.dash_tree.heading("db", text="DB"); self.dash_tree.column("db", width=120)
        self.dash_tree.heading("name", text="Controllo"); self.dash_tree.column("name", width=250)
        self.dash_tree.heading("period", text="Periodo"); self.dash_tree.column("period", width=160)
        self.dash_tree.heading("tag", text="Tag"); self.dash_tree.column("tag", width=120)
        self.dash_tree.heading("type", text="Tipo"); self.dash_tree.column("type", width=120)
        self.dash_tree.heading("count", text="Ris."); self.dash_tree.column("count", width=60, anchor=tk.CENTER)
        self.dash_tree.heading("status", text="Stato"); self.dash_tree.column("status", width=120)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.dash_tree.yview)
        self.dash_tree.configure(yscrollcommand=vsb.set)
        self.dash_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.dash_tree.tag_configure("error", background="#fff0f0")
        self.dash_tree.tag_configure("ok", background="#f0fff4")
        self.dash_tree.tag_configure("running", background="#fffbe6")
        self.dash_tree.bind("<Double-1>", self._on_double_click)

        # Pannello risultati live
        result_frame = ttk.LabelFrame(self, text="Risultati", padding=4)
        result_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.res_lbl = ttk.Label(result_frame, text="Nessun risultato", font=("", 9))
        self.res_lbl.pack(anchor=tk.W)

        self.res_tree = ttk.Treeview(result_frame, show="headings", height=5)
        self.res_tree.pack(fill=tk.BOTH, expand=True)

        # Progress bar
        self.progress_frame = ttk.Frame(result_frame)
        self.progress_frame.pack(fill=tk.X, pady=(4, 0))
        self.progress = ttk.Progressbar(
            self.progress_frame, mode="determinate",
            bootstyle="success-striped"
        )
        self.progress.pack(fill=tk.X)
        self.lbl_progress = ttk.Label(self.progress_frame, text="", font=("", 8))
        self.lbl_progress.pack(anchor=tk.W)

    def _refresh(self):
        self.app._refresh_dash()

    def _run_selected(self):
        self.app._run_selected_dashboard_check()

    def _run_all(self):
        self.app._run_all_batch()

    def _on_double_click(self, evt):
        self.app._on_dash_double_click(evt)

    def show_results(self, res):
        """Mostra i risultati nel pannello live."""
        if not res:
            return
        self.res_lbl.config(text=f"{res.get('title', '?')} ({res.get('count', 0)} record)")
        self.res_tree.delete(*self.res_tree.get_children())
        self.res_tree["columns"] = res.get("columns", [])
        for c in res.get("columns", []):
            self.res_tree.heading(c, text=c)
            self.res_tree.column(c, width=120)
        for i, r in enumerate(res.get("rows", [])):
            self.res_tree.insert("", tk.END, iid=str(i), values=r)

    def show_progress(self, current, total, text=""):
        if total > 0:
            self.progress["maximum"] = total
            self.progress["value"] = current
        self.lbl_progress.config(text=text)
```

- [ ] **Step 3: Aggancia DashboardView in `access_db_tool.py`**

In `_switch_tab` per `tab_id == "dashboard"`:

```python
from views.dashboard_view import DashboardView
self.current_view = DashboardView(self.main_panel, self)
self.current_view._refresh()
```

Sostituire `_show_results` per chiamare anche `self.current_view.show_results(res)` quando la vista attiva è DashboardView.

- [ ] **Step 4: Commit**

```bash
git add views/dashboard_view.py access_db_tool.py access_db_tool.pyw
git commit -m "feat(v7): unified DashboardView with filters, grid, live results, progress"
```

---

## Task 7: Integrazione e pulizia finale

**Files:**
- Modify: `access_db_tool.py`
- Modify: `access_db_tool.pyw`

- [ ] **Step 1: Sostituisci `_show_results` per dashboard**

```python
def _show_results(self, res):
    self.current_result = res
    if hasattr(self, "current_view") and hasattr(self.current_view, "show_results"):
        self.current_view.show_results(res)
    else:
        # Fallback: vecchio comportamento
        self.res_lbl.config(text=f"{res['title']} ({res['count']} record)")
        ...
```

- [ ] **Step 2: Rivedi `_refresh_dash`, `_sync_open_database_ui`, `_refresh_database_registry_ui`**

Farli puntare ai nuovi widget in `DatabaseView` e `DashboardView`.

- [ ] **Step 3: Rimuovi `_configure_v5_theme()` e codice theme legacy**

Sostituito da ttkbootstrap.

- [ ] **Step 4: Verifica integrazione**

```bash
cd "/mnt/c/Users/CO/Desktop/Progetti Antigravity/AccessDBTool/AccessDBTool_v6.0"
python3 -c "
import sys, os
sys.path.insert(0, '.')
# Test import dei nuovi moduli
from theme_config import setup_theme, THEME_NAME
from views.database_view import DatabaseView
from views.builder_view import BuilderView
from views.dashboard_view import DashboardView
from views.condition_manager_view import ConditionManagerDialog
print('All imports OK')
"
```

- [ ] **Step 5: Esegui i test esistenti**

```bash
python3 -m unittest tests/test_logic_verification.py -v 2>&1 | head -30
```
I test che non toccano la UI dovrebbero ancora passare (backend invariato).

- [ ] **Step 6: Commit**

```bash
git add access_db_tool.py access_db_tool.pyw
git commit -m "feat(v7): final integration, legacy theme removal, view wiring"
```

---

## Self-Review

| Requisito spec | Task |
|---|---|
| ttkbootstrap theme (Superhero) | Task 1 |
| Sidebar icon-based (44px) | Task 2 |
| 3 tab principali (DB, Controlli, Dashboard) | Task 2 |
| DatabaseView (info DB, insight, registry, tabelle) | Task 3 |
| BuilderView (pill navigation, fixed actions) | Task 4 |
| ConditionManager ridisegnato (split, ricerca, sort) | Task 5 |
| DashboardView unificata (griglia, risultati live, progress) | Task 6 |
| Bottoni azione sempre visibili | Task 4, Task 5 |
| Integrazione e pulizia legacy | Task 7 |
