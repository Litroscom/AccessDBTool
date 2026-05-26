# AccessDBTool v7.2 — Architecture & UX Redesign

**Data:** 2026-05-26
**Versione target:** 7.2
**Base:** feature/v7-ui (v7.1 con sezioni BuilderView completate)

---

## Obiettivo

Riorganizzare l'architettura (split della God class `App` in controller dedicati), ridisegnare Dashboard e Builder per un flusso batch-first, e uniformare l'estetica eliminando dead code v5.

---

## 1. Architettura: Split della God Class

**File attuale:** `access_db_tool.pyw` — 2231 linee, 98 metodi sulla classe `App`.

### Nuova struttura

```
access_db_tool.pyw              → App.__init__, mainloop, menu, routing tab, _quit
app/
  controllers/
    app_controller.py           → routing navigazione, stato globale, status bar
    db_controller.py            → open/close DB, registry, risoluzione path/label
    batch_controller.py         → batch multi-db, progress live, error recovery
    result_controller.py        → esecuzione singola, show_results, eccezioni, bulk replace
    library_controller.py       → save/load/update/delete/import/export condizioni
  state.py                      → stato condiviso (db, active_builder, current_result, ...)
views/
  builder_view.py               → ridisegnato (accordion sections, vedi §3)
  database_view.py              → invariato
  dashboard_view.py             → ridisegnato (split + log live, vedi §2)
  condition_manager_view.py     → invariato
  results_view.py               → arricchito (pannello indipendente, vedi §5)
ui_components.py                → invariato (rimosso ConditionManager legacy, vedi §4)
theme_config.py                 → invariato
```

### Principi

- Ogni controller ha uno scopo preciso e un'interfaccia chiara.
- Le viste ricevono i controller via dependency injection (passati nel costruttore).
- Le viste non chiamano più `self.app._metodo_a_caso()` — chiamano metodi del controller specifico.
- `state.py` è un oggetto condiviso immutabile: le viste leggono, i controller scrivono.

### Mappatura metodi App → controller

| Metodo attuale | Destinazione | Note |
|---|---|---|
| `_open_db`, `_close_db`, `_connect_active_database`, `_resolve_database_path`, `_ensure_active_database_for_label`, `_suggest_database_label`, `_register_database_reference`, `_sync_open_database_ui` | `db_controller.py` | |
| `_run_all_batch`, `_batch_worker`, `_run_batch_for_database`, `_mark_batch_row_running`, `_finalize_batch_row`, `_cancel_batch`, `_prepare_batch_database_paths` | `batch_controller.py` | Aggiunto log live e progress |
| `_run_current`, `_execute_task`, `_run_selected_dashboard_check`, `_start_dashboard_execution`, `_execute_dashboard_task`, `_complete_dashboard_task`, `_complete_dashboard_task_error`, `_show_results` | `result_controller.py` | `_show_results` non switcha più tab |
| `_save_to_lib`, `_update_to_lib`, `_save_cond`, `_load_from_lib`, `_refresh_lib`, `_load_cond_into_builder`, `_open_manager`, `_export_conditions`, `_import_conditions`, `_filter_conditions_by_tag`, `_refresh_tag_filters`, `_database_label_for_condition`, `_prepare_condition_for_storage` | `library_controller.py` | |
| `_switch_tab`, `_go_to_tab`, `_poll_monitor`, `_handle_monitor_msg`, `_start_monitor`, `_stop_monitor` | `app_controller.py` | |
| `_build_left_panel`, `_build_tab_*`, `_configure_v5_theme`, `v5_colors`, `_build_shortcut_legend` | ELIMINATO | Dead code v5 |
| `_mark_shortcut`, `_shortcut_legend_text`, `_attach_alt_shortcut` | `ui_helpers.py` | Nuovo file helper |
| `_show_res_menu`, `_add_selected_to_exceptions`, `_bulk_replace_results`, `_edit_res_record` | `result_controller.py` | |

### Non in scope

