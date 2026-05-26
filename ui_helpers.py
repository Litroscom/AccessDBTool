import tkinter as tk


def mark_shortcut(widget, letter):
    try:
        text = str(widget.cget("text"))
    except Exception:
        return
    idx = text.lower().find(str(letter).lower())
    if idx >= 0:
        try:
            widget.configure(underline=idx)
        except Exception:
            pass


SHORTCUT_TABLE = [
    ("Alt+A", "Apri DB"),
    ("Alt+C", "Chiudi DB"),
    ("Alt+H", "Home"),
    ("Alt+T", "Costruttore"),
    ("Alt+D", "Dashboard"),
    ("Alt+I", "Insight"),
    ("Alt+E", "Batch"),
    ("Alt+G", "Gestisci libreria"),
    ("Alt+R", "Esegui controllo"),
    ("Alt+S", "Salva"),
    ("Alt+U", "Aggiorna"),
    ("Alt+L", "Pulisci form"),
    ("Alt+V", "Avvia monitor"),
    ("Alt+F", "Ferma monitor"),
    ("Alt+P", "Pulisci log"),
    ("Alt+Q", "Verifica formula SQL"),
    ("Alt+/", "Mostra scorciatoie"),
]


def shortcut_legend_text():
    return (
        "Alt+A Apri DB, Alt+C Chiudi, Alt+H Home, Alt+T Costruttore, Alt+D Dashboard, "
        "Alt+I Insight, Alt+E Batch, Alt+G Gestisci libreria, Alt+R Esegui controllo, "
        "Alt+S Salva, Alt+U Aggiorna, Alt+L Pulisci form, Alt+V Avvia monitor, "
        "Alt+F Ferma monitor, Alt+P Pulisci log, Alt+Q Verifica formula SQL."
    )
