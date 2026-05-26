# BuilderView Sezioni Filtri, Esclusioni, Periodicità — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completare le 3 sezioni placeholder del BuilderView con editor funzionanti che interagiscono col builder attivo.

**Architecture:** Le sezioni leggono/scrivono configurazione dal builder attivo via `get_config()`/`set_config()`. Un meccanismo `_sync_builder_from_sections()` propaga le modifiche quando l'utente cambia pill.

**Tech Stack:** Python 3, tkinter, ttkbootstrap

---

## File Structure

| File | Modifica |
|------|----------|
| `views/builder_view.py` | Aggiungere `_build_section_filtri`, `_build_section_esclusioni`, `_build_section_periodicita`, `_sync_builder_from_sections` |
| `ui_components.py` | Nessuna modifica (riuso MultiConditionBuilder esistente) |

---

## Task 1: Meccanismo sync + Sezione Filtri

**Files:**
- Modify: `views/builder_view.py`

- [ ] **Step 1: Aggiungi `_sync_builder_from_sections` a BuilderView**

Prima del cambio pill, salva le modifiche fatte nelle sezioni Filtri/Esclusioni/Periodicità nel builder attivo.

Aggiungi dopo `_build_section_periodicita()`:

```python
def _sync_builder_from_sections(self):
    if not self.app.active_builder:
        return
    try:
        config = self.app.active_builder.get_config()
    except Exception:
        return
    if hasattr(self, "_filtro_widget"):
        filtri = self._filtro_widget.get_conditions()
        config["conditions"] = filtri
    if hasattr(self, "_esclusioni_widget"):
        esclusioni = self._esclusioni_widget.get_conditions()
        if esclusioni:
            config["exclude_conditions"] = esclusioni
        elif "exclude_conditions" in config:
            del config["exclude_conditions"]
    if hasattr(self, "_periodicita_data"):
        config.update(self._periodicita_data)
    try:
        self.app.active_builder.set_config(config)
    except Exception:
        pass
```

- [ ] **Step 2: Modifica `_show_section` per chiamare sync prima del cambio pill**

Sostituisci il metodo esistente:

```python
def _show_section(self, section_id):
    # Sync modifiche dal builder attuale PRIMA di cambiare sezione
    self._sync_builder_from_sections()

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
```

- [ ] **Step 3: Implementa `_build_section_filtri`**

Sostituisci la sezione placeholder:

```python
def _build_section_filtri(self):
    if not self.app.active_builder:
        ttk.Label(self.section_content, text="Configura prima la sezione Base.").pack(pady=20)
        return
    try:
        config = self.app.active_builder.get_config()
    except Exception:
        ttk.Label(self.section_content, text="Questo tipo di controllo non supporta filtri aggiuntivi.").pack(pady=20)
        return

    table = config.get("table", "")
    conditions = config.get("conditions", [])

    from ui_components import MultiConditionBuilder
    filtro = MultiConditionBuilder(
        self.section_content, self.app.db,
        on_table_change=self.app._on_builder_table_change,
        title="Filtri (AND/OR)"
    )
    filtro.pack(fill=tk.BOTH, expand=True)
    filtro.set_config({
        "table": table,
        "conditions": conditions,
    })
    # Rimuovi/exclude la parte esclusioni dal MultiConditionBuilder
    # Nascondi il separatore e la sezione esclusioni
    self._filtro_widget = filtro
```

- [ ] **Step 4: Commit**

```bash
git add views/builder_view.py
git commit -m "feat(v7): implement BuilderView Filtri section with condition editor"
```

---

## Task 2: Sezione Esclusioni

**Files:**
- Modify: `views/builder_view.py`

- [ ] **Step 1: Implementa `_build_section_esclusioni`**

Sostituisci la sezione placeholder:

