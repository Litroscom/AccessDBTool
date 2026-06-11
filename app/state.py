import threading


class AppState:
    def __init__(self):
        self._lock = threading.Lock()
        self.db = None
        self.executor = None
        self.store = None
        self.group_store = None
        self.db_registry = None
        self.monitor = None
        self.monitor_queue = None
        self.mon_log = None
        self.current_result = None
        self.active_builder = None
        self.active_ctype = None
        self.sel_tables = []
        self.current_db_label = ""
        self.batch_running = False
        self.loaded_condition_idx = None
        self.dash_items = []
        self.dash_state_by_key = {}
        self.current_insights = []

        self.status = None
        self.var_ctype = None
        self.var_saved = None
        self.var_lib_tag = None

    # Accesso sincronizzato allo stato dashboard condiviso tra UI e worker batch.
    def set_dash_state(self, key, value):
        with self._lock:
            self.dash_state_by_key[key] = value

    def get_dash_state(self, key, default=None):
        with self._lock:
            return self.dash_state_by_key.get(key, default)

    def dash_state_snapshot(self):
        with self._lock:
            return dict(self.dash_state_by_key)
