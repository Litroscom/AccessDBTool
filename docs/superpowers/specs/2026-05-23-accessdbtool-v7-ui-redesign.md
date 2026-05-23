# AccessDBTool v7 — UI Redesign

**Data:** 2026-05-23  
**Versione target:** 7.0  
**Base:** v6.0 (modulare, funzionante)  
**Stato:** Design approvato, da implementare in ramo separato

---

## Obiettivo

Riprogettare l'interfaccia utente della AccessDBTool con **ttkbootstrap** e layout fluido, risolvendo i problemi di:
- Bottoni azione che spariscono sotto la finestra
- Condition Manager mal dimensionato
- Dashboard con troppe colonne e informazioni frammentate
- Builder con scrolling eccessivo e campi sparsi
- Esperienza complessivamente "ingombrante"

---

## Stack tecnico

| Componente | Scelta | Motivazione |
|---|---|---|
| UI Framework | **ttkbootstrap** | Tema moderno, temi built-in (Superhero scelto), nessuna dipendenza pesante |
| Layout | **PanedWindow + Frame annidati** | Già in uso, esteso con proporzioni fluide |
| Icone | **Unicode/Emoji + ttkbootstrap icons** | Zero dipendenze, già usate parzialmente in v6 |
| Branch | `feature/v7-ui` | Separato da v6 stabile |

---

## Struttura finestra

### Prima (v6)
```
+-- Menu Bar -----------+
| Sidebar (280px) | Tab 5 tab             |
| DB info         |   Insight             |
| Registry        |   Dashboard V6        |
| Tabelle         |   Costruttore         |
| Shortcut legend |   Risultati           |
|                 |   Monitor             |
+-- Status Bar ---------+
```

### Dopo (v7)
```
+-- Menu Bar (ttkbootstrap style) --------+
| Icon   | Tab principali (3) | Pannello   |
| Sidebar| [DB][Contr][Dash]  | Info DB    |
| (44px) |                    | compatto   |
|        | Pannello principale| (opzionale)|
|        | + area risultati   |            |
|        | + progress bar     |            |
+-- Status Bar (con indicatori live) -----+
```

### Sidebar icon-based
- Larghezza fissa ~44px
- Icone grandi e chiare: Database, Controlli, Dashboard, Impostazioni
- Tooltip su hover
- Highlighter sul tab attivo

### Pannello Info DB (opzionale, collassabile)
- Mostra DB connesso, label, path, numero tabelle
- Stato connessione con indicatore colorato
- Collassabile per dare più spazio al contenuto principale

---

## Riorganizzazione Tab

### Da 5 a 3 tab principali

| Tab | Contenuto |
|---|---|
| **Database** | Info DB, insight automatici (DataProfiler), registry DB collegati, elenco tabelle |
| **Controlli** | Builder (configurazione), libreria condizioni, gruppi, gestione condizioni |
| **Dashboard** | Esecuzione batch/singola, risultati live, storico monitor, esportazione |

---

## Componenti ridisegnati

### 1. Condition Manager

| Aspetto | v6 | v7 |
|---|---|---|
| Layout | Dialog monolitico | Split orizzontale: lista sx + dettagli dx |
| Ridimensionamento | Fisso | Fluido, si adatta alla finestra |
| Ricerca | Assente | Filtro live sulla lista |
| Ordinamento | Per inserimento | Per nome, categoria, data, DB |
| Bottoni azione | In fondo al frame (debordano) | Ancorati in basso, sempre visibili |
| Dettaglio | Solo testo | Anteprima strutturata con badge |

### 2. Builder

| Aspetto | v6 | v7 |
|---|---|---|
| Organizzazione | Unico form verticale (scroll) | Navigazione a pill: Base · Filtri · Esclusioni · Report · Periodicità |
| Bottoni azione | In fondo, a volte nascosti | Fissi in basso, sempre visibili |
| Selettore DB | Solo nel pannello sinistro | Integrato nel builder |
| Cambio tipo analisi | Ricostruzione completa | Transizione fluida, mantiene contesto |

### 3. Dashboard Unificata

| Aspetto | v6 | v7 |
|---|---|---|
| Viste separate | Dashboard, Risultati, Monitor in 3 tab | Unica vista verticale: griglia + risultati live + progress |
| Colonne tabella | 9 colonne (troppe) | 7 colonne con badge compatti |
| Filtri | Solo macrosettore | Filtri multipli: DB, tag, solo anomalie, ricerca testo |
| Progresso | Nessuno | Progress bar reale durante batch |
| Azioni per riga | Solo doppio click | Pulsanti ▶ esegui, 📋 dettagli per riga |

---

## Tema

- **ttkbootstrap theme:** `superhero` (blu scuro professionale, coerente con palette v6)
- Variabile d'ambiente o impostazione per passare ad altri temi
- Colori accent preservati dalla v5: `#0F8B8D`, `#E85D75`

---

## Dettagli tecnici

### Dipendenze nuove
- `ttkbootstrap` → `pip install ttkbootstrap`

### Refactoring coinvolti
- `access_db_tool.py`: estrarre login in `App` in moduli separati per vista (view layer)
- `ui_components.py` (3703 righe): suddividere in moduli specializzati
- Nuovo file: `theme_config.py` per gestione tema ttkbootstrap
- Nuovo file: `views/dashboard_view.py`, `views/builder_view.py`, `views/condition_manager_view.py`

### Compatibilità all'indietro
- Salvataggio condizioni (`saved_conditions.json`) invariato
- Registry DB (`database_registry.json`) invariato
- Gruppi condizioni (`condition_groups.json`) invariato

---

## Implementazione (fasi successive)

L'implementazione sarà guidata dal writing-plans. Sequencing suggerito:

1. Setup branch, install ttkbootstrap, creare theme_config.py
2. Refactor App.__init__ per caricare tema
3. Sidebar icon-based e nuovo layout principale
4. Riorganizzazione 3 tab (Database, Controlli, Dashboard)
5. Builder a pill
6. Condition Manager split
7. Dashboard unificata
8. Test e rifiniture

---

## Non in scope (v7)

- Backend rewriting (engines, db_manager)
- Nuovi tipi di controllo
- Supporto multi-utente/rete
- Dark mode toggle (si usa tema Superhero come base; altri temi esplorabili dopo)