```python
def _build_section_esclusioni(self):
    if not self.app.active_builder:
        ttk.Label(self.section_content, text="Configura prima la sezione Base.").pack(pady=20)
        return
    try:
        config = self.app.active_builder.get_config()
    except Exception:
        ttk.Label(self.section_content, text="Questo tipo di controllo non supporta esclusioni.").pack(pady=20)
        return

    table = config.get("table", "")
    exclude_conditions = config.get("exclude_conditions", [])

    from ui_components import MultiConditionBuilder
    excl = MultiConditionBuilder(
        self.section_content, self.app.db,
        on_table_change=self.app._on_builder_table_change,
        title="Esclusioni (opzionale)"
    )
    excl.pack(fill=tk.BOTH, expand=True)
    excl.set_config({
        "table": table,
        "conditions": exclude_conditions,
    })
    self._esclusioni_widget = excl
```

- [ ] **Step 2: Commit**

```bash
git add views/builder_view.py
git commit -m "feat(v7): implement BuilderView Esclusioni section"
```

---

## Task 3: Sezione Periodicità

**Files:**
- Modify: `views/builder_view.py`

- [ ] **Step 1: Implementa `_build_section_periodicita`**

Sostituisci la sezione placeholder. Usa lo stesso pattern UI di `ConditionSaveDialog`:

```python
def _build_section_periodicita(self):
    if not self.app.active_builder:
        ttk.Label(self.section_content, text="Configura prima la sezione Base.").pack(pady=20)
        return
    try:
        config = self.app.active_builder.get_config()
    except Exception:
        config = {}

    import ui_components
    from ui_components import PERIODIC_REVIEW_CYCLE_CHOICES

    frame = ttk.LabelFrame(self.section_content, text="Promemoria Aggiornamento Periodo", padding=12)
    frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    self._var_periodic_enabled = tk.BooleanVar(
        value=bool(config.get("periodic_review_enabled", False))
    )
    self._var_periodic_cycle = tk.StringVar(
        value=self._cycle_display_from_key(config.get("periodic_review_cycle", "monthly"))
    )
    self._var_periodic_note = tk.StringVar(
        value=config.get("periodic_review_note", "")
    )
    self._var_periodic_last_ack = tk.StringVar(
        value=config.get("periodic_review_last_ack", "")
    )

    chk = ttk.Checkbutton(
        frame,
        text="Richiede aggiornamento periodico dei filtri",
        variable=self._var_periodic_enabled,
        command=self._toggle_periodic_fields,
    )
    chk.pack(anchor=tk.W, pady=(0, 10))

    cycle_row = ttk.Frame(frame)
    cycle_row.pack(fill=tk.X, pady=4)
    ttk.Label(cycle_row, text="Frequenza:").pack(side=tk.LEFT)
    self._cmb_periodic_cycle = ttk.Combobox(
        cycle_row,
        textvariable=self._var_periodic_cycle,
        state="readonly" if self._var_periodic_enabled.get() else tk.DISABLED,
        width=18,
        values=[label for label, _key in PERIODIC_REVIEW_CYCLE_CHOICES],
    )
    self._cmb_periodic_cycle.pack(side=tk.LEFT, padx=(8, 0))

    note_row = ttk.Frame(frame)
    note_row.pack(fill=tk.X, pady=(8, 4))
    ttk.Label(note_row, text="Nota promemoria:").pack(anchor=tk.W)
    self._ent_periodic_note = ttk.Entry(
        frame, textvariable=self._var_periodic_note,
        state=tk.NORMAL if self._var_periodic_enabled.get() else tk.DISABLED,
    )
    self._ent_periodic_note.pack(fill=tk.X, pady=(2, 0))

    last_ack_text = self._var_periodic_last_ack.get()
    if last_ack_text:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(last_ack_text)
            last_ack_text = dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
    else:
        last_ack_text = "Mai"

    self._lbl_last_ack = ttk.Label(
        frame, text=f"Ultimo aggiornamento: {last_ack_text}",
        foreground="gray", font=("", 8, "italic"),
    )
    self._lbl_last_ack.pack(anchor=tk.W, pady=(10, 4))

    btn_mark = ttk.Button(
        frame, text="Segna come aggiornato ora",
        command=self._mark_periodic_ack,
        bootstyle="info-outline",
    )
    btn_mark.pack(anchor=tk.W, pady=4)

    ttk.Label(
        frame,
        text="Esempio: aggiornare il mese corrente prima di eseguire il batch.",
        foreground="gray", font=("", 8),
    ).pack(anchor=tk.W, pady=(4, 0))

    self._periodicita_data = {}
```

