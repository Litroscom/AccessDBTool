import queue
import logging

logger = logging.getLogger("AccessDBTool.AppController")


class AppController:
    def __init__(self, state, db_controller):
        self.state = state
        self.db_ctrl = db_controller

    def switch_tab(self, tab_id, nav_buttons, main_panel):
        import tkinter as tk
        from tkinter import ttk

        for btn in nav_buttons.values():
            btn.configure(bootstyle="secondary-outline")
        nav_buttons[tab_id].configure(bootstyle="primary")

        for w in main_panel.winfo_children():
            w.destroy()

        if tab_id == "db":
            from views.database_view import DatabaseView
            view = DatabaseView(main_panel, self.state, self.db_ctrl)
            view.pack(fill=tk.BOTH, expand=True)
            view.refresh()
            return view
        elif tab_id == "controls":
            from views.builder_view import BuilderView
            view = BuilderView(main_panel, self.state, self.db_ctrl)
            view.pack(fill=tk.BOTH, expand=True)
            return view
        elif tab_id == "dashboard":
            from views.dashboard_view import DashboardView
            view = DashboardView(main_panel, self.state, self.db_ctrl)
            view.pack(fill=tk.BOTH, expand=True)
            view._refresh()
            return view
        return None

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
            return
        if msg_type == "cycle_start":
            self.state.status.set(f"Monitor: avvio ciclo su {m.get('total', 0)} controlli")
            return
        if msg_type == "progress":
            self.state.status.set(f"Monitor: {m.get('current', 0)}/{m.get('total', 0)} - {m.get('name', '?')}")
            return

    def start_monitor(self):
        if not self.state.db.connected:
            from tkinter import messagebox
            return messagebox.showwarning("!", "Apri un Database prima di avviare il monitor.")
        if not self.state.store.items:
            from tkinter import messagebox
            return messagebox.showwarning("!", "Salva almeno una condizione prima di avviare il monitor.")
        if not self.state.monitor.start(self.state.store.items):
            self.state.status.set("Monitor non avviato.")
            return False
        return True

    def stop_monitor(self):
        self.state.monitor.stop()
