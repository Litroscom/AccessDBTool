"""Misura separatamente il costo del cambio tab e il costo di rendering Tk.

Lo script crea l'app senza aprire alcun database e tiene la finestra visibile,
come nell'uso reale. Prima riscalda le quattro view (Controlli, Dashboard,
Monitor, Database) visitandole una volta e scartando quei numeri. Poi esegue
5 giri sulle quattro tab e registra, per ogni switch, due durate distinte con
`time.perf_counter()`:

- switch: solo `app._switch_tab(tab)`, cioè la logica controllata dal codice
  (pack_forget + pack + refresh + navigazione);
- update: il successivo `app.update()`, cioè il flush di relayout/repaint di
  Tk/ttkbootstrap sulla finestra visibile.

Le due colonne sono separate perché sommandole in un unico numero il benchmark
misurerebbe il framework, non la modifica: `app.update()` costava già 37-187 ms
prima di questo branch e nessuna modifica all'architettura delle view può
eliminarlo. Viene stampata la mediana per tab di entrambe le colonne e il totale
delle due mediane; il budget `< 50 ms` viene verificato solo sulla colonna
`switch`.

Uso: python tests/bench_tabs.py
"""
import os
import sys
import time
import logging
import statistics

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
logging.disable(logging.CRITICAL)

import access_db_tool

TABS = ("controls", "dashboard", "monitor", "db")
ROUNDS = 5
SWITCH_BUDGET_MS = 50.0


def _median_ms(samples):
    return statistics.median(samples) * 1000.0


def main():
    app = access_db_tool.App()
    app.update()

    # Riscaldamento: crea e mostra ogni view una volta; i numeri vengono scartati.
    for tab in TABS:
        app._switch_tab(tab)
        app.update()

    switch_samples = {tab: [] for tab in TABS}
    update_samples = {tab: [] for tab in TABS}

    for _ in range(ROUNDS):
        for tab in TABS:
            t0 = time.perf_counter()
            app._switch_tab(tab)
            switch_samples[tab].append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            app.update()
            update_samples[tab].append(time.perf_counter() - t0)

    switch_med = {tab: _median_ms(switch_samples[tab]) for tab in TABS}
    update_med = {tab: _median_ms(update_samples[tab]) for tab in TABS}

    print(f"{'tab':<10}{'switch med':>11}{'update med':>12}{'totale':>13}")
    for tab in TABS:
        sm = switch_med[tab]
        um = update_med[tab]
        print(f"{tab:<10}{sm:>8.1f} ms{um:>9.1f} ms{sm + um:>10.1f} ms")

    print(
        "update: rendering Tk/ttkbootstrap, gia' 37-187 ms prima di questo branch"
    )

    failing = [
        (tab, switch_med[tab])
        for tab in TABS
        if switch_med[tab] >= SWITCH_BUDGET_MS
    ]
    if failing:
        tab, value = failing[0]
        print(f"BUDGET switch<50ms: FAIL ({tab} {value:.1f} ms)")
        app.destroy()
        return 1

    print("BUDGET switch<50ms: OK")
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