- [ ] **Step 2: Aggiungi metodi helper per la sezione Periodicità**

```python
def _cycle_display_from_key(self, cycle):
    normalized = str(cycle or "").strip().lower()
    for label, key in ui_components.PERIODIC_REVIEW_CYCLE_CHOICES:
        if key == normalized:
            return label
    return ui_components.PERIODIC_REVIEW_CYCLE_CHOICES[-1][0]

def _cycle_key_from_display(self):
    current = self._var_periodic_cycle.get().strip()
    for label, key in ui_components.PERIODIC_REVIEW_CYCLE_CHOICES:
        if label == current:
            return key
    return "monthly"

def _toggle_periodic_fields(self):
    enabled = self._var_periodic_enabled.get()
    self._cmb_periodic_cycle.configure(
        state="readonly" if enabled else tk.DISABLED
    )
    self._ent_periodic_note.configure(
        state=tk.NORMAL if enabled else tk.DISABLED
    )

def _mark_periodic_ack(self):
    from datetime import datetime
    now = datetime.now().isoformat()
    self._var_periodic_last_ack.set(now)
    self._lbl_last_ack.config(
        text=f"Ultimo aggiornamento: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    self.status.set("Aggiornamento periodico segnato come completato.")
```

- [ ] **Step 3: Aggiorna `_periodicita_data` nel sync**

Assicurati che in `_sync_builder_from_sections`, quando si raccoglie `_periodicita_data`, vengano incluse le chiavi corrette. Nel `_build_section_periodicita`, inizializza `_periodicita_data` a `{}` e popolala ogni volta che si esce dalla sezione.

In `_sync_builder_from_sections`, dopo il blocco `_periodicita_data`:

```python
if hasattr(self, "_var_periodic_enabled"):
    enabled = self._var_periodic_enabled.get()
    self._periodicita_data = {
        "periodic_review_enabled": enabled,
        "periodic_review_cycle": self._cycle_key_from_display() if enabled else "",
        "periodic_review_note": self._var_periodic_note.get().strip() if enabled else "",
        "periodic_review_last_ack": self._var_periodic_last_ack.get() if enabled else "",
    }
if hasattr(self, "_periodicita_data"):
    config.update(self._periodicita_data)
```

- [ ] **Step 4: Commit**

```bash
git add views/builder_view.py
git commit -m "feat(v7): implement BuilderView Periodicità section with periodic review editor"
```

---

## Task 4: Verifica

- [ ] **Step 1: Esegui i test esistenti per assicurarsi che non si siano rotti**

```bash
python3 -m unittest tests/test_logic_verification.py -v 2>&1 | head -40
```

Expected: tutti i test passano (backend invariato).

- [ ] **Step 2: Verifica import del modulo aggiornato**

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from views.builder_view import BuilderView
from ui_components import MultiConditionBuilder, PERIODIC_REVIEW_CYCLE_CHOICES
print('All imports OK - BuilderView sections ready')
"
```

- [ ] **Step 3: Commit finale**

```bash
git add -A
git commit -m "chore(v7): verify BuilderView sections implementation"
```

---

## Self-Review

| Requisito spec | Coperto da |
|----------------|------------|
| Sezione Filtri con editor condizioni AND/OR | Task 1 |
| Sezione Esclusioni con editor exclusion | Task 2 |
| Sezione Periodicità con periodic review UI | Task 3 |
| Sync dati tra sezioni via get_config/set_config | Task 1 (Step 1) |
| Compatibilità builder che non supportano set_config | Task 1 (Step 3, try/except) |
| Gestione stato checkbox enable/disable periodic fields | Task 3 (Step 2, _toggle_periodic_fields) |
