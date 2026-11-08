# AccessDBTool v8 — View persistenti (navigazione senza ricostruzione)

**Data:** 2026-11-08
**Base:** branch `beta` (commit `babe0b8`), versione `8.0-beta`
**Nuovo ramo:** `fix/view-persistenti`
**Dimensione:** modifica piccola/circoscritta (~150 righe su 7 file), non un progetto
**Stato:** design da approvare

---

## Obiettivo e perché

All'uso reale l'app risulta lenta nel passaggio da una pagina all'altra e
"perde" il lavoro fatto nel costruttore. Non è un problema di disegno grafico:
è che **ogni click sulla sidebar distrugge la pagina e la ricostruisce da zero**.
Lo stato dell'applicazione vive dentro i widget, quindi muore con loro.

Questo blocco non tocca l'estetica. Rende la navigazione immediata e fa
sopravvivere lo stato alle pagine, così che i blocchi successivi (bug
funzionali, ridisegno GUI) partano da una base che si comporta.

## Misura di partenza (misurata, non stimata)

Tempo di un cambio tab, con app avviata e nessun DB aperto
(`App` istanziata, `update()` forzato dopo ogni switch):

| Tab | 1ª visita | 2ª visita |
|---|---|---|
| Controlli | 543 ms | 382 ms |
| Dashboard | 594 ms | 332 ms |
| Monitor | 190 ms | — |
| Database | 170 ms | 274 ms |

Ogni click ricostruisce la pagina: 15 builder, selettore colonne, sezioni,
treeview, dialoghi figli. È qui che l'utente sente "ridimensionamenti frequenti".

## Cause individuate nel codice

1. **`AppController.switch_tab`** (`app/controllers/app_controller.py:34`)
   esegue `w.destroy()` su tutti i figli di `main_panel` e istanzia una view
   nuova a ogni cambio tab.
2. **`_wire_view_callbacks`** (`access_db_tool.pyw:341`) viene rieseguita a
   ogni switch e chiama `result_ctrl.set_results_callback(...)`, che
   **accoda** in una lista senza mai svuotarla (`result_controller.py:22`).
   Dopo N switch ci sono N callback che puntano a view distrutte: ogni
   risultato le invoca tutte. È una perdita di memoria e un rallentamento
   che cresce con l'uso.
3. **`switch_tab` azzera `state.active_builder`**: cambiare tab butta via il
   builder in corso, anche non salvato.
4. **`library_controller.open_manager`** (`library_controller.py:212`) passa
   `lambda: None` come refresh e `load_cond_into_builder` come callback di
   caricamento. `load_cond_into_builder` **cambia solo lo stato**: nessuna
   view viene toccata. "Carica" dal Gestore Condizioni non produce nulla di
   visibile — è il sintomo "gestione condizioni non funzionante".

## Approcci considerati

| | Approccio | Trade-off | Esito |
|---|---|---|---|
| **A** | Toppe mirate (riordino `load_condition`, callback ripuntate, niente reset di `active_builder`) | Costo minimo, rischio minimo. Lentezza invariata, la famiglia di bug resta | Scartato da solo |
| **B** | **View persistenti**: la view si crea una volta sola, il cambio tab è `pack_forget`/`pack` | Costo contenuto, elimina in un colpo lentezza + callback morte + stato perso. Richiede wiring fatto una volta per view | **Scelto** |
| **C** | Stato unico, view come renderer puri | Architettura corretta, ma rifacimento ampio e blocca la GUI per settimane | Rimandato al ridisegno |

**Perché B:** copre i tre quarti dei sintomi lamentati con un intervento
circoscritto, e la beta è già pronta ad accoglierlo — `ResultController`
notifica una lista di view (`_on_results_callbacks`), quindi il disegno
ammette più view vive contemporaneamente.

## Design

**Ciclo di vita delle view.** `App` mantiene `self.views: dict[str, ttk.Frame]`.
Creazione **pigra**: una view nasce alla prima visita al suo tab, poi resta viva
fino alla chiusura dell'app.

**Cambio tab.** `AppController.switch_tab` diventa:
1. `pack_forget()` della view attiva (se visibile);
2. creazione della view di destinazione se assente;
3. `pack(fill=BOTH, expand=True)` della view di destinazione;
4. hook di aggiornamento on-show;
5. stile dei pulsanti sidebar, titolo pagina, header DB.