- Modifiche al backend (`engines.py`, `db_manager.py`, `storage.py`, `monitor_engine.py`, `data_profiler.py`)
- Modifiche ai test esistenti
- Sostituzione di `ConditionSaveDialog` (ui_components.py)

---

## 2. Dashboard ridisegnata (flusso batch)

### Layout

DashboardView occupa l'intero tab con split orizzontale:

```
┌──────────────────────────────────────────────────────────┐
│ toolbar: [▶ Esegui Tutti] [▶ Esegui Selez.] [☐ Solo anom.] [🔍 Cerca] │
│ filtri:  [Tag ▾] [DB ▾] [Gruppo ▾]                                       │
├──────────────────────────────┬───────────────────────────┤
│  CONTROLLI (weight=1)        │  RISULTATI (weight=2)      │
│  Treeview a 5 colonne:       │                             │
│  #  Nome    DB   R.  Stato   │  Titolo controllo + Treeview│
│                              │  risultati (dinamico)      │
│                              │                             │
│                              │  [📤 CSV] [✏ Modifica]     │
├──────────────────────────────┴───────────────────────────┤
│  ═══════ Progress bar  ████████░░░  75%  3/12 controlli  │
│  LOG: [timestamps] Dup_anni su Datico.mdb → OK (0)       │
│  LOG: [timestamps] Sim_nomi su Datico.mdb → 12 anomalie  │
└──────────────────────────────────────────────────────────┘
```

### Comportamento

- **Click singolo** su un controllo → carica l'ultimo risultato nel pannello destro (se disponibile)
- **Doppio click** → riesegue quel controllo e mostra i risultati nel pannello destro
- **"Esegui Tutti"** → batch: progress bar si riempie, log scrolla in tempo reale, ogni riga della tabella si aggiorna al completamento
- **"Esegui Selezionato"** → esegue il controllo selezionato (singolo click + conferma se già eseguito)
- **Filtri**: Tag, DB, Gruppo — dropdown popolati dinamicamente, filtrano in tempo reale senza refresh manuale
- **Solo anomalie**: checkbox che mostra solo controlli con conteggio > 0 (o stato "error" / "mai eseguito")
- **Cerca**: campo testo che filtra per nome controllo (sottostringa)
- **Treeview controlli** colonne: #, Nome, Database, Risultati (conteggio), Stato
- **Tag Treeview**: `error` (rosso scuro, >0 anomalie), `ok` (verde scuro, 0 anomalie), `running` (giallo, in corso), `idle` (grigio, mai eseguito)
- **Log live**: Listbox/ScrolledText in fondo, max 100 righe, scroll automatico, mostra timestamp + nome controllo + DB + esito

### Progress bar

- Durante il batch: `maximum = len(batch_items)`, `value = completati + errori`
- Label: "N/M controlli" aggiornato in tempo reale
- A batch finito: barra verde piena per 2 secondi, poi si resetta

### Risultati (pannello destro)

- Il Treeview risultati usa tutte le colonne del result set
- Azioni in basso: Esporta CSV, Modifica record (se supportato), Apri nel builder (carica il controllo nel tab Controlli)
- Se nessun controllo è selezionato: messaggio "Seleziona un controllo per vedere i risultati"

---

## 3. Builder: UX semplificata (accordion)

### Layout

Sostituzione delle pill con pannelli accordion espandibili:

```
┌──────────────────────────────────────────────────────┐
│ Tipo Analisi: [▾]  Tag: [▾]  DB: [▾]                │
├──────────────────────────────────────────────────────┤
│  ▸ BASE                                               │
│    [contenuto del builder specifico per tipo]         │
│                                                        │
│  ▸ FILTRI — 2 condizioni attive                       │
│  ▸ ESCLUSIONI — 1 esclusione attiva                  │
│  ▸ COLONNE REPORT — 5 selezionate                     │
│  ▸ PERIODICITÀ — Mensile (ultimo agg: 12/05/2025)    │
│                                                        │
├──────────────────────────────────────────────────────┤
│ Libreria: [▾] [Carica] [Gestisci] [Gruppi]           │
├──────────────────────────────────────────────────────┤
│ [Pulisci] [💾 Salva] [♻ Aggiorna]     [▶ Esegui]    │
└──────────────────────────────────────────────────────┘
```

