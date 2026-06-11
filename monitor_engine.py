import threading
import logging
import time
from datetime import datetime

logger = logging.getLogger("AccessDBTool.Monitor")

class MonitorEngine:
    def __init__(self, db, executor, result_queue):
        self.db = db
        self.executor = executor
        self.queue = result_queue
        self._thread = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self.conditions = []
        self.interval_sec = 600
        self.is_running = False
        self.sound_enabled = True

    def configure(self, conditions, interval_min, sound):
        self.conditions = list(conditions or [])
        self.interval_sec = max(30, interval_min * 60)
        self.sound_enabled = sound
        logger.info(f"Monitor configurato: {len(self.conditions)} condizioni, intervallo {interval_min} min")

    def start(self, conditions=None):
        if conditions is not None:
            self.conditions = list(conditions or [])
        if self.is_running or not self.conditions:
            return False
        self._stop_event.clear()
        self._pause_event.set()
        self.is_running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.queue.put({"type": "status", "msg": "Monitor avviato", "running": True})
        logger.info("Thread monitor avviato.")
        return True

    def stop(self):
        self._stop_event.set()
        self._pause_event.set()  # Sblocca eventuale wait su pausa
        self.is_running = False
        # Attendi che il thread termini (max 3 secondi per non bloccare la UI)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3)
            if self._thread.is_alive():
                logger.warning("Thread monitor non terminato entro il timeout di 3s.")
        self._thread = None
        self.queue.put({"type": "status", "msg": "Monitor fermato", "running": False})
        logger.info("Thread monitor fermato.")

    def pause(self):
        self._pause_event.clear()
        self.queue.put({"type": "status", "msg": "Monitor in pausa"})
        logger.info("Monitor in pausa.")

    def resume(self):
        self._pause_event.set()
        self.queue.put({"type": "status", "msg": "Monitor ripreso"})
        logger.info("Monitor ripreso.")

    def _loop(self):
        while not self._stop_event.is_set():
            self._pause_event.wait()
            if self._stop_event.is_set():
                break
            
            logger.info("Inizio ciclo di monitoraggio.")
            self.queue.put({
                "type": "cycle_start", 
                "time": datetime.now().isoformat(),
                "total": len(self.conditions)
            })
            
            cycle_errors = []
            for i, cond in enumerate(self.conditions):
                if self._stop_event.is_set():
                    break
                
                self.queue.put({
                    "type": "progress", "current": i + 1,
                    "total": len(self.conditions), "name": cond.get("name", "?")
                })
                
                try:
                    result = self.executor.run(cond)
                    entry = {
                        "type": "check_result", "time": datetime.now().isoformat(),
                        "name": cond.get("name", "?"), "count": result.get("count", 0),
                        "title": result.get("title", ""),
                        "columns": result.get("columns", []),
                        "rows": result.get("rows", [])[:50],
                        "has_errors": result.get("count", 0) > 0,
                        "sound": self.sound_enabled
                    }
                    self.queue.put(entry)
                    if result.get("count", 0) > 0:
                        cycle_errors.append(entry)
                except Exception as e:
                    import traceback
                    logger.critical(f"ERRORE CRITICO in monitor '{cond.get('name')}': {e}\n{traceback.format_exc()}")
                    self.queue.put({
                        "type": "check_error", "time": datetime.now().isoformat(),
                        "name": cond.get("name", "?"), "error": str(e)
                    })
            
            next_run_ts = time.time() + self.interval_sec
            next_run = datetime.fromtimestamp(next_run_ts).strftime("%H:%M:%S")
            self.queue.put({
                "type": "cycle_end", "time": datetime.now().isoformat(),
                "errors_count": len(cycle_errors), "next_run": next_run
            })
            logger.info(f"Ciclo completato. {len(cycle_errors)} anomalie trovate. Prossimo avvio: {next_run}")
            
            # Attesa interrompibile: ritorna subito quando viene richiesto lo stop
            self._stop_event.wait(timeout=self.interval_sec)