**Wiring una volta sola.** Tutto ciò che oggi `_wire_view_callbacks` rifà a
ogni switch (controller iniettati, `set_results_callback`,
`set_log_callback`, `set_open_in_builder_callback`, callback monitor) viene
eseguito **alla creazione della view**. A ogni switch restano solo gli hook
di aggiornamento, che devono essere idempotenti.

**Hook di aggiornamento on-show** (uniformati a un metodo pubblico `refresh()`):
`DatabaseView.refresh()`, `BuilderView.refresh()`, `DashboardView.refresh()`
(alias pubblico dell'attuale `_refresh`), `MonitorView.refresh()`
(alias pubblico di `_refresh_state_label`). Questo è anche il punto in cui
`state.active_builder` non viene più azzerato: appartiene alla view Controlli,
che ora sopravvive.

**Gestore Condizioni.** Il callback di caricamento passato a
`ConditionManagerDialog` punta alla `BuilderView` viva
(`self.views["controls"].load_condition`) invece che al solo
`library_controller`. Il refresh post-modifica della lista punta a
`BuilderView.refresh_lib`. Spostamento su Controlli se il tab attivo è
diverso: `load_condition` apre il tab corretto via callback dell'`App`.

## Non-obiettivi

- Estetica, tema, spaziature, icone: blocco separato (ridisegno GUI).
- Completezza dei `set_config` dei 15 builder (bug "modifica condizioni"):
  blocco successivo, con test dedicati. Qui si garantisce solo che il builder
  non venga distrutto dal cambio tab.
- Build PyInstaller portabile.
- Passaggio allo stato unico (approccio C).

## Vincoli

- `ttkbootstrap 2.x`: una sola root viva per processo; nei test serve una root
  persistente di modulo (vedi `tests/smoke_qa.py`).
- I builder vanno creati **direttamente nel parent finale** — mai
  `pack(in_=...)` (skill `tkinter-pack-parent-mismatch`).
- Quoting identificatori ODBC invariato (skill `access-odbc-identifier-quoting`).
- I test esistenti devono restare verdi: `python -m unittest tests.test_logic_verification tests.smoke_qa`
  (131 + 16).

## Rischi

| Rischio | Mitigazione |
|---|---|
| Una view costruita senza DB aperto non si aggiorna quando il DB si apre dopo | hook `refresh()` on-show; `DatabaseView` già riceve `set_db_changed_callback` → va esteso a notificare le view vive |
| Memoria: 4 view vive con treeview | dimensioni trascurabili rispetto al beneficio; verifica con `refresh()` idempotente |
| Callback duplicate se un domani qualcuno rimette il wiring nello switch | `set_results_callback` resta idempotente per callback distinte; test che verifica che la lista **non cresca** dopo N switch |
| Ordine di impacchettamento dopo `pack_forget`/`pack` | una sola view visibile per volta in `main_panel`; nessun `side=` condiviso |

## Come si verifica

1. **Prestazioni**: cambio tab < 50 ms dopo la prima visita a ogni tab, misurato
   con lo stesso script che ha prodotto la tabella sopra.
2. **Nessuna callback aggiunta dallo switch**: `len(result_ctrl._on_results_callbacks)`
   invariato dopo 10 cambi tab.
3. **Stato conservato**: configurare un controllo, cambiare tab, tornare → i
   campi sono ancora popolati.
4. **Gestore Condizioni**: "Carica" da `Gestisci libreria` popola la
   `BuilderView` e porta il tab su Controlli.
5. **Regressione**: 131 + 16 test verdi; app avviabile con
   `Avvia_Tool.vbs`; i 4 tab si aprono e funzionano.
6. **DB reale** (`D:\daticirc\se\`, sola lettura, nessun dato stampato):
   aprire un DB, eseguire un controllo, popolare la dashboard.

## Cosa resta a chi implementa

- Nomi e firme esatte degli hook `refresh()` per view.
- Se la creazione pigra debba prevedere un segnaposto "caricamento".
- Come estendere `set_db_changed_callback` alle view vive (lista di listener
  o `refresh()` on-show sufficiente).
- Partizionamento dei test nuovi.

---

## Esito misurato (aggiunto a fine lavoro, 2026-11-08)

### Cosa ha consegnato il branch

Sei task, 147 test verdi (115 + 16 + 11 nuovi + 5 dalla correzione finale),
app avviabile, smoke su **copia** di `Datico.MDB` (33 tabelle scoperte, nessun
dato letto).

### Prestazioni: A/B reale, non stima

Stesso script, stessa macchina, finestra nascosta, 5 giri dopo riscaldamento,
mediane. Baseline = commit `cb26ea9` in worktree separato.

| Tab | switch prima | switch dopo | repaint prima | repaint dopo |
|---|---|---|---|---|
| Controlli | 201.0 ms | **3.3 ms** | 187.4 ms | 72.6 ms |
| Dashboard | 297.8 ms | **3.3 ms** | 104.5 ms | 68.2 ms |
| Monitor | 179.6 ms | **3.2 ms** | 43.6 ms | 41.4 ms |
| Database | 80.6 ms | **4.0 ms** | 37.5 ms | 35.8 ms |

`switch` = `_switch_tab` (la parte che il codice controlla). `repaint` =
`app.update()`, rendering di Tk.

**Onestà sui numeri:** il guadagno sulla parte che il codice controlla è di
15-25x e il criterio dei 50 ms è rispettato con margine (3-4 ms). Su **finestra
visibile** il repaint che segue al cambio è però *cresciuto* (da 242-610 ms a
324-932 ms): il totale percepito su questa macchina non è quindi chiaramente
migliore, e in alcune misure peggiore. `refresh()` on-show non è la causa
(misurato: 1196 vs 1110 ms con `refresh()` neutralizzato) — è il map/paint del
sottoalbero Tk che `pack_forget` + `pack` rimappa.

**Conseguenza:** la ricostruzione delle view è sparita e lo stato sopravvive
alle pagine (gli obiettivi di questo blocco), ma il costo residuo di Tk va
affrontato con una tecnica diversa — view impilate nella stessa cella `grid`
con `tkraise()` invece di unmap/remap — che è un esperimento a sé, non una
estensione di questo branch.

### Debito noto lasciato aperto

- Messaggio di stato: aprire un DB scrive "Monitor fermato: database cambiato"
  anche quando non c'è stato alcun cambio (sovrascrive "DB aperto: …").
- Un cambio DB reale notifica due volte (prima e dopo la connessione) → refresh
  doppio, idempotente ma evitabile.
- `state.status.set(...)` e `filedialog` possono essere toccati da thread worker
  (`db_controller.py:48`, `batch_controller.py:196`) — preesistenti, fuori scope.
- `ensure_active_builder_from_result` è codice morto senza chiamanti.
- `_run_profiler_from_view` aggiorna solo la view attiva, non tutte.

---

## Esperimento successivo: view impilate + `tkraise()` (branch `exp/tkraise-stack`)

L'ipotesi lasciata aperta sopra è stata verificata e **confermata**: il costo del
repaint non era il "ridisegnare", era il **rimappare** (`pack_forget` smonta il
sottoalbero, `pack` lo rimonta).

**Meccanismo nuovo:** le view si agganciano tutte alla stessa cella
(`grid(row=0, column=0, sticky="nsew")`, con `grid_rowconfigure/grid_columnconfigure`
pesati sull'host) e il cambio tab è `view.tkraise()`. Nessun unmap/remap: i
sottotree restano montati e cambia solo l'ordine di impilamento. La view in cima
è l'ultimo figlio in `main_panel.winfo_children()`.

**A/B a tre vie** (stessa macchina, finestra visibile, 5 giri, mediane,
switch + repaint successivo):

| Tab | prima del blocco (ricostruzione) | view persistenti `pack` | **impilate + `tkraise`** |
|---|---|---|---|
| Controlli | 751 ms | 618 ms | **115 ms** |
| Dashboard | 619 ms | 459 ms | **104 ms** |
| Monitor | 339 ms | 201 ms | **62 ms** |
| Database | 362 ms | 248 ms | **82 ms** |

Il `pack` da solo non bastava a rendere il cambio tab "immediato": guadagnava
sulla logica di switch (3-4 ms) ma il repaint peggiorava. Con `tkraise` il
repaint scende a 57-105 ms e il totale è 6-7x il baseline.

Suite completa verde (147 test) anche con il nuovo meccanismo; le asserzioni
"esattamente una view impacchettata" sono state sostituite da "la view attiva è
quella in cima" e "tutte le view restano montate".