### Comportamento accordion

- **Base**: sempre espansa. Contiene il builder specifico del tipo analisi (SimilarityBuilder, CrossTableBuilder, ecc.)
- **Filtri, Esclusioni, Colonne Report, Periodicità**: collassate per default
- **Badge conteggio**: ogni header mostra quante condizioni/esclusioni sono attive (es. "FILTRI — 2 condizioni attive")
- **Click sull'header**: espande/comprime la sezione
- **Sync**: quando l'utente comprime una sezione, i dati vengono sincronizzati nel builder attivo (stesso meccanismo `_sync_builder_from_sections`)
- **Nessuna ricostruzione widget**: le sezioni vengono create una volta sola e mostrate/nascoste con `pack()`/`pack_forget()` invece di `destroy()`

### Implementazione tecnica

- `_build_section_*()` diventano metodi che creano un `ttk.LabelFrame` con un header cliccabile
- `_toggle_section(section_id)` gestisce expand/collapse
- Le sezioni collassate mantengono i widget in vita (no destroy, no reparenting)
- Il builder Base rimane sempre nel suo `frm_dyn`, visibile nella sezione Base espansa
- `col_selector` vive nella sezione Colonne Report
- I widget MultiConditionBuilder di Filtri/Esclusioni vengono creati al primo expand e mantenuti

---

## 4. Libreria: gestione condizioni unificata

### Rimozione ConditionManager legacy

- `ConditionManager` in `ui_components.py` (~1000 linee) viene rimosso
- Resta solo `ConditionManagerDialog` in `views/condition_manager_view.py`
- `_open_manager()` in `library_controller.py` importa e apre solo `ConditionManagerDialog`

### ConditionManagerDialog arricchito

Aggiunte funzionalità:

- **Multi-selezione**: Treeview con `selectmode="extended"` e checkbox visive (tag configure per checked/unchecked). Le operazioni (elimina, esporta, assegna tag, verifica integrità) agiscono su tutti gli elementi selezionati
- **Preview pannello destro**: mostra nome, tipo, tag, DB, tabella, periodo. Click singolo = preview, doppio click = carica nel builder e chiudi
- **Operazione "Assegna tag..."**: pulsante che apre un dialog `simpledialog.askstring("Nuovo tag")` e lo applica a tutte le condizioni selezionate
- **Footer**: "N condizioni totali | Tag: X (Y), Z (W)..." — conteggio e breakdown
- **Layout**: split paned window sinistra/destra (già presente), sinistra = lista con checkbox, destra = dettaglio + azioni

### Non in scope

- Drag & drop tra gruppi (rimandato a v7.3)
- Ricerca full-text su descrizione (la ricerca per nome/tag è già presente)

---

## 5. Vista Risultati indipendente

### Nuovo ResultsView

Sostituisce l'attuale `ResultsView` (84 linee, solo Treeview) con un pannello ricco:

```
┌──────────────────────────────────────────────────────┐
│ [🔍 Filtra risultati...]  {titolo} — {count} record   │
├──────────────────────────────────────────────────────┤
│  Treeview risultati (colonne dinamiche)               │
│  con scrollbar verticale e orizzontale                │
├──────────────────────────────────────────────────────┤
│ [📤 Esporta CSV] [✏ Modifica record]                  │
│ [🔎 Sostituzione massiva] [🚫 Aggiungi a esclusioni]  │
│ [🔗 Apri nel builder]                                 │
└──────────────────────────────────────────────────────┘
```

### Comportamento

- **Accessibile da qualsiasi tab**: eseguendo un controllo dal builder, il ResultsView si apre come pannello overlay/side-panel o come sezione espandibile nel builder stesso
- **Non forza switch tab**: `_show_results` non chiama più `_switch_tab("dashboard")`
- **Tag righe**: `error` per righe >0, `ok` per 0 (se appropriato)
- **Azioni**: Esporta CSV, Modifica record, Sostituzione massiva, Aggiungi a esclusioni (tasto dedicato, non solo click destro), Apri nel builder
- **Filtro live**: campo testo in alto, filtra righe in tempo reale per sottostringa

