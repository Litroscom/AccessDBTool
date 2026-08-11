# Beta v8.0 — Redesign usabilità (ramo `beta`)

Ramo parallelo di sviluppo: la versione attuale (v7.4) resta su `main`.
Tutte le funzionalità esistenti rimangono valide: qui è cambiata solo la
**presentazione e l'organizzazione dell'interfaccia**, più i fix di
stabilità già inclusi nella v7.4 (vedi commit su `main`).

## Obiettivo

Un tool lineare e immediato: l'utente deve capire in 3 secondi
**dove sta, cosa può fare e qual è il passo successivo**.

## Cosa è cambiato

### 1. Navigazione chiara (App shell)
- Barra laterale verticale con **icone + etichette** (Database, Controlli,
  Dashboard, Monitor) e indicatore di versione: prima c'era una striscia
  laterale vuota di 44px più una barra superiore ridondante.
- **Header contestuale** per ogni pagina: titolo della sezione a sinistra,
  database attivo a destra (sempre visibile, aggiornato a ogni
  apertura/chiusura DB).

### 2. Tab Controlli: flusso lineare
- **Niente più accordion collassabile** che nascondeva configurazione
  essenziale: le sezioni sono sempre visibili e numerate in ordine di flusso:
  1. Configurazione del controllo
  2. Filtri aggiuntivi (facoltativi)
  3. Colonne da mostrare nel report
  4. Promemoria di aggiornamento (facoltativo)
- **Risultati incorporati nel tab Controlli**: esegui un controllo e i
  risultati compaiono subito sotto il modulo. Prima c'era un salto
  automatico al tab Dashboard (disorientante) e i risultati non erano
  visibili nello stesso contesto.
- Rimossi selettori morti "Tag" e "DB" dalla barra superiore del builder
  (non collegati a nulla).
- Hint guida nella barra azioni: "1) Scegli il tipo · 2) Configura ·
  3) Esegui (Alt+R)".

### 3. Risultati multi-view
- Il controller risultati ora notifica **più view contemporaneamente**
  (Controlli e Dashboard), senza più sovrascriversi.

### 4. Dashboard
- Messaggio guida quando non ci sono condizioni salvate.
- Filtro "Solo anomalie" corretto (vedi fix su main).

### 5. Controlli con logica propria
- Per "Condizione formula SQL" e "SE...ALLORA" la sezione filtri mostra un
  messaggio esplicativo invece di un builder vuoto fuorviante.

## Verifica
- 91 test di regressione verdi (suite completa `tests/test_logic_verification.py`).
- I 2 errori residui di `tests/smoke_qa.py` sono ambientali (manca
  `ttkbootstrap` e l'import di `.pyw` non funziona in WSL), preesistenti
  e non legati a questa branch.

## Versioning
- `constants.APP_VERSION = "8.0-beta"` (solo su `beta`; `main` resta 7.4).
