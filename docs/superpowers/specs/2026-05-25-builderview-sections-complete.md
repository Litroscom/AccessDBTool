# AccessDBTool v7 — BuilderView: Completamento sezioni Filtri, Esclusioni, Periodicità

**Data:** 2026-05-25
**Versione target:** 7.1
**Base:** v7.0 (feature/v7-ui)

---

## Obiettivo

Completare le tre sezioni placeholder del BuilderView che attualmente mostrano solo "(in arrivo)":

| Sezione | Stato attuale | Target |
|---------|-------------|--------|
| Filtri | `ttk.Label(..., text="Filtri condizioni (in arrivo)")` | Editor condizioni AND/OR per il builder attivo |
| Esclusioni | `ttk.Label(..., text="Esclusioni (in arrivo)")` | Editor esclusioni per il builder attivo |
| Periodicità | `ttk.Label(..., text="Configurazione periodicità (in arrivo)")` | Pannello promemoria aggiornamento periodico |

---

## Architettura

### Principio guida

Le sezioni **non** contengono UI duplicata. Invece, leggono e scrivono la configurazione dal builder attivo (attraverso `get_config()` / `set_config()`), sincronizzandosi ogni volta che l'utente cambia pill.

### Flusso dati

```
User modifica Filtri → set_config({conditions: [...]}) → builder attivo
User passa a Base → get_config() → mostra builder con dati aggiornati
User passa a Esclusioni → get_config() → mostra exclude_conditions correnti
```

### Interfaccia comune attesa dal builder

Tutti i builder supportano già queste chiavi in `get_config()`/`set_config()`:
- `conditions` → lista di `{column, operator, value, logic}`
- `exclude_conditions` → stessa struttura
- `periodic_review_enabled`, `periodic_review_cycle`, `periodic_review_note`, `periodic_review_last_ack`

---

## Componenti

### 1. Sezione Filtri

Un frame che contiene il `MultiConditionBuilder` leggero:

- **Tabella sorgente**: letta dal builder attivo (se presente in `get_config()["table"]`)
- **Colonne**: caricate dal DB se connesso
- **Operatori**: elenco standard da `constants.OPERATORS`
- **Condizioni esistenti**: precaricate da `get_config()["conditions"]`

Entry point in `builder_view.py:BuiderView._build_section_filtri()`:

```python
def _build_section_filtri(self):
    if not self.app.active_builder:
        ttk.Label(self.section_content, text="Configura prima la sezione Base.").pack()
        return
    config = self.app.active_builder.get_config()
    # Crea MultiConditionBuilder leggero per i soli filtri
    filtro = MultiConditionBuilder(
        self.section_content, self.app.db,
        on_table_change=self.app._on_builder_table_change,
        title="Filtri (AND/OR)"
    )
    filtro.pack(fill=tk.BOTH, expand=True)
    filtro.set_config({
        "table": config.get("table", ""),
        "conditions": config.get("conditions", []),
    })
    self._filtro_widget = filtro  # salvato per sync
```

### 2. Sezione Esclusioni

Stesso pattern ma per `exclude_conditions`:

- **Tabella sorgente**: dalla configurazione del builder
- **Colonna predefinita per esclusioni**: come già implementato in `MultiConditionBuilder.get_exception_column()` (cerca PK per nome: "ID", "Codice", ecc.)
- **Condizioni di esclusione**: precaricate da `get_config()["exclude_conditions"]`
- **Tooltip guida**: "Le esclusioni rimuovono record che soddisfano queste regole"

```python
def _build_section_esclusioni(self):
    if not self.app.active_builder:
        ttk.Label(..., text="Configura prima la sezione Base.").pack()
        return
    config = self.app.active_builder.get_config()
    excl = MultiConditionBuilder(
        ..., title="Esclusioni (opzionale)"
    )
    excl.set_config({
        "table": config.get("table", ""),
        "conditions": config.get("exclude_conditions", []),
    })
    self._esclusioni_widget = excl
```

### 3. Sezione Periodicità

Pannello ispirato a `ConditionSaveDialog` ma standalone:

- **Checkbox**: "Richiede aggiornamento periodico"
- **Combobox frequenza**: Giornaliero / Settimanale / Mensile
- **Entry nota**: promemoria personalizzato
- **Label ultimo aggiornamento**: mostra `periodic_review_last_ack`
- **Pulsante "Segna come aggiornato"**: setta `last_ack` a `datetime.now()`

```python
def _build_section_periodicita(self):
    if not self.app.active_builder:
        ttk.Label(...).pack()
        return
    config = self.app.active_builder.get_config()
    # UI periodic review qui
```

### Salvataggio dei cambiamenti

Quando l'utente torna alla sezione **Base**, le modifiche in Filtri/Esclusioni/Periodicità devono essere applicate al builder attivo. Meccanismo:

```python
def _show_section(self, section_id):
    # 1. Sync: salva modifiche dal builder attuale PRIMA di cambiare sezione
    self._sync_builder_from_sections()
    # 2. Cambia pill
    for sid, btn in self.pill_buttons.items():
        btn.configure(bootstyle="secondary-outline")
    self.pill_buttons[section_id].configure(bootstyle="primary")
    # 3. Ricostruisci sezione
    for w in self.section_content.winfo_children():
        w.destroy()
    getattr(self, f"_build_section_{section_id}")()
```

Dove `_sync_builder_from_sections()`:

```python
def _sync_builder_from_sections(self):
    if not self.app.active_builder:
        return
    config = self.app.active_builder.get_config()
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
    self.app.active_builder.set_config(config)
```

---

## Casi particolari

### Builder senza supporto `get_config()`/`set_config()`
Solo i builder che non implementano `set_config()` (FormulaBuilder, ecc.) mostreranno un messaggio "Questo tipo di controllo non supporta filtri aggiuntivi."

### Tabella non selezionata
Filtri/Esclusioni mostrano "Seleziona prima una tabella nella sezione Base" con la combobox disabilitata.

### Builder con condizioni già incorporate (SimilarityBuilder, DuplicateBuilder)
Questi builder hanno già una sezione filtri propria. La sezione Filtri della pill funge da **livello aggiuntivo** e si sincronizza con il builder.

---

## Non in scope

- Modificare i builder esistenti per rimuovere le loro condizioni incorporate (si può fare in v7.2)
- Rewrite dell'intero `ui_components.py`
- Test automatici delle nuove sezioni (aggiunti in task separato)