### Integrazione con Dashboard

- Nella dashboard, il pannello risultati a destra è il ResultsView
- Nel builder, i risultati appaiono in un pannello a scomparsa (tipo drawer) dalla destra, senza cambiare tab

---

## 6. Estetica e pulizia

### Dead code eliminato

File e metodi rimossi:
- `_build_left_panel` (~45 linee)
- `_build_tab_insights` (~30 linee)
- `_build_tab_dashboard` (~45 linee)
- `_build_tab_builder` (~80 linee, v5 builder)
- `_build_tab_results` (~30 linee)
- `_build_tab_monitor` (~20 linee)
- `_configure_v5_theme` (~15 linee)
- `v5_colors` dict e ogni suo riferimento (usato solo da metodi v5 dead code)
- `_build_shortcut_legend` (~10 linee)
- `ConditionManager` in `ui_components.py` (~1000 linee)

### Home screen

Riscritta con ttkbootstrap, niente raw tk:
- Sfondo: stile `dark` di ttkbootstrap
- Titolo: "AccessDBTool v7" con versione aggiornata
- Due pulsanti grandi: "Costruttore" e "Dashboard" con stile ttkbootstrap
- Testo: "Apri un database per iniziare"
- Shortcut: link "Mostra shortcut (Alt+/)" che apre un dialog

### Sidebar

- Icone cliccabili per i 3 tab (🗄 ⚙ 📊) con `bootstyle="secondary-link"` e tooltip
- Larghezza 44px invariata
- Icona attiva evidenziata con `bootstyle="primary-link"`

### Coerenza visiva

- Padding uniforme: 8px per tutti i container principali (LabelFrame, Frame con padding)
- `Listbox` (tabella in DatabaseView) → `Treeview` per ereditare tema scuro
- Tag colore Treeview: usare stili ttkbootstrap `bootstyle` o colori dal tema invece di codici RGB hardcodati
- Font: `Segoe UI` consistente (10 testi, 9 label, 8 hint/italic)
- Badge conteggio su sezioni accordion con font ridotto e colore secondario

### Status bar

```
[Pronto]                                           [MONITOR OFF] [DB: Nome.mdb]
```

- Testo stato a sinistra
- Indicatore monitor a destra (con `bootstyle="danger"` / `bootstyle="success"`)
- Label DB attivo visibile sempre a destra

### Shortcut

- Legenda rimossa dal DatabaseView
- Nuovo dialog "Scorciatoie" accessibile via `Alt+/` o menu `?` → `Scorciatoie...`
- Il dialog mostra una tabella a 2 colonne (Tasto, Azione) in un Toplevel modale

---

## Non in scope

- Riscrittura del backend (engines, db_manager, storage, monitor_engine, data_profiler)
- Aggiunta di nuovi tipi di controllo/analisi
- Test automatici delle nuove viste (da fare in task separato dopo verifica Windows)
- Internazionalizzazione (i18n)
- Build portable (rimane invariato `build_portable.py`)
- Drag & drop tra gruppi nella libreria

---

## Rischio e mitigazione

| Rischio | Mitigazione |
|---------|-------------|
| Impossibilità di testare tkinter su Linux | Commit piccoli e frequenti, un modulo controller alla volta. Test su Windows dopo ogni commit. |
| Regressioni su batch multi-db | Il batch controller è estratto ma la logica interna (`_batch_worker`, `_run_batch_for_database`) resta identica |
| Accordion introduce nuovi bug di layout | Usare `pack()`/`pack_forget()` invece di `destroy()`, testare ogni sezione singolarmente |
| Rimozione ConditionManager legacy rompe referenze | Verificare con grep che nessun altro file importi `ConditionManager` da `ui_components.py` |
