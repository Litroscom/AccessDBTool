# AccessDBTool v8.0 Beta — Stato e Riprendibilità

**Ultimo aggiornamento:** 2026-08-11
**Ramo attivo:** `beta` — commit `a9b678a`
**Versione stabile:** `main` (7.4 + bugfix) — commit `63332c6`

---

## ⚠️ COME RIPRENDERE (dalla prossima sessione)

```bash
cd C:\Users\CO\AccessDBTool
git checkout beta          # la cartella locale potrebbe essere su un altro ramo
git fetch origin && git pull origin beta
```

Lancia: doppio clic su **`Avvia_Tool.vbs`** (usa `pythonw.exe` della venv hermes).
Se serve la console per i log: `"C:\Users\CO\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" access_db_tool.pyw`

**Dipendenza importante:** la venv hermes deve avere `ttkbootstrap` e `pyodbc`
(installati già: ttkbootstrap 2.2.0, pyodbc). Se mancano:
`pip install ttkbootstrap pyodbc`

---

## 📌 PROSSIMI PASSI (cosa resta da fare)

1. **Test su DB Access reale** (il blocco più importante — non fatto perché
   l'utente non ha ancora un DB):
   - esecuzione SQL di ogni tipo di controllo
   - esclusioni (similarità + non-fuzzy) con conteggi veri
   - modifica record / sostituzione massiva su dati reali
   - batch multi-DB
   - monitor su DB vero
2. **Build PyInstaller portabile** — `python build_portable.py`
   (assente nel venv hermes; richiede `pip install pyinstaller`).
   Verificare che `--collect-all ttkbootstrap` risolva asset/temi.
3. (opzionale) UI feedback dell'utente dopo primo uso reale.

---

## ✅ FATTO (cronologia su `beta`)

| Commit | Cosa |
|---|---|
| `751c044` | **Redesign usabilità v8.0**: sidebar con etichette, Controlli con sezioni numerate sempre visibili, risultati incorporati, niente salto di tab automatico |
| `078a675` | **Debug session**: fix avvio (`ttkbootstrap as ttk`, `Panedwindow`), fix critico builder (pack parent TclError), test smoke multi-root |
| `4215b5a` | **Esclusioni verificate** (17 test): 4 modalità similarità + NOT(...) per tutti i tipi, flusso da Dashboard |
| `ce5517d` | Fix **esclusioni da Dashboard**: `_condition_type` allegato al risultato |
| `7c2d00f` | **Monitor**: errori non più mostrati come OK (marker `is_error`), stop al cambio DB, indicatore ON/OFF, intervallo configurabile, cronologia con ora reale |
| `9b953a9` | Fix **Gestione Condizioni** Esporta/Importa (erano inerti) + `build_portable.py` con `--collect-all ttkbootstrap` |
| `41af4d8` / `2ecd453` | Rimozione **codice morto** (ping, row_count, ui_helpers, NotificationPopup, MONITOR_COLORS) |
| `a9b678a` | **Bug filtri**: rimossa sezione "Filtri" duplicata (doppia fonte di verità persa), filtri inline in ConcatSimilarityBuilder, `_switch_tab` deduplicato, rimossi metodi morti |

---

## 🧪 STATO DEI TEST

- **`tests/test_logic_verification.py`: 91 base + filtri/esclusioni/monitor → 131 test, tutti OK**
  su Python reale Windows (Python 3.11 della venv hermes).
- **`tests/smoke_qa.py`: 16/16 OK** (richiede la root persistente di modulo già in place).
- **E2E manuale (finestra nascosta): 13/13 OK** — 15/15 builder creati con
  parent corretto, tab, risultati, filtri inline concat, indicatore monitor.
- Comando: `python -m unittest tests.test_logic_verification tests.smoke_qa`

---

## 📐 STRUTTURA INTERFACCIA BETA

**Sidebar sinistra:** Database · Controlli · Dashboard · Monitor
**Tab Controlli (flusso lineare):**
1. Configurazione del controllo (filtri/esclusioni INLINE nel builder)
2. Colonne da mostrare nel report
3. Promemoria di aggiornamento (facoltativo)
＋ Risultati incorporati sotto il modulo ＋ Libreria ＋ barra azioni (Esegui Alt+R)
**Visibilità DB:** header sempre visibile (titolo pagina + database attivo).

---

## 🔧 PUNTI DI ATTENZIONE (per la prossima sessione)

- **Import modulo**: i file usano `import ttkbootstrap as ttk` (NON `from tkinter import ttk`): l'app non parte con `tkinter.ttk` (bootstyle).
- **ttkbootstrap 2.x**: widget esportati direttamente (`ttk.Frame`... ma `Panedwindow`, non `PanedWindow`); una sola root viva per processo (Style singleton) — i test creano una root persistente di modulo.
- **Pack dei builder**: mai `pack(in_=...)` su widget creato con altro parent (TclError) — creare nel parent finale.
- **Marker d'errore**: `ConditionExecutor._error()` aggiunge `"is_error": True`; monitor/dashboard lo usano per non mostrare un errore come "OK".
- **Cambio DB**: ferma il monitor (`DBController.set_active_db_switched_callback`).
- **Skill in `.pi/skills/learned/`**: leggi `tkinter-pack-parent-mismatch`, `access-odbc-identifier-quoting` prima di toccare layout/queries.

---

## 🏷 VERSIONI SU GITHUB
- `origin/main` → v7.4 stabile + bugfix (avviabile, 107 test OK)
- `origin/beta` → v8.0-beta (questo lavoro)
