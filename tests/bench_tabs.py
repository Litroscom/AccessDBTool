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
