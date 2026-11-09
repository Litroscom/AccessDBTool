import queue
import logging
from datetime import datetime

logger = logging.getLogger("AccessDBTool.AppController")


class AppController:
    def __init__(self, state, db_controller):
        self.state = state
        self.db_ctrl = db_controller
        self._on_tab_switch_callback = None
        self._mon_row_cb = None
        self._mon_state_cb = None

    def set_tab_switch_callback(self, callback):
        self._on_tab_switch_callback = callback

    def set_monitor_state_callback(self, callback):
        """View hook: riceve 'running'/'stopped' quando lo stato del monitor cambia."""
        self._mon_state_cb = callback

    def set_monitor_row_callback(self, callback):
        """View hook: receives a (time, name, status, count) tuple per monitor result row."""
        self._mon_row_cb = callback

    def _beep(self):
        try:
            import winsound
            winsound.Beep(1000, 200)
        except Exception as e:
            logger.debug("Beep monitor non disponibile: %s", e)

    def set_active_nav(self, tab_id, nav_buttons):
        for btn_tab, btn in nav_buttons.items():
            btn.configure(bootstyle="primary" if btn_tab == tab_id else "secondary-outline")

    def poll_monitor(self, root):
        try:
            while True:
                m = self.state.monitor_queue.get_nowait()
                self._handle_monitor_msg(m)
        except queue.Empty:
            pass
        root.after(500, lambda: self.poll_monitor(root))

    def _handle_monitor_msg(self, m):
        msg_type = m.get("type")
        if msg_type == "status":
            self.state.status.set(m.get("msg", "Monitor"))
            if self._mon_state_cb:
                try:
                    self._mon_state_cb("running" if m.get("running") else "stopped")
                except Exception:
                    pass
            return
        if msg_type == "cycle_start":
            self.state.status.set(f"Monitor: avvio ciclo su {m.get('total', 0)} controlli")
            return
        if msg_type == "progress":
            self.state.status.set(f"Monitor: {m.get('current', 0)}/{m.get('total', 0)} - {m.get('name', '?')}")
            return
        if msg_type == "log":
            logger.info("Monitor: %s", m.get("msg", ""))
            return
        if msg_type == "error":
            logger.error("Monitor error: %s", m.get("msg", ""))
            self.state.status.set("Monitor: ERRORE")
            return
        if msg_type == "stop":
            self.state.status.set("Monitor fermato.")
            return

        event_time = datetime.now().strftime("%H:%M:%S")
        mon_log = getattr(self.state, "mon_log", None)
        if msg_type == "check_result":
            name = m.get("name") or m.get("check") or "?"
            count = m.get("count", 0)
            if m.get("is_error"):
                status = "Errore"
            else:
                status = "Trovati" if count > 0 else "OK"
            if self._mon_row_cb:
                self._mon_row_cb((event_time, name, status, count))
            if mon_log:
                mon_log.add(dict(m))
            if count > 0 and m.get("sound", True):
                self._beep()
            return
        if msg_type == "check_error":
            if self._mon_row_cb:
                self._mon_row_cb((event_time, m.get("name", "?"), "Errore", 0))
            if mon_log:
                mon_log.add(dict(m))
            self.state.status.set(f"Errore monitor: {m.get('name', '?')}")
            return
        if msg_type == "cycle_end":
            if mon_log:
                mon_log.flush()
            self.state.status.set(
                f"Monitor: ciclo completato, anomalie {m.get('errors_count', 0)} - prossimo avvio {m.get('next_run', '?')}"
            )
            return

    def start_monitor(self, interval_min=10):
        if not self.state.db.connected:
            from tkinter import messagebox
            return messagebox.showwarning("!", "Apri un Database prima di avviare il monitor.")
        if not self.state.store.items:
            from tkinter import messagebox
            return messagebox.showwarning("!", "Salva almeno una condizione prima di avviare il monitor.")
        self.state.monitor.configure(
            self.state.store.items, interval_min, sound=True,
        )
        if self.state.monitor.start():
            self.state.status.set("Monitor avviato.")
            return True
        self.state.status.set("Monitor non avviato.")
        return False

    def stop_monitor(self):
        self.state.monitor.stop()
        self.state.status.set("Monitor fermato.")

    def clear_mon_log(self):
        # Svuotamento sicuro: drena la coda con get_nowait invece di toccare
        # il deque interno di queue.Queue (operazione non thread-safe).
        try:
            while True:
                self.state.monitor_queue.get_nowait()
        except queue.Empty:
            pass
        if getattr(self.state, "mon_log", None):
            self.state.mon_log.clear()
        self.state.status.set("Log monitor pulito.")
