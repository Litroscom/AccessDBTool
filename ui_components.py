import tkinter as tk
import ttkbootstrap as ttk
from tkinter import messagebox, filedialog
import re
import logging
from decimal import Decimal
from datetime import datetime
import constants

logger = logging.getLogger("AccessDBTool.UIComponents")

PERIODIC_REVIEW_CYCLE_LABELS = {
    "daily": "Giornaliero",
    "weekly": "Settimanale",
    "monthly": "Mensile",
}
PERIODIC_REVIEW_CYCLE_CHOICES = [
    ("Ogni giorno", "daily"),
    ("Ogni settimana", "weekly"),
    ("Ogni mese", "monthly"),
]


def periodic_review_cycle_label(cycle):
    return PERIODIC_REVIEW_CYCLE_LABELS.get(str(cycle or "").strip().lower(), "")


def periodic_review_summary(cond, now=None):
    enabled = bool(cond.get("periodic_review_enabled"))
    cycle = str(cond.get("periodic_review_cycle", "") or "").strip().lower()
    note = str(cond.get("periodic_review_note", "") or "").strip()
    last_ack_raw = str(cond.get("periodic_review_last_ack", "") or "").strip()
    if not enabled or not cycle:
        return {"enabled": False, "due": False, "label": "-", "note": note, "last_ack": last_ack_raw}

    now = now or datetime.now()
    last_ack = None
    if last_ack_raw:
        try:
            last_ack = datetime.fromisoformat(last_ack_raw)
        except Exception:
            last_ack = None

    due = False
    if not last_ack:
        due = True
    elif cycle == "daily":
        due = last_ack.date() != now.date()
    elif cycle == "weekly":
        due = last_ack.isocalendar()[:2] != now.isocalendar()[:2]
    elif cycle == "monthly":
        due = (last_ack.year, last_ack.month) != (now.year, now.month)
    else:
        due = False

    cycle_label = periodic_review_cycle_label(cycle) or "Periodico"
    status_text = "DA AGG." if due else "OK"
    label = f"{cycle_label} {status_text}"
    if note:
        label = f"{label} | {note}"
    return {
        "enabled": True,
        "due": due,
        "label": label,
        "note": note,
        "last_ack": last_ack_raw,
    }


def attach_alt_shortcut(widget, letter, command=None):
    shortcut = str(letter or "").lower()
    if not shortcut:
        return
    cmd = command or getattr(widget, "invoke", None)
    if not callable(cmd):
        return
    text = ""
    try:
        text = widget.cget("text")
    except Exception:
        text = ""
    lower_text = str(text).lower()
    try:
        widget.configure(underline=lower_text.index(shortcut))
    except Exception:
        pass

    def _handler(_event=None):
        try:
            if not widget.winfo_exists() or not widget.winfo_viewable():
                return "break"
        except Exception:
            return "break"
        cmd()
        return "break"

    widget.bind_all(f"<Alt-{shortcut}>", _handler, add="+")

class ColumnSelector(ttk.LabelFrame):
    def __init__(self, parent, text="Colonne da visualizzare nel report"):
        super().__init__(parent, text=text, padding=5)
        self.col_vars = {}
        self._inner = ttk.Frame(self)
        self._btn_frame = ttk.Frame(self)
        self._btn_frame.pack(fill=tk.X, side=tk.TOP)
        self._inner.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
        
        ttk.Button(self._btn_frame, text="Tutte", command=self._sel_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(self._btn_frame, text="Nessuna", command=self._sel_none).pack(side=tk.LEFT, padx=2)
        ttk.Label(self._btn_frame, text="(vuoto = tutte le colonne)",
                  foreground="gray").pack(side=tk.RIGHT, padx=4)

    def set_columns(self, columns):
        for w in self._inner.winfo_children():
            w.destroy()
        self.col_vars = {}
        for i, col in enumerate(columns):
            var = tk.BooleanVar(value=False)
            self.col_vars[col] = var
            r = i // 4
            cc = i % 4
            ttk.Checkbutton(self._inner, text=col, variable=var).grid(
                row=r, column=cc, sticky="w", padx=3, pady=1)

    def get_selected(self):
        selected = []
        for col, var in self.col_vars.items():
            if var.get():
                selected.append(col)
        return selected

    def set_selected(self, cols):
        for col, var in self.col_vars.items():
            var.set(col in cols)

    def _sel_all(self):
        for var in self.col_vars.values():
            var.set(True)

    def _sel_none(self):
        for var in self.col_vars.values():
            var.set(False)


class MultiConditionBuilder(ttk.LabelFrame):
    def __init__(self, parent, db, on_table_change=None, title="Condizioni (AND/OR)",
                 show_conditions=True, show_table=True):
        super().__init__(parent, text=title, padding=5)
        self.db = db
        self.on_table_change = on_table_change
        self.condition_rows = []
        self.exclude_rows = []
        self._show_conditions = show_conditions
        self._show_table = show_table
        
        # --- Tabella Sorgente ---
        top_frm = ttk.Frame(self)
        top_frm.pack(fill=tk.X, pady=(0, 5))
        self.var_table = tk.StringVar()
        if show_table:
            ttk.Label(top_frm, text="Tabella Sorgente:").pack(side=tk.LEFT, padx=2)
            self.cmb_table = ttk.Combobox(top_frm, textvariable=self.var_table, state="readonly", width=30)
            self.cmb_table.pack(side=tk.LEFT, padx=5)
            if self.db and self.db.connected: self.cmb_table["values"] = self.db.tables
            self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)
        else:
            # Nei filtri dell'accordion la tabella deve essere quella del
            # builder principale: offrire un secondo selettore causava filtri
            # costruiti su una tabella ed eseguiti su un'altra.
            ttk.Label(top_frm, text="Tabella sorgente (dal builder):").pack(side=tk.LEFT, padx=2)
            ttk.Label(top_frm, textvariable=self.var_table,
                      font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=5)
            self.cmb_table = None
        
        self._current_table = ""
        self._rows_frame = ttk.Frame(self)
        self._rows_frame.pack(fill=tk.X, pady=4)
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X)
        if show_conditions:
            ttk.Button(btn_frame, text="+ Aggiungi condizione", command=self._add_row).pack(side=tk.LEFT, padx=4)
            ttk.Button(btn_frame, text="- Rimuovi ultima", command=self._remove_last).pack(side=tk.LEFT, padx=4)
            ttk.Separator(self, orient="horizontal").pack(fill=tk.X, pady=(8, 6))
            excl_title = "Esclusioni (opzionale)"
        else:
            # Modalità solo-esclusioni: nascondi la sezione conditions
            self._rows_frame.pack_forget()
            btn_frame.pack_forget()
            excl_title = "Esclusioni"
        excl_hdr = ttk.Frame(self)
        excl_hdr.pack(fill=tk.X)
        ttk.Label(excl_hdr, text=excl_title, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(
            excl_hdr,
            text="  Se un record soddisfa queste regole viene ignorato.",
            foreground="gray",
            font=("Segoe UI", 8, "italic"),
        ).pack(side=tk.LEFT)
        self._exclude_rows_frame = ttk.Frame(self)
        self._exclude_rows_frame.pack(fill=tk.X, pady=4)
        excl_btn_frame = ttk.Frame(self)
        excl_btn_frame.pack(fill=tk.X)
        ttk.Button(excl_btn_frame, text="+ Aggiungi esclusione", command=self._add_exclude_row).pack(side=tk.LEFT, padx=4)
        ttk.Button(excl_btn_frame, text="- Rimuovi ultima esclusione", command=self._remove_last_exclude).pack(side=tk.LEFT, padx=4)

    def _on_table_sel(self, _evt=None):
        self._current_table = self.var_table.get()
        cols = self.db.columns(self._current_table) if self._current_table and self.db else []
        for row in self.condition_rows:
            row["col_combo"]["values"] = cols
            if row["column"].get() and row["column"].get() not in cols:
                row["column"].set("")
        for row in self.exclude_rows:
            row["col_combo"]["values"] = cols
            if row["column"].get() and row["column"].get() not in cols:
                row["column"].set("")
        if self.on_table_change: self.on_table_change(self._current_table)

    def set_table(self, table):
        self.var_table.set(table)
        self._on_table_sel()

    def _create_row(self, row_store, parent_frame):
        idx = len(row_store)
        frame = ttk.Frame(parent_frame)
        frame.pack(fill=tk.X, pady=2)
        logic_var = tk.StringVar(value="AND")
        if idx > 0:
            ttk.Combobox(frame, textvariable=logic_var, values=constants.LOGIC_OPS,
                         state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frame, text="SE   ", width=5).pack(side=tk.LEFT, padx=2)
        col_var = tk.StringVar()
        cols = self.db.columns(self._current_table) if self._current_table else []
        col_combo = ttk.Combobox(frame, textvariable=col_var, values=cols,
                                  state="readonly", width=20)
        col_combo.pack(side=tk.LEFT, padx=2)
        op_var = tk.StringVar()
        ops = [k + "  (" + v + ")" for k, v in constants.OPERATORS.items()]
        ttk.Combobox(frame, textvariable=op_var, values=ops,
                     state="readonly", width=22).pack(side=tk.LEFT, padx=2)
        val_var = tk.StringVar()
        ttk.Entry(frame, textvariable=val_var, width=20).pack(side=tk.LEFT, padx=2)
        row_data = {
            "frame": frame, "logic": logic_var, "column": col_var,
            "operator": op_var, "value": val_var, "col_combo": col_combo,
        }
        row_store.append(row_data)
        return row_data

    def _add_row(self):
        self._create_row(self.condition_rows, self._rows_frame)

    def _add_exclude_row(self):
        self._create_row(self.exclude_rows, self._exclude_rows_frame)

    def _remove_last(self):
        self._remove_last_from(self.condition_rows)

    def _remove_last_exclude(self):
        self._remove_last_from(self.exclude_rows)

    def _remove_last_from(self, row_store):
        if row_store:
            row = row_store.pop()
            row["frame"].destroy()

    def validate(self):
        if not self.var_table.get():
            return False, "Selezionare una Tabella Sorgente."
        return True, ""

    def _get_conditions_from_rows(self, row_store):
        conditions = []
        for row in row_store:
            col = row["column"].get()
            op_full = row["operator"].get()
            val = row["value"].get()
            logic = row["logic"].get()
            if not col or not op_full:
                continue
            op = op_full.split("  (")[0]
            conditions.append({
                "column": col, "operator": op,
                "value": val, "logic": logic,
            })
        return conditions

    def get_conditions(self):
        return self._get_conditions_from_rows(self.condition_rows)

    def get_exclude_conditions(self):
        return self._get_conditions_from_rows(self.exclude_rows)

    def _set_rows(self, row_store, conditions, add_callback):
        for row in row_store:
            row["frame"].destroy()
        row_store.clear()
        for cond in conditions:
            add_callback()
            row = row_store[-1]
            row["column"].set(cond.get("column", ""))
            op = cond.get("operator", "=")
            desc = constants.OPERATORS.get(op, "")
            row["operator"].set(op + "  (" + desc + ")" if desc else op)
            row["value"].set(cond.get("value", ""))
            row["logic"].set(cond.get("logic", "AND"))

    def set_conditions(self, conditions):
        self._set_rows(self.condition_rows, conditions, self._add_row)

    def set_exclude_conditions(self, conditions):
        self._set_rows(self.exclude_rows, conditions, self._add_exclude_row)

    def _default_exclusion_column(self):
        cols = self.db.columns(self._current_table) if self._current_table and self.db else []
        preferred = ["ID", "Id", "id", "Codice", "Code", "Key", "Chiave"]
        for name in preferred:
            if name in cols:
                return name
        return cols[0] if cols else ""

    def get_exception_column(self):
        return self._default_exclusion_column()

    def _exception_column_score(self, column):
        col = str(column).strip().lower()
        if col in ("diffusore", "nome", "iniz", "nominativo", "persona", "ragione sociale", "ragione_sociale"):
            return 0
        for token in ("nome", "diff", "iniz", "nomin", "persona", "ragione", "cognome"):
            if token in col:
                return 1
        if col in ("id", "iddif", "codice", "code", "key", "chiave"):
            return 90
        return 50

    def get_exception_targets(self, result_columns=None):
        table_cols = self.db.columns(self._current_table) if self._current_table and self.db else []
        if result_columns:
            candidates = [col for col in result_columns if col in table_cols]
        else:
            candidates = list(table_cols)
        indexed = list(enumerate(candidates))
        indexed.sort(key=lambda item: (self._exception_column_score(item[1]), item[0]))
        candidates = [col for _, col in indexed]
        default_col = self.get_exception_column()
        if default_col and default_col not in candidates:
            candidates.append(default_col)
        return candidates

    def _legacy_exceptions_to_conditions(self, values):
        column = self._default_exclusion_column()
        if not column:
            return []
        conditions = []
        for idx, value in enumerate(values):
            sval = str(value).strip()
            if not sval:
                continue
            conditions.append({
                "column": column,
                "operator": "=",
                "value": sval,
                "logic": "AND" if idx == 0 else "OR",
            })
        return conditions

    def add_exceptions(self, values, column=None):
        column = column or self._default_exclusion_column()
        if not column:
            return 0
        existing = {
            (
                cond.get("column", "").upper(),
                cond.get("operator", "").upper(),
                str(cond.get("value", "")).strip().upper(),
            )
            for cond in self.get_exclude_conditions()
        }
        count = 0
        for value in values:
            sval = str(value).strip()
            if not sval:
                continue
            key = (column.upper(), "=".upper(), sval.upper())
            if key in existing:
                continue
            self._add_exclude_row()
            row = self.exclude_rows[-1]
            row["column"].set(column)
            desc = constants.OPERATORS.get("=", "")
            row["operator"].set("=  (" + desc + ")" if desc else "=")
            row["value"].set(sval)
            row["logic"].set("AND" if len(self.exclude_rows) == 1 else "OR")
            existing.add(key)
            count += 1
        return count

    def get_config(self):
        cfg = {
            "table": self.var_table.get(),
            "conditions": self.get_conditions()
        }
        exclude_conditions = self.get_exclude_conditions()
        if exclude_conditions:
            cfg["exclude_conditions"] = exclude_conditions
        return cfg

    def set_config(self, c):
        self.set_table(c.get("table") or c.get("source_table") or (c.get("tables", [""])[0] if c.get("tables") else ""))
        self.set_conditions(c.get("conditions", []))
        exclude_conditions = c.get("exclude_conditions")
        if exclude_conditions is None and c.get("exceptions"):
            exclude_conditions = self._legacy_exceptions_to_conditions(c.get("exceptions", []))
        self.set_exclude_conditions(exclude_conditions or [])

    def clear(self):
        for row in self.condition_rows:
            row["frame"].destroy()
        self.condition_rows = []
        for row in self.exclude_rows:
            row["frame"].destroy()
        self.exclude_rows = []


class ConditionSaveDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        store=None,
        default_name="",
        default_tag="",
        force_new=False,
        default_desc="",
        initial_periodic_review_enabled=False,
        initial_periodic_review_cycle="monthly",
        initial_periodic_review_note="",
        # Legacy parameter names (kept for backward compatibility)
        initial_name=None,
        initial_desc=None,
        initial_tag=None,
    ):
        # Use legacy params if provided (they override the new ones)
        if initial_name is not None:
            default_name = initial_name
        if initial_desc is not None:
            default_desc = initial_desc
        if initial_tag is not None:
            default_tag = initial_tag
        if force_new:
            default_name = ""
            default_tag = ""
        super().__init__(parent)
        self.title("Salva Condizione")
        self.geometry("460x470")
        self.result = None
        self.transient(parent)
        self.grab_set()
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Titolo Breve:").pack(anchor=tk.W)
        self.ent_name = ttk.Entry(frame)
        self.ent_name.pack(fill=tk.X, pady=(5, 15))
        self.ent_name.insert(0, default_name)
        self.ent_name.focus_set()
        ttk.Label(frame, text="Macrosettore / Tipo Database:").pack(anchor=tk.W)
        self.ent_tag = ttk.Entry(frame)
        self.ent_tag.pack(fill=tk.X, pady=(5, 15))
        self.ent_tag.insert(0, default_tag)
        ttk.Label(frame, text="Descrizione Estesa:").pack(anchor=tk.W)
        self.txt_desc = tk.Text(frame, height=5, font=("Segoe UI", 9))
        self.txt_desc.pack(fill=tk.BOTH, expand=True, pady=5)
        self.txt_desc.insert("1.0", default_desc)

        reminder_box = ttk.LabelFrame(frame, text="Promemoria Aggiornamento Periodo", padding=10)
        reminder_box.pack(fill=tk.X, pady=(12, 0))
        self.var_periodic_review_enabled = tk.BooleanVar(value=bool(initial_periodic_review_enabled))
        self.chk_periodic_review = ttk.Checkbutton(
            reminder_box,
            text="Questa condizione usa un periodo da aggiornare regolarmente",
            variable=self.var_periodic_review_enabled,
            command=self._toggle_periodic_review_fields,
        )
        self.chk_periodic_review.pack(anchor=tk.W)

        cycle_row = ttk.Frame(reminder_box)
        cycle_row.pack(fill=tk.X, pady=(8, 4))
        ttk.Label(cycle_row, text="Frequenza:").pack(side=tk.LEFT)
        self.var_periodic_review_cycle = tk.StringVar(
            value=self._cycle_display_from_key(initial_periodic_review_cycle or "monthly")
        )
        self.cmb_periodic_review_cycle = ttk.Combobox(
            cycle_row,
            textvariable=self.var_periodic_review_cycle,
            state="readonly",
            width=18,
            values=[label for label, _key in PERIODIC_REVIEW_CYCLE_CHOICES],
        )
        self.cmb_periodic_review_cycle.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(reminder_box, text="Nota promemoria:").pack(anchor=tk.W, pady=(6, 0))
        self.var_periodic_review_note = tk.StringVar(value=initial_periodic_review_note)
        self.ent_periodic_review_note = ttk.Entry(reminder_box, textvariable=self.var_periodic_review_note)
        self.ent_periodic_review_note.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(
            reminder_box,
            text="Esempio: aggiornare il mese corrente prima di eseguire il batch.",
            foreground="gray",
        ).pack(anchor=tk.W, pady=(4, 0))

        btn_bar = ttk.Frame(frame)
        btn_bar.pack(fill=tk.X, pady=(15, 0))
        btn_cancel = ttk.Button(btn_bar, text="Annulla", command=self.destroy)
        btn_cancel.pack(side=tk.RIGHT, padx=5)
        btn_save = ttk.Button(btn_bar, text="SALVA", command=self._on_save)
        btn_save.pack(side=tk.RIGHT, padx=5)
        attach_alt_shortcut(btn_cancel, "a")
        attach_alt_shortcut(btn_save, "s")
        self._toggle_periodic_review_fields()

    def _cycle_display_from_key(self, cycle):
        normalized = str(cycle or "").strip().lower()
        for label, key in PERIODIC_REVIEW_CYCLE_CHOICES:
            if key == normalized:
                return label
        return PERIODIC_REVIEW_CYCLE_CHOICES[-1][0]

    def _cycle_key_from_display(self):
        current = self.var_periodic_review_cycle.get().strip()
        for label, key in PERIODIC_REVIEW_CYCLE_CHOICES:
            if label == current:
                return key
        return "monthly"

    def _toggle_periodic_review_fields(self):
        state = "readonly" if self.var_periodic_review_enabled.get() else tk.DISABLED
        self.cmb_periodic_review_cycle.configure(state=state)
        self.ent_periodic_review_note.configure(state=tk.NORMAL if self.var_periodic_review_enabled.get() else tk.DISABLED)

    def _on_save(self):
        name = self.ent_name.get().strip()
        tag = self.ent_tag.get().strip()
        desc = self.txt_desc.get("1.0", tk.END).strip()
        if not name:
            messagebox.showwarning("Attenzione", "Il titolo è obbligatorio.")
            return
        if not tag:
            messagebox.showwarning("Attenzione", "Il macrosettore o tipo database e obbligatorio.")
            return
        enabled = self.var_periodic_review_enabled.get()
        self.result = {
            "name": name,
            "description": desc,
            "tag": tag,
            "periodic_review_enabled": enabled,
            "periodic_review_cycle": self._cycle_key_from_display() if enabled else "",
            "periodic_review_note": self.var_periodic_review_note.get().strip() if enabled else "",
        }
        self.destroy()


class RecordEditorDialog(tk.Toplevel):
    def __init__(self, parent, db, table, record_data):
        super().__init__(parent)
        self.db = db
        self.table = table
        self.data = record_data
        self.result = None
        
        self.title(f"Modifica Record - {table}")
        self.geometry("500x600")
        self.grab_set()
        self.transient(parent)
        
        # UI
        main = ttk.Frame(self, padding=20)
        main.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(main, text=f"Tabella: {table}", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 15))
        
        # Scrollable content area
        self.canvas = tk.Canvas(main)
        vsb = ttk.Scrollbar(main, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = ttk.Frame(self.canvas)
        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_win = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.entries = {}
        # Identifica le colonne chiave che identificano UNIVOCAMENTE il record.
        self.key_cols, self._key_error = self._determine_key_columns()
        self.pk_col = self.key_cols[0] if self.key_cols else None
        # Colonne reali della tabella (confronto case-insensitive: Access non
        # distingue le maiuscole). Le altre (computate/alias/join) non sono
        # modificabili e vanno mostrate in sola lettura.
        try:
            self._table_cols_lower = (
                {str(c).strip().lower() for c in self.db.columns(table)}
                if hasattr(self.db, "columns") else set()
            )
        except Exception:
            self._table_cols_lower = set()

        for k, v in record_data.items():
            f = ttk.Frame(self.scroll_frame)
            f.pack(fill=tk.X, pady=5)
            lbl = ttk.Label(f, text=k, width=20)
            lbl.pack(side=tk.LEFT)

            ent = ttk.Entry(f)
            ent.insert(0, str(v) if v is not None else "")
            ent.pack(side=tk.LEFT, fill=tk.X, expand=True)

            if k in self.key_cols:
                ent.config(state="readonly")
                lbl.config(text=k + " (PK)")
            elif self._table_cols_lower and str(k).strip().lower() not in self._table_cols_lower:
                ent.config(state="readonly")
                lbl.config(text=k + " (non modificabile)")
            else:
                # Se è un campo numerico, rimappa il punto (tastierino o tastiera) in virgola
                if isinstance(v, (float, int, Decimal)):
                    ent.bind("<KeyPress-period>", self._on_dot_to_comma)
                    ent.bind("<KeyPress-KP_Decimal>", self._on_dot_to_comma)
                
            self.entries[k] = ent

        btn_f = ttk.Frame(main, padding=(0, 20, 0, 0))
        btn_f.pack(fill=tk.X)
        ttk.Button(btn_f, text="SALVA MODIFICHE", command=self._save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_f, text="Annulla", command=self.destroy).pack(side=tk.RIGHT)

    def _on_dot_to_comma(self, event):
        """Sostituisce il punto con la virgola durante la digitazione."""
        event.widget.insert(tk.INSERT, ",")
        return "break"

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_win, width=event.width)

    def _guess_pk(self):
        cols = list(self.data.keys())
        # Cerca PK note per nome esatto
        for c in cols:
            if c.lower() in ("id", "pk", "codice", "code", "key"): return c
        # Cerca colonne che iniziano con "id" (es. IDdiff, ID_cliente)
        for c in cols:
            if c.lower().startswith("id"): return c
        # Fallback: usa la prima colonna ma avvisa l'utente
        logger.warning(f"Chiave primaria non identificata per '{self.table}'. "
                       f"Uso '{cols[0]}' come fallback. update_record_safe verifichera' "
                       f"comunque l'unicita' a runtime.")
        return cols[0]

    def _data_key_ci(self, name):
        """Trova nel record la chiave che combacia con 'name' senza distinguere
        maiuscole/minuscole; ritorna la grafia presente nei dati (così
        self.data[k] funziona) o None."""
        target = str(name).strip().lower()
        for k in self.data:
            if str(k).strip().lower() == target:
                return k
        return None

    def _determine_key_columns(self):
        """Colonne che identificano univocamente il record da modificare.
        Preferisce la chiave primaria REALE del database; se non e' tra le
        colonne mostrate, ritorna ([], errore) cosi' la modifica viene bloccata
        con un messaggio chiaro. Senza PK nota dal driver ripiega su una colonna
        'id-like': la sicurezza e' comunque garantita a runtime da
        update_record_safe (UPDATE solo se COUNT==1)."""
        pks = self.db.primary_keys(self.table) if hasattr(self.db, "primary_keys") else []
        if pks:
            resolved, missing = [], []
            for p in pks:
                dk = self._data_key_ci(p)
                if dk is None:
                    missing.append(p)
                else:
                    resolved.append(dk)
            if missing:
                return [], (
                    "Chiave primaria mancante",
                    f"Per modificare il record in sicurezza serve la chiave primaria "
                    f"{', '.join(missing)}, ma non è tra le colonne mostrate.\n\n"
                    "Aggiungi questa colonna alle 'colonne da visualizzare' della "
                    "condizione, riesegui il controllo e riprova la modifica.",
                )
            return resolved, None
        guess = self._guess_pk()
        return ([guess] if guess else []), None

    def _save(self):
        if not self.key_cols:
            if self._key_error:
                messagebox.showwarning(*self._key_error)
            else:
                messagebox.showerror("Errore", "Impossibile identificare il record da modificare.")
            return
        new_data = {}
        for k, ent in self.entries.items():
            if k not in self.key_cols:
                val_str = ent.get()
                orig_val = self.data.get(k)

                # Campo svuotato dall'utente
                if not val_str:
                    if orig_val is None:
                        new_data[k] = None
                    elif isinstance(orig_val, (int, float, bool, Decimal)):
                        # Campo numerico svuotato → NULL (non stringa vuota che causerebbe errore ODBC)
                        new_data[k] = None
                    else:
                        new_data[k] = ""
                    continue

                # Prova il casting al tipo originale per evitare la perdita di decimali e problemi ODBC
                if isinstance(orig_val, bool):
                    v_lower = val_str.strip().lower()
                    if v_lower in ("true", "1", "vero", "sì", "si", "yes", "-1"):
                        new_data[k] = True
                    elif v_lower in ("false", "0", "falso", "no", "0.0"):
                        new_data[k] = False
                    else:
                        new_data[k] = val_str
                elif isinstance(orig_val, (float, Decimal)):
                    try:
                        val_str_clean = val_str.replace(",", ".")
                        if isinstance(orig_val, Decimal):
                            new_data[k] = Decimal(val_str_clean)
                        else:
                            new_data[k] = float(val_str_clean)
                    except Exception:
                        new_data[k] = val_str
                elif isinstance(orig_val, int):
                    try:
                        new_data[k] = int(val_str)
                    except ValueError:
                        new_data[k] = val_str
                else:
                    new_data[k] = val_str
        
        try:
            key_dict = {k: self.data[k] for k in self.key_cols}
            rowcount = self.db.update_record_safe(self.table, key_dict, new_data)
            if rowcount > 0:
                messagebox.showinfo("Successo", f"Record aggiornato correttamente ({rowcount} righe).")
                self.result = True
                self.destroy()
            else:
                messagebox.showinfo("Nessuna modifica", "Nessun campo da aggiornare.")
        except ValueError as e:
            # update_record_safe ha rifiutato (0 o >1 record): nulla è stato scritto.
            messagebox.showerror("Modifica annullata", str(e))
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile aggiornare il record:\n{e}")

class GroupSelector(ttk.Frame):
    def __init__(self, parent, group_store, on_load_cb):
        super().__init__(parent)
        self.store = group_store
        self.on_load = on_load_cb
        
        ttk.Label(self, text="Gruppo:").pack(side=tk.LEFT, padx=(0, 5))
        self.var = tk.StringVar()
        self.cmb = ttk.Combobox(self, textvariable=self.var, state="readonly", width=30)
        self.cmb.pack(side=tk.LEFT, padx=5)
        self.cmb.bind("<<ComboboxSelected>>", self._trigger_load)
        
        ttk.Button(self, text="Salva Set Corrente", command=self._save_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(self, text="Elimina", command=self._delete_group).pack(side=tk.LEFT, padx=2)
        
        self.refresh()

    def refresh(self):
        self.cmb["values"] = self.store.names()

    def _trigger_load(self, _evt=None):
        name = self.var.get()
        group = self.store.get(name) if name else None
        if group:
            self.on_load(group)

    def _save_group(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("Salva Gruppo", "Nome del gruppo di condizioni:")
        if name:
            # Qui servirebbe un callback per ottenere le condizioni correnti dall'app
            # Per ora emettiamo un evento che verrà catturato dall'app
            self.event_generate("<<SaveGroup>>", when="tail")
            self._temp_name = name # Temporaneo per il callback

    def finalize_save(self, conditions, database_label=""):
        if hasattr(self, "_temp_name"):
            self.store.save_group(self._temp_name, conditions, database_label=database_label)
            self.refresh()
            self.var.set(self._temp_name)
            del self._temp_name

    def _delete_group(self):
        name = self.var.get()
        if name and messagebox.askyesno("Conferma", f"Eliminare il gruppo '{name}'?"):
            self.store.delete_group(name)
            self.var.set("")
            self.refresh()

class SimilarityBuilder(ttk.Frame):
    """Builder per similarity_check: mostra tutti i parametri necessari all'engine."""
    def __init__(self, parent, db=None, on_table_change=None):
        super().__init__(parent, padding=5)
        self.db = db
        self.on_table_change = on_table_change
        self.columnconfigure(1, weight=1)

        # --- Tabella Sorgente ---
        ttk.Label(self, text="Tabella Sorgente:").grid(row=0, column=0, sticky="w", pady=2)
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(self, textvariable=self.var_table, state="readonly", width=30)
        self.cmb_table.grid(row=0, column=1, sticky="ew", padx=5)
        if self.db and self.db.connected: self.cmb_table["values"] = self.db.tables
        
        # --- Colonna da analizzare ---
        ttk.Label(self, text="Colonna da analizzare:").grid(row=1, column=0, sticky="w", pady=2)
        self.var_col = tk.StringVar()
        self.cmb_col = ttk.Combobox(self, textvariable=self.var_col, width=30)
        self.cmb_col.grid(row=1, column=1, sticky="ew", padx=5)

        ttk.Label(self, text="Colonna chiave (ID):").grid(row=2, column=0, sticky="w", pady=(2, 0))
        self.var_key = tk.StringVar()
        self.cmb_key = ttk.Combobox(self, textvariable=self.var_key, width=30)
        self.cmb_key.grid(row=2, column=1, sticky="ew", padx=5, pady=(2, 0))
        ttk.Label(self, text="ℹ Deve essere l'ID univoco di questa tabella (non ID di tabelle collegate).",
                  foreground="gray", font=("Segoe UI", 8, "italic")).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=(0, 0), pady=(0, 4))
        
        self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)

        # --- Soglia ---
        ttk.Label(self, text="Soglia Somiglianza (%):").grid(row=4, column=0, sticky="w", pady=2)
        frm_sl = ttk.Frame(self)
        frm_sl.grid(row=4, column=1, sticky="ew", padx=5)
        self.var_thresh = tk.IntVar(value=80)
        self.sld = ttk.Scale(frm_sl, from_=50, to=100, variable=self.var_thresh, orient=tk.HORIZONTAL)
        self.sld.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.lbl_v = ttk.Label(frm_sl, text="80%", width=4)
        self.lbl_v.pack(side=tk.LEFT, padx=4)
        self.var_thresh.trace_add("write", lambda *a: self.lbl_v.config(text=f"{self.var_thresh.get()}%"))
        ttk.Label(self, text="Confronta solo coppie con somiglianza ≥ soglia (i flag ignorano la soglia).",
                  foreground="gray", font=("Segoe UI", 8, "italic")).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(0, 4))

        # --- Filtri (opzionale) ---
        ttk.Separator(self, orient="horizontal").grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 2))
        frm_filter_hdr = ttk.Frame(self)
        frm_filter_hdr.grid(row=7, column=0, columnspan=2, sticky="ew")
        ttk.Label(frm_filter_hdr, text="Filtri sottoinsieme (opzionale):",
                  font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(frm_filter_hdr,
                  text="  Limita la ricerca a un gruppo di record (es. solo un mese, solo attivi…)",
                  foreground="gray", font=("Segoe UI", 8, "italic")).pack(side=tk.LEFT)
        self._filter_rows = []  # lista di dict con i widget di ogni riga
        self._frm_filters = ttk.Frame(self)
        self._frm_filters.grid(row=8, column=0, columnspan=2, sticky="ew", padx=(10, 0))
        ttk.Button(self, text="+ Aggiungi filtro",
                   command=self._add_filter_row).grid(row=9, column=0, columnspan=2, sticky="w", pady=(2, 4))
        ttk.Separator(self, orient="horizontal").grid(row=10, column=0, columnspan=2, sticky="ew", pady=(2, 4))

        # --- Opzioni ---
        self.var_phonetic = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Abilita confronto fonetico (es. 'Rossi' vs 'Rosi')", variable=self.var_phonetic).grid(row=11, column=0, columnspan=2, sticky="w", pady=1)
        self.var_contain = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Rileva contenimento (es. 'Via Roma' in 'Piazza Via Roma')", variable=self.var_contain).grid(row=12, column=0, columnspan=2, sticky="w", pady=1)
        
        self.var_prefix = tk.BooleanVar(value=False)
        self.chk_prefix = ttk.Checkbutton(self, text="Rileva errori di battitura/prefissi (es. 'SRL' vs 'S.R.L.')", variable=self.var_prefix, command=self._toggle_prefix_options)
        self.chk_prefix.grid(row=13, column=0, columnspan=2, sticky="w", pady=1)

        self.frm_min_prefix = ttk.Frame(self)
        self.frm_min_prefix.grid(row=14, column=0, columnspan=2, sticky="ew", padx=(20,0))
        ttk.Label(self.frm_min_prefix, text="Lunghezza minima prefisso:").pack(side=tk.LEFT, padx=(0,5))
        self.var_min_prefix = tk.IntVar(value=3)
        self.sld_min_prefix = ttk.Scale(self.frm_min_prefix, from_=1, to=10, variable=self.var_min_prefix, orient=tk.HORIZONTAL, length=100)
        self.sld_min_prefix.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.lbl_min_prefix_v = ttk.Label(self.frm_min_prefix, text="3", width=3)
        self.lbl_min_prefix_v.pack(side=tk.LEFT, padx=4)
        self.var_min_prefix.trace_add("write", lambda *a: self.lbl_min_prefix_v.config(text=f"{self.var_min_prefix.get()}"))
        
        self._toggle_prefix_options() # Initialize visibility

        # --- Eccezioni ---
        ttk.Separator(self, orient="horizontal").grid(row=15, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        ttk.Label(self, text="Eccezioni  —  due formati supportati:",
                  font=("Segoe UI", 9, "bold")).grid(row=16, column=0, columnspan=2, sticky="w")
        ttk.Label(self, text="  • NOME1 | NOME2              esclude sempre questa coppia di valori",
                  foreground="gray", font=("Consolas", 8)).grid(row=17, column=0, columnspan=2, sticky="w", padx=(4, 0))
        ttk.Label(self, text="  • IDdiff:5 | IDdiff:12       esclude solo questa coppia di record (ID specifici)",
                  foreground="gray", font=("Consolas", 8)).grid(row=18, column=0, columnspan=2, sticky="w", padx=(4, 0))
        self.txt_exc = tk.Text(self, height=4, font=("Consolas", 9))
        self.txt_exc.grid(row=19, column=0, columnspan=2, sticky="ew", pady=(2, 2))

        # --- Esclusioni record (SQL pre-filter, opzionale) ---
        ttk.Separator(self, orient="horizontal").grid(row=20, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        frm_excl_hdr = ttk.Frame(self)
        frm_excl_hdr.grid(row=21, column=0, columnspan=2, sticky="ew")
        ttk.Label(frm_excl_hdr, text="Esclusioni record (opzionale):",
                  font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(frm_excl_hdr,
                  text="  Escludi interi record prima dell'analisi (es. solo una sede, un anno…)",
                  foreground="gray", font=("Segoe UI", 8, "italic")).pack(side=tk.LEFT)
        self._exclude_cond_rows = []
        self._frm_exclude_conds = ttk.Frame(self)
        self._frm_exclude_conds.grid(row=22, column=0, columnspan=2, sticky="ew", padx=(10, 0))
        ttk.Button(self, text="+ Aggiungi esclusione record",
                   command=self._add_exclude_cond_row).grid(row=23, column=0, columnspan=2, sticky="w", pady=(2, 4))

    def _on_table_sel(self, _evt=None):
        t = self.var_table.get()
        if t and self.db:
            cols = self.db.columns(t)
            self.cmb_col["values"] = cols
            self.cmb_key["values"] = cols
            # Aggiorna anche le combo dei filtri già presenti
            for row in self._filter_rows:
                row["cmb_col"]["values"] = cols
            for row in self._exclude_cond_rows:
                row["cmb_col"]["values"] = cols
            if self.on_table_change: self.on_table_change(t)

    def _add_filter_row(self, col="", op="=", val=""):
        """Aggiunge una riga filtro [Colonna] [Operatore] [Valore] [X]."""
        frm = ttk.Frame(self._frm_filters)
        frm.pack(fill=tk.X, pady=1)
        
        cols = self.db.columns(self.var_table.get()) if (self.db and self.var_table.get()) else []
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols, width=18)
        cmb_col.pack(side=tk.LEFT, padx=(0, 2))
        
        OPERATORS = ["=", "<>", "<", "<=", ">", ">=", "LIKE", "IS NULL", "IS NOT NULL"]
        var_op = tk.StringVar(value=op)
        cmb_op = ttk.Combobox(frm, textvariable=var_op, values=OPERATORS, width=12, state="readonly")
        cmb_op.pack(side=tk.LEFT, padx=(0, 2))
        
        var_val = tk.StringVar(value=val)
        ent_val = ttk.Entry(frm, textvariable=var_val, width=18)
        ent_val.pack(side=tk.LEFT, padx=(0, 2))
        
        row_dict = {"frm": frm, "cmb_col": cmb_col, "var_col": var_col,
                    "cmb_op": cmb_op, "var_op": var_op,
                    "ent_val": ent_val, "var_val": var_val}
        
        btn_del = ttk.Button(frm, text="✕", width=2,
                             command=lambda r=row_dict: self._remove_filter_row(r))
        btn_del.pack(side=tk.LEFT)
        
        self._filter_rows.append(row_dict)

    def _remove_filter_row(self, row_dict):
        row_dict["frm"].destroy()
        self._filter_rows.remove(row_dict)

    def _toggle_prefix_options(self):
        if self.var_prefix.get():
            self.frm_min_prefix.grid()
        else:
            self.frm_min_prefix.grid_remove()

    def validate(self):
        if not self.var_table.get(): return False, "Selezionare la Tabella Sorgente."
        if not self.var_col.get(): return False, "Selezionare la Colonna da analizzare."
        if not self.var_key.get(): return False, "Selezionare la Colonna Chiave (ID)."
        return True, ""

    def get_config(self):
        exc = [line.strip() for line in self.txt_exc.get("1.0", tk.END).splitlines() if line.strip()]
        # Costruisce la lista di condizioni dai filtri UI
        conditions = []
        for r in self._filter_rows:
            c, op, v = r["var_col"].get().strip(), r["var_op"].get().strip(), r["var_val"].get().strip()
            if c and op:
                conditions.append({"column": c, "operator": op, "value": v})
        cfg = {
            "table": self.var_table.get(),
            "column": self.var_col.get(),
            "key_column": self.var_key.get(),
            "threshold": self.var_thresh.get(),
            "check_phonetic": self.var_phonetic.get(),
            "check_containment": self.var_contain.get(),
            "check_prefix": self.var_prefix.get(),
            "min_prefix": self.var_min_prefix.get() if self.var_prefix.get() else 3,
            "exceptions": exc,
        }
        if conditions:
            cfg["conditions"] = conditions
        excl_conds = self.get_exclude_conditions()
        if excl_conds:
            cfg["exclude_conditions"] = excl_conds
        return cfg

    def add_exceptions(self, values, column=None):
        existing = self.txt_exc.get("1.0", tk.END).strip()
        lines = [l.strip().upper() for l in existing.split("\n") if l.strip()]
        cnt = 0
        for v in values:
            if str(v).upper() not in lines:
                self.txt_exc.insert(tk.END, ("\n" if (existing or cnt > 0) else "") + str(v))
                lines.append(str(v).upper())
                cnt += 1
        return cnt

    def get_exception_column(self):
        return self.var_key.get().strip() or self.var_col.get().strip()

    def get_exception_targets(self, result_columns=None):
        targets = []
        key_col = self.get_exception_column()
        if key_col:
            targets.append(key_col)
        return targets

    def add_record_exclusions(self, values, column=None):
        column = column or self.get_exception_column()
        if not column:
            return 0
        existing = {
            (
                cond.get("column", "").upper(),
                cond.get("operator", "").upper(),
                str(cond.get("value", "")).strip().upper(),
            )
            for cond in self.get_exclude_conditions()
        }
        count = 0
        for value in values:
            sval = str(value).strip()
            if not sval:
                continue
            key = (column.upper(), "=", sval.upper())
            if key in existing:
                continue
            self._add_exclude_cond_row(col=column, op="=", val=sval)
            if len(self._exclude_cond_rows) > 1:
                self._exclude_cond_rows[-1]["logic"].set("OR")
            existing.add(key)
            count += 1
        return count

    def set_config(self, c):
        self.var_table.set(c.get("table") or c.get("source_table") or (c.get("tables", [""])[0] if c.get("tables") else ""))
        self._on_table_sel()
        self.var_col.set(c.get("column", ""))
        self.var_key.set(c.get("key_column", ""))
        self.var_thresh.set(c.get("threshold", 80))
        self.var_phonetic.set(c.get("check_phonetic", False))
        self.var_contain.set(c.get("check_containment", False))
        self.var_prefix.set(c.get("check_prefix", False))
        self.var_min_prefix.set(c.get("min_prefix", 3))
        self._toggle_prefix_options()
        # Ripristina i filtri
        for r in list(self._filter_rows):
            self._remove_filter_row(r)
        for cond in c.get("conditions", []):
            self._add_filter_row(
                col=cond.get("column", ""),
                op=cond.get("operator", "="),
                val=str(cond.get("value", ""))
            )
        self.txt_exc.delete("1.0", tk.END)
        self.txt_exc.insert("1.0", "\n".join(c.get("exceptions", [])))
        self.set_exclude_conditions(c.get("exclude_conditions", []))

    def _add_exclude_cond_row(self, col="", op="=", val=""):
        frm = ttk.Frame(self._frm_exclude_conds)
        frm.pack(fill=tk.X, pady=1)
        cols_list = self.db.columns(self.var_table.get()) if (self.db and self.var_table.get()) else []
        logic_var = tk.StringVar(value="AND")
        if self._exclude_cond_rows:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS,
                         state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text="ESCLUDI", width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols_list, width=18)
        cmb_col.pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar()
        ops = [k + "  (" + v + ")" for k, v in constants.OPERATORS.items()]
        op_display = op + "  (" + constants.OPERATORS.get(op, "") + ")" if op in constants.OPERATORS else op
        var_op.set(op_display)
        ttk.Combobox(frm, textvariable=var_op, values=ops, state="readonly", width=22).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=18).pack(side=tk.LEFT, padx=2)
        row_dict = {"frm": frm, "logic": logic_var, "cmb_col": cmb_col,
                    "col": var_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2,
                   command=lambda r=row_dict: self._remove_exclude_cond_row(r)).pack(side=tk.LEFT)
        self._exclude_cond_rows.append(row_dict)

    def _remove_exclude_cond_row(self, row_dict):
        row_dict["frm"].destroy()
        self._exclude_cond_rows.remove(row_dict)

    def get_exclude_conditions(self):
        result = []
        for row in self._exclude_cond_rows:
            c = row["col"].get().strip()
            op_full = row["op"].get()
            op = op_full.split("  (")[0].strip()
            v = row["val"].get()
            logic = row["logic"].get()
            if c and op:
                result.append({"column": c, "operator": op, "value": v, "logic": logic})
        return result

    def set_exclude_conditions(self, conditions):
        for row in list(self._exclude_cond_rows):
            self._remove_exclude_cond_row(row)
        for cond in conditions:
            self._add_exclude_cond_row(
                col=cond.get("column", ""),
                op=cond.get("operator", "="),
                val=str(cond.get("value", "")),
            )
            logic = (cond.get("logic") or "AND").upper()
            if len(self._exclude_cond_rows) > 1 and logic not in constants.LOGIC_OPS:
                logic = "OR"
            self._exclude_cond_rows[-1]["logic"].set(logic)


class CrossTableBuilder(ttk.Frame):
    """Builder per cross_table_existence con filtri, destinazioni multiple ed eccezioni."""
    def __init__(self, parent, db, on_table_change=None):
        super().__init__(parent, padding=5)
        self.db = db
        self.on_table_change = on_table_change
        self.columnconfigure(1, weight=1)

        # --- Tabella e chiave sorgente ---
        ttk.Label(self, text="Tabella Sorgente:").grid(row=0, column=0, sticky="w", pady=2)
        self.var_src = tk.StringVar()
        self.cmb_src = ttk.Combobox(self, textvariable=self.var_src, values=db.tables, state="readonly", width=30)
        self.cmb_src.grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(self, text="Chiave Sorgente:").grid(row=1, column=0, sticky="w", pady=2)
        self.var_key_src = tk.StringVar()
        self.cmb_key_src = ttk.Combobox(self, textvariable=self.var_key_src, state="readonly", width=30)
        self.cmb_key_src.grid(row=1, column=1, sticky="ew", padx=5)
        self.cmb_src.bind("<<ComboboxSelected>>", self._on_src_sel)

        # --- Filtri sorgente ---
        ttk.Label(self, text="Filtri Sorgente (AND):").grid(row=2, column=0, sticky="nw", pady=(8, 2))
        self._filter_frame = ttk.Frame(self)
        self._filter_frame.grid(row=2, column=1, sticky="ew", padx=5, pady=(8, 2))
        self.filter_rows = []
        self.exclude_rows = []
        ttk.Button(self, text="+ Aggiungi filtro", command=self._add_filter).grid(row=3, column=1, sticky="w", padx=5)

        ttk.Label(self, text="Esclusioni Sorgente (OR, opzionale):").grid(row=4, column=0, sticky="nw", pady=(6, 2))
        self._exclude_frame = ttk.Frame(self)
        self._exclude_frame.grid(row=4, column=1, sticky="ew", padx=5, pady=(6, 2))
        ttk.Button(self, text="+ Aggiungi esclusione", command=self._add_exclude_filter).grid(row=5, column=1, sticky="w", padx=5)

        # --- Destinazioni ---
        ttk.Separator(self, orient="horizontal").grid(row=6, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(self, text="Tabelle Destinazione:").grid(row=7, column=0, sticky="nw", pady=2)
        self._dest_frame = ttk.Frame(self)
        self._dest_frame.grid(row=7, column=1, sticky="ew", padx=5)
        self.dest_rows = []
        ttk.Button(self, text="+ Aggiungi destinazione", command=self._add_dest).grid(row=8, column=1, sticky="w", padx=5)

        ttk.Label(self, text="Logica Mancanti:").grid(row=9, column=0, sticky="w", pady=(8, 2))
        self.var_logic = tk.StringVar(value="ALMENO_UNA")
        ttk.Combobox(self, textvariable=self.var_logic, values=["ALMENO_UNA", "TUTTE", "NESSUNA"], state="readonly", width=20).grid(row=9, column=1, sticky="w", padx=5)

    def _on_src_sel(self, _evt=None):
        t = self.var_src.get()
        if t:
            cols = self.db.columns(t)
            self.cmb_key_src["values"] = cols
            for row in self.filter_rows:
                row["col_combo"]["values"] = cols
            for row in self.exclude_rows:
                row["col_combo"]["values"] = cols
            if self.on_table_change: self.on_table_change(t)

    def _add_filter(self):
        frame = ttk.Frame(self._filter_frame)
        frame.pack(fill=tk.X, pady=1)
        col_var = tk.StringVar()
        cols = self.db.columns(self.var_src.get()) if self.var_src.get() else []
        col_combo = ttk.Combobox(frame, textvariable=col_var, values=cols, width=18)
        col_combo.pack(side=tk.LEFT, padx=2)
        op_var = tk.StringVar(value="=")
        ttk.Combobox(frame, textvariable=op_var, values=list(constants.OPERATORS.keys()), width=10).pack(side=tk.LEFT, padx=2)
        val_var = tk.StringVar()
        ttk.Entry(frame, textvariable=val_var, width=15).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame, text="✕", width=2, command=lambda f=frame, r=None: self._remove_filter(f)).pack(side=tk.LEFT)
        row_data = {"frame": frame, "column": col_var, "operator": op_var, "value": val_var, "col_combo": col_combo}
        self.filter_rows.append(row_data)

    def _add_exclude_filter(self, column="", operator="=", value=""):
        frame = ttk.Frame(self._exclude_frame)
        frame.pack(fill=tk.X, pady=1)
        col_var = tk.StringVar(value=column)
        cols = self.db.columns(self.var_src.get()) if self.var_src.get() else []
        col_combo = ttk.Combobox(frame, textvariable=col_var, values=cols, width=18)
        col_combo.pack(side=tk.LEFT, padx=2)
        op_var = tk.StringVar(value=operator)
        ttk.Combobox(frame, textvariable=op_var, values=list(constants.OPERATORS.keys()), width=10).pack(side=tk.LEFT, padx=2)
        val_var = tk.StringVar(value=value)
        ttk.Entry(frame, textvariable=val_var, width=15).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame, text="✕", width=2, command=lambda f=frame: self._remove_filter(f, self.exclude_rows)).pack(side=tk.LEFT)
        row_data = {"frame": frame, "column": col_var, "operator": op_var, "value": val_var, "col_combo": col_combo}
        self.exclude_rows.append(row_data)

    def _remove_filter(self, frame, row_store=None):
        if row_store is None:
            row_store = self.filter_rows
        row_store[:] = [r for r in row_store if r["frame"] is not frame]
        frame.destroy()

    def _add_dest(self, table="", key=""):
        frame = ttk.Frame(self._dest_frame)
        frame.pack(fill=tk.X, pady=1)
        t_var = tk.StringVar(value=table)
        t_cmb = ttk.Combobox(frame, textvariable=t_var, values=self.db.tables, width=22)
        t_cmb.pack(side=tk.LEFT, padx=2)
        k_var = tk.StringVar(value=key)
        k_cmb = ttk.Combobox(frame, textvariable=k_var, width=18)
        k_cmb.pack(side=tk.LEFT, padx=2)
        def update_keys(*a):
            t = t_var.get()
            if t: k_cmb["values"] = self.db.columns(t)
        t_cmb.bind("<<ComboboxSelected>>", lambda e: update_keys())
        if table:
            k_cmb["values"] = self.db.columns(table)
        ttk.Button(frame, text="✕", width=2, command=lambda f=frame: self._remove_dest(f)).pack(side=tk.LEFT)
        self.dest_rows.append({"frame": frame, "table": t_var, "key": k_var})

    def _remove_dest(self, frame):
        self.dest_rows = [r for r in self.dest_rows if r["frame"] is not frame]
        frame.destroy()

    def validate(self):
        if not self.var_src.get(): return False, "Selezionare la Tabella Sorgente."
        if not self.var_key_src.get(): return False, "Selezionare la Chiave Sorgente."
        if not self.dest_rows: return False, "Aggiungere almeno una Tabella Destinazione."
        for r in self.dest_rows:
            if not r["table"].get(): return False, "Specificare il nome della tabella in tutte le destinazioni."
            if not r["key"].get(): return False, f"Specificare la chiave per la tabella {r['table'].get()}."
        return True, ""

    def get_config(self):
        filters = []
        for row in self.filter_rows:
            if row["column"].get():
                filters.append({"column": row["column"].get(), "operator": row["operator"].get(),
                                 "value": row["value"].get(), "logic": "AND"})
        exclude_filters = []
        for idx, row in enumerate(self.exclude_rows):
            if row["column"].get():
                exclude_filters.append({"column": row["column"].get(), "operator": row["operator"].get(),
                                        "value": row["value"].get(), "logic": "AND" if idx == 0 else "OR"})
        dests = [{"table": r["table"].get(), "key": r["key"].get()} for r in self.dest_rows if r["table"].get()]
        cfg = {
            "source_table": self.var_src.get(),
            "key_source": self.var_key_src.get(),
            "conditions": filters,
            "destinations": dests,
            "dest_logic": self.var_logic.get(),
        }
        if exclude_filters:
            cfg["exclude_conditions"] = exclude_filters
        return cfg

    def set_config(self, c):
        # Sorgente
        src = c.get("source_table", "")
        self.var_src.set(src)
        if src:
            self.cmb_key_src["values"] = self.db.columns(src)
            if self.on_table_change: self.on_table_change(src)
        self.var_key_src.set(c.get("key_source", ""))
        # Filtri
        for row in self.filter_rows: row["frame"].destroy()
        self.filter_rows = []
        for flt in c.get("conditions", []):
            self._add_filter()
            last = self.filter_rows[-1]
            last["column"].set(flt.get("column", ""))
            last["operator"].set(flt.get("operator", "="))
            last["value"].set(flt.get("value", ""))
        for row in self.exclude_rows: row["frame"].destroy()
        self.exclude_rows = []
        exclude_filters = c.get("exclude_conditions")
        if exclude_filters is None and c.get("exceptions") and c.get("key_source"):
            exclude_filters = []
            for idx, value in enumerate(c.get("exceptions", [])):
                sval = str(value).strip()
                if not sval:
                    continue
                exclude_filters.append({
                    "column": c.get("key_source", ""),
                    "operator": "=",
                    "value": sval,
                    "logic": "AND" if idx == 0 else "OR",
                })
        for flt in exclude_filters or []:
            self._add_exclude_filter(
                column=flt.get("column", ""),
                operator=flt.get("operator", "="),
                value=flt.get("value", ""),
            )
        # Destinazioni
        for row in self.dest_rows: row["frame"].destroy()
        self.dest_rows = []
        for d in c.get("destinations", []):
            self._add_dest(table=d.get("table", ""), key=d.get("key", ""))
        self.var_logic.set(c.get("dest_logic", "ALMENO_UNA"))

    def _exception_column_score(self, column):
        col = str(column).strip().lower()
        if col in ("diffusore", "nome", "iniz", "nominativo", "persona", "ragione sociale", "ragione_sociale"):
            return 0
        for token in ("nome", "diff", "iniz", "nomin", "persona", "ragione", "cognome"):
            if token in col:
                return 1
        if col in ("id", "iddif", "codice", "code", "key", "chiave"):
            return 90
        return 50

    def get_exception_targets(self, result_columns=None):
        source_cols = self.db.columns(self.var_src.get()) if self.var_src.get() else []
        if result_columns:
            candidates = [col for col in result_columns if col in source_cols]
        else:
            candidates = list(source_cols)
        indexed = list(enumerate(candidates))
        indexed.sort(key=lambda item: (self._exception_column_score(item[1]), item[0]))
        candidates = [col for _, col in indexed]
        default_col = self.get_exception_column()
        if default_col and default_col not in candidates:
            candidates.append(default_col)
        return candidates

    def add_exceptions(self, values, column=None):
        key_col = column or self.var_key_src.get()
        if not key_col:
            return 0
        existing = {
            (
                row["column"].get().upper(),
                row["operator"].get().upper(),
                str(row["value"].get()).strip().upper(),
            )
            for row in self.exclude_rows
        }
        cnt = 0
        for v in values:
            sval = str(v).strip()
            key = (key_col.upper(), "=".upper(), sval.upper())
            if not sval or key in existing:
                continue
            self._add_exclude_filter(column=key_col, operator="=", value=sval)
            existing.add(key)
            cnt += 1
        return cnt

    def get_exception_column(self):
        return self.var_key_src.get()


class FormulaBuilder(ttk.Frame):
    """Builder per formula_condition con aiuti SQL per utenti inesperti."""
    def __init__(self, parent, db=None, on_table_change=None):
        super().__init__(parent, padding=10)
        self.db = db
        self.on_table_change = on_table_change
        
        # --- Sezione Aiuti / Costruttore Guidato ---
        help_frm = ttk.LabelFrame(self, text="Tabella Sorgente e Aiuti Composizione SQL", padding=5)
        help_frm.pack(fill=tk.X, pady=(0, 10))
        
        r1 = ttk.Frame(help_frm)
        r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text="1. Tabella Sorgente:").pack(side=tk.LEFT, padx=2)
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(r1, textvariable=self.var_table, state="readonly", width=15)
        self.cmb_table.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(r1, text="  Colonna:").pack(side=tk.LEFT, padx=2)
        self.var_col = tk.StringVar()
        self.cmb_col = ttk.Combobox(r1, textvariable=self.var_col, state="readonly", width=20)
        self.cmb_col.pack(side=tk.LEFT, padx=2)
        btn_insert_col = ttk.Button(r1, text="Inserisci", command=self._insert_col)
        btn_insert_col.pack(side=tk.LEFT, padx=5)
        
        if self.db and self.db.connected:
            self.cmb_table["values"] = self.db.tables
        self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)
        
        r2 = ttk.Frame(help_frm)
        r2.pack(fill=tk.X, pady=2)
        ttk.Label(r2, text="2. Inserisci Operatore/Template:").pack(side=tk.LEFT, padx=2)
        self.var_tpl = tk.StringVar()
        tpls = [
            " = 'Valore'  (Uguale a testo)",
            " = 100  (Uguale a numero)",
            " IS NULL  (Cella Vuota)",
            " IS NOT NULL  (Cella Piena)",
            " LIKE '*testo*'  (Contiene)",
            " NOT LIKE '*testo*'  (Non contiene)",
            " > 0  (Maggiore di)",
            " <> 'Valore'  (Diverso da)",
            "LEN([]) > 5  (Lunghezza testo)",
            "(  (Apri gruppo)", ")  (Chiudi gruppo)",
            " AND ", " OR "
        ]
        self.cmb_tpl = ttk.Combobox(r2, textvariable=self.var_tpl, values=tpls, state="readonly", width=35)
        self.cmb_tpl.pack(side=tk.LEFT, padx=2)
        btn_insert_tpl = ttk.Button(r2, text="Inserisci", command=self._insert_tpl)
        btn_insert_tpl.pack(side=tk.LEFT, padx=5)

        # --- Formula Reale ---
        ttk.Label(self, text="Clausola SQL WHERE finale (modificabile a mano):").pack(anchor=tk.W, pady=(5,0))
        ttk.Label(
            self,
            text="Quando combini AND e OR usa le parentesi: Access valuta AND prima di OR.",
            foreground="gray", font=("Segoe UI", 8, "italic"),
        ).pack(anchor=tk.W)
        self.txt = tk.Text(self, height=4, font=("Consolas", 10))
        self.txt.pack(fill=tk.X, pady=2)
        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, pady=(4, 0))
        self.btn_verify_sql = ttk.Button(actions, text="Verifica Formula SQL", command=self.verify_formula)
        self.btn_verify_sql.pack(side=tk.LEFT)
        self.lbl_formula_check = ttk.Label(actions, text="Controlla la sintassi prima di eseguire.", foreground="gray")
        self.lbl_formula_check.pack(side=tk.LEFT, padx=10)

        # --- Esclusioni record (falsi positivi) ---
        # I record che soddisfano queste condizioni non vengono segnalati.
        # Alimentate anche dal tasto destro "Aggiungi a Esclusioni" sui risultati.
        excl_frm = ttk.LabelFrame(self, text="Esclusioni record (falsi positivi)", padding=6)
        excl_frm.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(excl_frm,
                  text="I record che soddisfano queste condizioni NON saranno segnalati.",
                  foreground="gray").pack(anchor=tk.W)
        self._frm_excl_rows = ttk.Frame(excl_frm)
        self._frm_excl_rows.pack(fill=tk.X, pady=2)
        self._excl_rows = []
        ttk.Button(excl_frm, text="+ Esclusione",
                   command=lambda: self._add_excl_row()).pack(anchor=tk.W, pady=2)

    def _on_table_sel(self, _evt=None):
        t = self.var_table.get()
        if t and self.db:
            self.cmb_col["values"] = self.db.columns(t)
            if self.on_table_change: self.on_table_change(t)

    def _insert_col(self):
        c = self.var_col.get()
        if c: self.txt.insert(tk.INSERT, f"[{c}]")

    def _insert_tpl(self):
        t = self.var_tpl.get().split("  (")[0]
        if t: self.txt.insert(tk.INSERT, t)

    def validate(self):
        if not self.var_table.get(): return False, "Selezionare la Tabella Sorgente."
        if not self.txt.get("1.0", tk.END).strip(): return False, "Inserire una formula SQL (clausola WHERE)."
        return True, ""

    def verify_formula(self):
        ok, msg = self.validate()
        if not ok:
            self.lbl_formula_check.config(text=msg, foreground="#B71C1C")
            messagebox.showwarning("Verifica SQL", msg)
            return False
        if not self.db or not self.db.connected:
            msg = "Apri un database prima di verificare la formula SQL."
            self.lbl_formula_check.config(text=msg, foreground="#B71C1C")
            messagebox.showwarning("Verifica SQL", msg)
            return False
        table = self.var_table.get().strip()
        formula = self.txt.get("1.0", tk.END).strip()
        sql = f"SELECT TOP 1 * FROM [{table}] WHERE {formula}"
        try:
            self.db.fetch(sql)
            msg = "Formula SQL valida."
            self.lbl_formula_check.config(text=msg, foreground="#2E7D32")
            messagebox.showinfo("Verifica SQL", f"{msg}\n\nQuery testata:\n{sql}")
            return True
        except Exception as e:
            msg = f"Errore SQL: {e}"
            self.lbl_formula_check.config(text="Formula non valida.", foreground="#B71C1C")
            messagebox.showerror("Verifica SQL", f"{msg}\n\nQuery testata:\n{sql}")
            return False

    def _default_exclusion_column(self):
        cols = self.db.columns(self.var_table.get()) if (self.db and self.var_table.get()) else []
        for name in ("ID", "Id", "id", "Codice", "Code", "Key", "Chiave"):
            if name in cols:
                return name
        return cols[0] if cols else ""

    def get_exception_column(self):
        return self._default_exclusion_column()

    def _add_excl_row(self, col="", op="=", val=""):
        frm = ttk.Frame(self._frm_excl_rows)
        frm.pack(fill=tk.X, pady=1)
        cols_list = self.db.columns(self.var_table.get()) if (self.db and self.var_table.get()) else []
        logic_var = tk.StringVar(value="AND")
        if self._excl_rows:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS,
                         state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text="ESCLUDI", width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        ttk.Combobox(frm, textvariable=var_col, values=cols_list, width=18).pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar()
        ops = [k + "  (" + v + ")" for k, v in constants.OPERATORS.items()]
        var_op.set(op + "  (" + constants.OPERATORS.get(op, "") + ")" if op in constants.OPERATORS else op)
        ttk.Combobox(frm, textvariable=var_op, values=ops, state="readonly", width=22).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=18).pack(side=tk.LEFT, padx=2)
        row_dict = {"frm": frm, "logic": logic_var, "col": var_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2,
                   command=lambda r=row_dict: self._remove_excl_row(r)).pack(side=tk.LEFT)
        self._excl_rows.append(row_dict)

    def _remove_excl_row(self, row_dict):
        row_dict["frm"].destroy()
        self._excl_rows.remove(row_dict)

    def get_exclude_conditions(self):
        result = []
        for row in self._excl_rows:
            c = row["col"].get().strip()
            op = row["op"].get().split("  (")[0].strip()
            v = row["val"].get()
            logic = row["logic"].get()
            if c and op:
                result.append({"column": c, "operator": op, "value": v, "logic": logic})
        return result

    def set_exclude_conditions(self, conditions):
        for row in list(self._excl_rows):
            self._remove_excl_row(row)
        for cond in conditions or []:
            self._add_excl_row(
                col=cond.get("column", ""),
                op=cond.get("operator", "="),
                val=str(cond.get("value", "")),
            )
            logic = (cond.get("logic") or "AND").upper()
            if len(self._excl_rows) > 1 and logic not in constants.LOGIC_OPS:
                logic = "OR"
            self._excl_rows[-1]["logic"].set(logic)

    def add_exceptions(self, values, column=None):
        column = column or self._default_exclusion_column()
        if not column:
            return 0
        existing = {
            (cond.get("column", "").upper(), cond.get("operator", "").upper(),
             str(cond.get("value", "")).strip().upper())
            for cond in self.get_exclude_conditions()
        }
        count = 0
        for value in values:
            sval = str(value).strip()
            if not sval:
                continue
            key = (column.upper(), "=", sval.upper())
            if key in existing:
                continue
            self._add_excl_row(col=column, op="=", val=sval)
            if len(self._excl_rows) > 1:
                self._excl_rows[-1]["logic"].set("OR")
            existing.add(key)
            count += 1
        return count

    def get_config(self):
        cfg = {
            "table": self.var_table.get(),
            "formula": self.txt.get("1.0", tk.END).strip()
        }
        excl = self.get_exclude_conditions()
        if excl:
            cfg["exclude_conditions"] = excl
        return cfg

    def set_config(self, c):
        self.var_table.set(c.get("table") or c.get("source_table", ""))
        self._on_table_sel()
        self.txt.delete("1.0", tk.END)
        self.txt.insert("1.0", c.get("formula", ""))
        self.set_exclude_conditions(c.get("exclude_conditions", []))
        self.lbl_formula_check.config(text="Controlla la sintassi prima di eseguire.", foreground="gray")


class ConcatSimilarityBuilder(ttk.Frame):
    """Builder per concat_similarity check: accoda più colonne prima del fuzzy match."""
    def __init__(self, parent, db=None, on_table_change=None):
        super().__init__(parent, padding=10)
        self.db = db
        self.on_table_change = on_table_change
        self.columnconfigure(1, weight=1)
        
        ttk.Label(self, text="Tabella Sorgente:").grid(row=0, column=0, sticky="w", pady=2)
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(self, textvariable=self.var_table, state="readonly", width=30)
        self.cmb_table.grid(row=0, column=1, sticky="ew", padx=5)
        if self.db and self.db.connected: self.cmb_table["values"] = self.db.tables
        self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)

        ttk.Label(self, text="Soglia (%):").grid(row=1, column=0, sticky="w", pady=5)
        self.var_thresh = tk.IntVar(value=80)
        ttk.Scale(self, from_=50, to=100, variable=self.var_thresh, orient=tk.HORIZONTAL).grid(row=1, column=1, sticky="ew")
        
        ttk.Label(self, text="Fonti (Solo Nomi Colonne):").grid(row=2, column=0, sticky="nw", pady=5)
        self.txt_sources = tk.Text(self, height=4, font=("Consolas", 10))
        self.txt_sources.grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Label(self, text="Inserisci una colonna per riga", foreground="gray").grid(row=3, column=1, sticky="w")

        ttk.Label(self, text="Colonna chiave (ID):").grid(row=4, column=0, sticky="w", pady=2)
        self.var_key = tk.StringVar()
        self.cmb_key = ttk.Combobox(self, textvariable=self.var_key, width=30)
        self.cmb_key.grid(row=4, column=1, sticky="ew", padx=5)

        ttk.Label(self, text="Eccezioni:").grid(row=5, column=0, sticky="nw", pady=(8, 2))
        self.txt_exc = tk.Text(self, height=4, font=("Consolas", 9))
        self.txt_exc.grid(row=5, column=1, sticky="ew", pady=(8, 2))

        # --- Esclusioni record (SQL pre-filter, opzionale) ---
        ttk.Separator(self, orient="horizontal").grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        frm_excl_hdr = ttk.Frame(self)
        frm_excl_hdr.grid(row=7, column=0, columnspan=2, sticky="ew")
        ttk.Label(frm_excl_hdr, text="Esclusioni record (opzionale):",
                  font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(frm_excl_hdr,
                  text="  Escludi interi record prima dell'analisi (es. solo una sede, un anno…)",
                  foreground="gray", font=("Segoe UI", 8, "italic")).pack(side=tk.LEFT)
        self._exclude_cond_rows = []
        self._frm_exclude_conds = ttk.Frame(self)
        self._frm_exclude_conds.grid(row=8, column=0, columnspan=2, sticky="ew", padx=(10, 0))
        ttk.Button(self, text="+ Aggiungi esclusione record",
                   command=self._add_exclude_cond_row).grid(row=9, column=0, columnspan=2, sticky="w", pady=(2, 4))

        # --- Filtri pre-analisi (opzionale) ---
        ttk.Separator(self, orient="horizontal").grid(row=10, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        frm_filt_hdr = ttk.Frame(self)
        frm_filt_hdr.grid(row=11, column=0, columnspan=2, sticky="ew")
        ttk.Label(frm_filt_hdr, text="Filtri (opzionale):",
                  font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(frm_filt_hdr,
                  text="  Limita la ricerca a un sottoinsieme di record (es. solo un mese).",
                  foreground="gray", font=("Segoe UI", 8, "italic")).pack(side=tk.LEFT)
        self._filter_rows = []
        self._frm_filters = ttk.Frame(self)
        self._frm_filters.grid(row=12, column=0, columnspan=2, sticky="ew", padx=(10, 0))
        ttk.Button(self, text="+ Aggiungi filtro",
                   command=self._add_filter_row).grid(row=13, column=0, columnspan=2, sticky="w", pady=(2, 4))

    def _add_filter_row(self, col="", op="=", val="", logic="AND"):
        frm = ttk.Frame(self._frm_filters)
        frm.pack(fill=tk.X, pady=1)
        cols_list = self.db.columns(self.var_table.get()) if (self.db and self.var_table.get()) else []
        logic_var = tk.StringVar(value=logic)
        if self._filter_rows:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS,
                         state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text="FILTRO", width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols_list, width=18)
        cmb_col.pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar()
        ops = [k + "  (" + v + ")" for k, v in constants.OPERATORS.items()]
        op_display = op + "  (" + constants.OPERATORS.get(op, "") + ")" if op in constants.OPERATORS else op
        var_op.set(op_display)
        ttk.Combobox(frm, textvariable=var_op, values=ops, state="readonly", width=22).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=18).pack(side=tk.LEFT, padx=2)
        row_dict = {"frm": frm, "logic": logic_var, "cmb_col": cmb_col,
                    "col": var_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2,
                   command=lambda r=row_dict: self._remove_filter_row(r)).pack(side=tk.LEFT)
        self._filter_rows.append(row_dict)

    def _remove_filter_row(self, row_dict):
        row_dict["frm"].destroy()
        self._filter_rows.remove(row_dict)

    def get_conditions(self):
        result = []
        for row in self._filter_rows:
            c = row["col"].get().strip()
            op = row["op"].get().split("  (")[0].strip()
            v = row["val"].get()
            logic = row["logic"].get()
            if c and op:
                result.append({"column": c, "operator": op, "value": v, "logic": logic})
        return result

    def set_conditions(self, conditions):
        for row in list(self._filter_rows):
            self._remove_filter_row(row)
        for cond in conditions:
            self._add_filter_row(
                col=cond.get("column", ""),
                op=cond.get("operator", "="),
                val=str(cond.get("value", "")),
                logic=cond.get("logic", "AND"),
            )

    def _on_table_sel(self, _evt=None):
        t = self.var_table.get()
        if t and self.db:
            cols = self.db.columns(t)
            self.cmb_key["values"] = cols
            for row in self._exclude_cond_rows:
                row["cmb_col"]["values"] = cols
            for row in self._filter_rows:
                row["cmb_col"]["values"] = cols
            if self.on_table_change: self.on_table_change(t)

    def validate(self):
        if not self.var_table.get(): return False, "Selezionare la Tabella Sorgente."
        if not self.var_key.get(): return False, "Selezionare la Colonna Chiave (ID)."
        cols = [line.strip() for line in self.txt_sources.get("1.0", tk.END).splitlines() if line.strip()]
        if not cols: return False, "Inserire almeno una colonna da concatenare."
        return True, ""

    def get_config(self):
        cols = [line.strip() for line in self.txt_sources.get("1.0", tk.END).splitlines() if line.strip()]
        cfg = {
            "table": self.var_table.get(),
            "threshold": self.var_thresh.get(),
            "columns": cols,
            "key_column": self.var_key.get()
        }
        exc = [line.strip() for line in self.txt_exc.get("1.0", tk.END).splitlines() if line.strip()]
        if exc:
            cfg["exceptions"] = exc
        excl_conds = self.get_exclude_conditions()
        if excl_conds:
            cfg["exclude_conditions"] = excl_conds
        conditions = self.get_conditions()
        if conditions:
            cfg["conditions"] = conditions
        return cfg

    def set_config(self, c):
        t = c.get("table") or c.get("source_table", "")
        self.var_table.set(t)
        self._on_table_sel()
        self.var_thresh.set(c.get("threshold", 80))
        self.var_key.set(c.get("key_column", ""))
        self.txt_sources.delete("1.0", tk.END)
        self.txt_sources.insert("1.0", "\n".join(c.get("columns", [])))
        self.txt_exc.delete("1.0", tk.END)
        self.txt_exc.insert("1.0", "\n".join(c.get("exceptions", [])))
        self.set_exclude_conditions(c.get("exclude_conditions", []))
        self.set_conditions(c.get("conditions", []))

    def _add_exclude_cond_row(self, col="", op="=", val=""):
        frm = ttk.Frame(self._frm_exclude_conds)
        frm.pack(fill=tk.X, pady=1)
        cols_list = self.db.columns(self.var_table.get()) if (self.db and self.var_table.get()) else []
        logic_var = tk.StringVar(value="AND")
        if self._exclude_cond_rows:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS,
                         state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text="ESCLUDI", width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols_list, width=18)
        cmb_col.pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar()
        ops = [k + "  (" + v + ")" for k, v in constants.OPERATORS.items()]
        op_display = op + "  (" + constants.OPERATORS.get(op, "") + ")" if op in constants.OPERATORS else op
        var_op.set(op_display)
        ttk.Combobox(frm, textvariable=var_op, values=ops, state="readonly", width=22).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=18).pack(side=tk.LEFT, padx=2)
        row_dict = {"frm": frm, "logic": logic_var, "cmb_col": cmb_col,
                    "col": var_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2,
                   command=lambda r=row_dict: self._remove_exclude_cond_row(r)).pack(side=tk.LEFT)
        self._exclude_cond_rows.append(row_dict)

    def _remove_exclude_cond_row(self, row_dict):
        row_dict["frm"].destroy()
        self._exclude_cond_rows.remove(row_dict)

    def get_exclude_conditions(self):
        result = []
        for row in self._exclude_cond_rows:
            c = row["col"].get().strip()
            op_full = row["op"].get()
            op = op_full.split("  (")[0].strip()
            v = row["val"].get()
            logic = row["logic"].get()
            if c and op:
                result.append({"column": c, "operator": op, "value": v, "logic": logic})
        return result

    def set_exclude_conditions(self, conditions):
        for row in list(self._exclude_cond_rows):
            self._remove_exclude_cond_row(row)
        for cond in conditions:
            self._add_exclude_cond_row(
                col=cond.get("column", ""),
                op=cond.get("operator", "="),
                val=str(cond.get("value", "")),
            )

    def add_exceptions(self, values, column=None):
        existing = self.txt_exc.get("1.0", tk.END).strip()
        lines = [l.strip().upper() for l in existing.split("\n") if l.strip()]
        cnt = 0
        for v in values:
            if str(v).upper() not in lines:
                self.txt_exc.insert(tk.END, ("\n" if (existing or cnt > 0) else "") + str(v))
                lines.append(str(v).upper())
                cnt += 1
        return cnt


class LinkedTableBuilder(ttk.Frame):
    """Builder per linked_table_intersection: filtri su due tabelle e join su chiave."""
    def __init__(self, parent, db=None, on_table_change=None):
        super().__init__(parent, padding=10)
        self.db = db
        self.on_table_change = on_table_change
        
        # Sezione Tabella 1 (Sorgente)
        self.sec1 = MultiConditionBuilder(self, db, self._on_t1_change, title="1. Tabella Sorgente e Filtri")
        self.sec1.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Sezione Collegamento
        link_frm = ttk.LabelFrame(self, text="Parametri di Collegamento (JOIN)", padding=5)
        link_frm.pack(fill=tk.X, pady=5)
        
        # Chiave Sorgente
        row1 = ttk.Frame(link_frm)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Chiave Sorgente (Tabella 1):").pack(side=tk.LEFT, padx=5)
        self.var_key_src = tk.StringVar()
        self.cmb_key_src = ttk.Combobox(row1, textvariable=self.var_key_src, width=20)
        self.cmb_key_src.pack(side=tk.LEFT, padx=5)
        
        # Chiave Riscontro
        row2 = ttk.Frame(link_frm)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Chiave Riscontro (Tabella 2):").pack(side=tk.LEFT, padx=5)
        self.var_key_dest = tk.StringVar()
        self.cmb_key_dest = ttk.Combobox(row2, textvariable=self.var_key_dest, width=20)
        self.cmb_key_dest.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(link_frm, text="(Es: 'ID' in Tabella 1 corrisponde a 'IDdiff' in Tabella 2)", 
                  font=("Segoe UI", 8), foreground="gray").pack(anchor=tk.W, padx=5)

        # Sezione Tabella 2 (Destinazione)
        self.sec2 = MultiConditionBuilder(self, db, self._on_t2_change, title="2. Tabella di Riscontro e Filtri")
        self.sec2.pack(fill=tk.BOTH, expand=True, pady=5)

    def _on_t1_change(self, table):
        self._refresh_keys(table, self.cmb_key_src)
        if self.on_table_change:
            self.on_table_change(table)

    def _on_t2_change(self, table):
        self._refresh_keys(table, self.cmb_key_dest)

    def _refresh_keys(self, table, widget):
        if self.db and table:
            cols = self.db.columns(table)
            widget["values"] = cols
        else:
            widget["values"] = []

    def validate(self):
        v1, m1 = self.sec1.validate()
        if not v1: return False, f"Tabella 1: {m1}"
        v2, m2 = self.sec2.validate()
        if not v2: return False, f"Tabella 2: {m2}"
        if not self.var_key_src.get(): return False, "Specificare la Chiave Sorgente (Tabella 1)."
        if not self.var_key_dest.get(): return False, "Specificare la Chiave Riscontro (Tabella 2)."
        return True, ""

    def get_config(self):
        c1 = self.sec1.get_config()
        c2 = self.sec2.get_config()
        cfg = {
            "table": c1["table"],
            "conditions": c1["conditions"],
            "dest_table": c2["table"],
            "dest_conditions": c2["conditions"],
            "link_key_src": self.var_key_src.get(),
            "link_key_dest": self.var_key_dest.get()
        }
        if c1.get("exclude_conditions"):
            cfg["exclude_conditions"] = c1["exclude_conditions"]
        if c2.get("exclude_conditions"):
            cfg["exclude_dest_conditions"] = c2["exclude_conditions"]
        return cfg

    def set_config(self, c):
        self.sec1.set_config({
            "table": c.get("table") or c.get("source_table", ""),
            "conditions": c.get("conditions", []),
            "exclude_conditions": c.get("exclude_conditions", []),
        })
        self.sec2.set_config({
            "table": c.get("dest_table", ""),
            "conditions": c.get("dest_conditions", []),
            "exclude_conditions": c.get("exclude_dest_conditions", []),
        })
        self.var_key_src.set(c.get("link_key_src") or c.get("link_key", ""))
        self.var_key_dest.set(c.get("link_key_dest") or c.get("link_key", ""))

    def clear(self):
        self.sec1.clear()
        self.sec2.clear()
        self.var_key_src.set("")
        self.var_key_dest.set("")

    def add_exceptions(self, values, column=None):
        return self.sec1.add_exceptions(values, column=column)

    def get_exception_column(self):
        return self.sec1.get_exception_column()

    def get_exception_targets(self, result_columns=None):
        return self.sec1.get_exception_targets(result_columns)

class FormatValidationBuilder(ttk.Frame):
    """Builder visuale per generare Regex di validazione formato senza codice."""
    def __init__(self, parent, db=None, on_table_change=None):
        super().__init__(parent, padding=10)
        self.db = db
        self.on_table_change = on_table_change
        self.segments = []
        
        # Selezione Tabella e Colonna
        top = ttk.Frame(self)
        top.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(top, text="Tabella:").pack(side=tk.LEFT)
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(top, textvariable=self.var_table, state="readonly", width=30)
        self.cmb_table.pack(side=tk.LEFT, padx=5)
        if self.db and self.db.connected: self.cmb_table["values"] = self.db.tables
        self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)
        
        ttk.Label(top, text="Colonna da validare:").pack(side=tk.LEFT, padx=(10, 0))
        self.var_col = tk.StringVar()
        self.cmb_col = ttk.Combobox(top, textvariable=self.var_col, state="readonly", width=30)
        self.cmb_col.pack(side=tk.LEFT, padx=5)
        
        # Area Segmenti
        lbl_frm = ttk.LabelFrame(self, text="Costruttore Formato (da sinistra a destra)", padding=10)
        lbl_frm.pack(fill=tk.BOTH, expand=True)
        
        self.seg_frame = ttk.Frame(lbl_frm)
        self.seg_frame.pack(fill=tk.X)
        
        btn_frm = ttk.Frame(lbl_frm)
        btn_frm.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frm, text="+ Aggiungi Pezzo", command=self._add_segment).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frm, text="- Rimuovi Ultimo", command=self._remove_last).pack(side=tk.LEFT, padx=5)
        
        self.lbl_regex = ttk.Label(self, text="Regex Generata: ^$", foreground="gray", font=("Consolas", 9))
        self.lbl_regex.pack(fill=tk.X, pady=5)

        # --- Esclusioni record (SQL pre-filter, opzionale) ---
        excl_frm = ttk.LabelFrame(self, text="Esclusioni record (opzionale)", padding=5)
        excl_frm.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(excl_frm,
                  text="Escludi interi record prima della validazione (es. solo una sede, un anno…)",
                  foreground="gray", font=("Segoe UI", 8, "italic")).pack(anchor=tk.W)
        self._excl_rows_frame = ttk.Frame(excl_frm)
        self._excl_rows_frame.pack(fill=tk.X)
        self._excl_rows = []
        ttk.Button(excl_frm, text="+ Aggiungi esclusione",
                   command=self._add_excl_row).pack(anchor=tk.W, pady=(4, 0))

    def _on_table_sel(self, _evt=None):
        table = self.var_table.get()
        cols = self.db.columns(table) if table and self.db else []
        self.cmb_col["values"] = cols
        for row in self._excl_rows:
            row["cmb_col"]["values"] = cols
        if self.on_table_change: self.on_table_change(table)

    def _add_segment(self):
        row = ttk.Frame(self.seg_frame)
        row.pack(fill=tk.X, pady=2)
        
        var_type = tk.StringVar(value="Semplice Testo (qualsiasi)")
        types = {
            "text": "Semplice Testo (qualsiasi)",
            "number": "Solo Numeri",
            "fixed": "Testo Fisso (esatto)",
            "sep": "Separatore (es: - )"
        }
        cmb_type = ttk.Combobox(row, textvariable=var_type, values=list(types.values()), state="readonly", width=25)
        cmb_type.pack(side=tk.LEFT, padx=5)
        
        var_val = tk.StringVar()
        ent_val = ttk.Entry(row, textvariable=var_val, width=20)
        ent_val.pack(side=tk.LEFT, padx=5)
        
        def on_type_change(_evt=None):
            # Lookup sicuro: un tipo non riconosciuto (es. JSON importato con
            # chiave breve "text" invece del label) non deve crashare.
            matches = [k for k, v in types.items() if v == var_type.get()]
            t = matches[0] if matches else "text"
            if t in ("text", "number"):
                ent_val.config(state="disabled")
                var_val.set("")
            else:
                ent_val.config(state="normal")
            self._update_regex()

        cmb_type.bind("<<ComboboxSelected>>", on_type_change)
        var_val.trace_add("write", lambda *args: self._update_regex())
        
        self.segments.append({"frame": row, "var_type": var_type, "var_val": var_val, "types_map": types})
        on_type_change()

    def _remove_last(self):
        if self.segments:
            s = self.segments.pop()
            s["frame"].destroy()
            self._update_regex()

    def _update_regex(self):
        parts = ["^"]
        for s in self.segments:
            t_name = s["var_type"].get()
            matches = [k for k, v in s["types_map"].items() if v == t_name]
            t = matches[0] if matches else "text"
            val = s["var_val"].get()
            
            if t == "text": parts.append(".+")
            elif t == "number": parts.append("[0-9]+")
            elif t == "fixed": parts.append(re.escape(val))
            elif t == "sep": parts.append(re.escape(val))
        
        parts.append("$")
        regex = "".join(parts)
        self.lbl_regex.config(text=f"Formula Tecnica: {regex}")
        return regex

    def validate(self):
        if not self.var_table.get(): return False, "Selezionare la Tabella Sorgente."
        if not self.var_col.get(): return False, "Selezionare la Colonna da validare."
        if not self.segments: return False, "Aggiungere almeno un segmento al formato (Pezzo)."
        return True, ""

    def _add_excl_row(self, col="", op="=", val=""):
        table = self.var_table.get()
        cols_list = self.db.columns(table) if (self.db and table) else []
        frm = ttk.Frame(self._excl_rows_frame)
        frm.pack(fill=tk.X, pady=1)
        logic_var = tk.StringVar(value="AND")
        if self._excl_rows:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS,
                         state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text="ESCLUDI", width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols_list, width=18)
        cmb_col.pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar()
        ops = [k + "  (" + v + ")" for k, v in constants.OPERATORS.items()]
        op_display = op + "  (" + constants.OPERATORS.get(op, "") + ")" if op in constants.OPERATORS else op
        var_op.set(op_display)
        ttk.Combobox(frm, textvariable=var_op, values=ops, state="readonly", width=22).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=18).pack(side=tk.LEFT, padx=2)
        row_dict = {"frm": frm, "logic": logic_var, "cmb_col": cmb_col,
                    "col": var_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2,
                   command=lambda r=row_dict: self._remove_excl_row(r)).pack(side=tk.LEFT)
        self._excl_rows.append(row_dict)

    def _remove_excl_row(self, row_dict):
        row_dict["frm"].destroy()
        self._excl_rows.remove(row_dict)

    def get_exclude_conditions(self):
        result = []
        for row in self._excl_rows:
            c = row["col"].get().strip()
            op_full = row["op"].get()
            op = op_full.split("  (")[0].strip()
            v = row["val"].get()
            logic = row["logic"].get()
            if c and op:
                result.append({"column": c, "operator": op, "value": v, "logic": logic})
        return result

    def set_exclude_conditions(self, conditions):
        for row in list(self._excl_rows):
            self._remove_excl_row(row)
        for cond in conditions:
            self._add_excl_row(
                col=cond.get("column", ""),
                op=cond.get("operator", "="),
                val=str(cond.get("value", "")),
            )
            # Ripristina il logic (AND/OR) della riga appena aggiunta
            if self._excl_rows:
                self._excl_rows[-1]["logic"].set(cond.get("logic", "AND"))

    def _exception_column_score(self, column):
        col = str(column).strip().lower()
        if col in ("id", "iddif", "codice", "code", "key", "chiave"):
            return 90
        for token in ("id", "cod", "key", "chia"):
            if col.startswith(token):
                return 80
        return 50

    def get_exception_column(self):
        table = self.var_table.get()
        cols = self.db.columns(table) if (self.db and table) else []
        preferred = ["ID", "Id", "id", "Codice", "Code", "Key", "Chiave"]
        for name in preferred:
            if name in cols:
                return name
        return cols[0] if cols else ""

    def get_exception_targets(self, result_columns=None):
        table = self.var_table.get()
        table_cols = self.db.columns(table) if (self.db and table) else []
        if result_columns:
            candidates = [col for col in result_columns if col in table_cols]
        else:
            candidates = list(table_cols)
        candidates.sort(key=lambda c: (self._exception_column_score(c), candidates.index(c) if c in candidates else 0))
        default_col = self.get_exception_column()
        if default_col and default_col not in candidates:
            candidates.append(default_col)
        return candidates

    def add_exceptions(self, values, column=None):
        column = column or self.get_exception_column()
        if not column:
            return 0
        existing = {
            (cond.get("column", "").upper(), cond.get("operator", "").upper(),
             str(cond.get("value", "")).strip().upper())
            for cond in self.get_exclude_conditions()
        }
        count = 0
        for value in values:
            sval = str(value).strip()
            if not sval:
                continue
            key = (column.upper(), "=", sval.upper())
            if key in existing:
                continue
            self._add_excl_row(col=column, op="=", val=sval)
            existing.add(key)
            count += 1
        return count

    def get_config(self):
        regex = self._update_regex()
        wizard_data = []
        for s in self.segments:
            wizard_data.append({
                "type": s["var_type"].get(),
                "value": s["var_val"].get()
            })
        cfg = {
            "table": self.var_table.get(),
            "conditions": [
                {"column": self.var_col.get(), "operator": "REGEXP", "value": regex}
            ],
            "wizard_segments": wizard_data
        }
        excl_conds = self.get_exclude_conditions()
        if excl_conds:
            cfg["exclude_conditions"] = excl_conds
        return cfg

    def set_config(self, c):
        self.var_table.set(c.get("table") or c.get("source_table", ""))
        self._on_table_sel()
        conds = c.get("conditions", [])
        if conds:
            self.var_col.set(conds[0].get("column", ""))

        for s in self.segments: s["frame"].destroy()
        self.segments = []

        for seg in c.get("wizard_segments", []):
            self._add_segment()
            s = self.segments[-1]
            s["var_type"].set(seg["type"])
            s["var_val"].set(seg["value"])
            # Update entry state
            for w in s["frame"].winfo_children():
                if isinstance(w, ttk.Combobox): w.event_generate("<<ComboboxSelected>>")
        self._update_regex()
        self.set_exclude_conditions(c.get("exclude_conditions", []))

    def clear(self):
        self.var_table.set("")
        self.var_col.set("")
        for s in self.segments: s["frame"].destroy()
        self.segments = []
        self._update_regex()
        for row in list(self._excl_rows):
            self._remove_excl_row(row)

class BulkReplaceDialog(tk.Toplevel):
    """Dialogo per eseguire sostituzioni massive sui risultati correnti."""
    def __init__(self, parent, columns, record_count):
        super().__init__(parent)
        self.title("Sostituzione Massiva")
        self.geometry("450x350")
        self.result = None
        self.columns = columns
        
        main = ttk.Frame(self, padding=20)
        main.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main, text=f"Stai per modificare {record_count} record.", font=("Segoe UI", 10, "bold")).pack(pady=(0, 15))
        
        ttk.Label(main, text="Seleziona Colonna da modificare:").pack(anchor=tk.W)
        self.var_col = tk.StringVar()
        self.cmb_col = ttk.Combobox(main, textvariable=self.var_col, values=columns, state="readonly")
        self.cmb_col.pack(fill=tk.X, pady=(5, 15))
        
        ttk.Label(main, text="Nuovo Valore:").pack(anchor=tk.W)
        self.var_val = tk.StringVar()
        self.ent_val = ttk.Entry(main, textvariable=self.var_val)
        self.ent_val.pack(fill=tk.X, pady=(5, 15))
        
        self.var_mode = tk.StringVar(value="replace_all")
        ttk.Radiobutton(main, text="Sovrascrivi tutto con il nuovo valore", 
                        variable=self.var_mode, value="replace_all").pack(anchor=tk.W)
        
        btn_frm = ttk.Frame(main)
        btn_frm.pack(fill=tk.X, pady=(20, 0))
        ttk.Button(btn_frm, text="ANNULLA", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frm, text="ESEGUI AGGIORNAMENTO", command=self._confirm).pack(side=tk.RIGHT, padx=5)
        
        self.transient(parent)
        self.grab_set()

    def _confirm(self):
        col = self.var_col.get()
        val = self.var_val.get()
        if not col:
            messagebox.showwarning("Attenzione", "Seleziona una colonna.")
            return
        
        if not messagebox.askyesno("Conferma", f"Sei sicuro di voler sovrascrivere la colonna '{col}' per TUTTI i record selezionati?"):
            return
            
        self.result = {"column": col, "value": val, "mode": self.var_mode.get()}
        self.destroy()

class DailyCoverageBuilder(ttk.Frame):
    """Builder per il Controllo Copertura Giornaliera."""
    def __init__(self, parent, db, on_table_change=None):
        super().__init__(parent, padding=5)
        self.db = db
        self.on_table_change = on_table_change
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Tabella Sorgente:").grid(row=0, column=0, sticky="w", pady=2)
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(self, textvariable=self.var_table, state="readonly", width=30)
        self.cmb_table.grid(row=0, column=1, sticky="ew", padx=5)
        if self.db and self.db.connected: self.cmb_table["values"] = self.db.tables
        
        ttk.Label(self, text="Colonna Giorno:").grid(row=1, column=0, sticky="w", pady=2)
        self.var_day_col = tk.StringVar()
        self.cmb_day_col = ttk.Combobox(self, textvariable=self.var_day_col, width=30)
        self.cmb_day_col.grid(row=1, column=1, sticky="ew", padx=5)

        ttk.Separator(self, orient=tk.HORIZONTAL).grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        
        ttk.Label(self, text="Filtro Base: Mese").grid(row=3, column=0, sticky="w", pady=2)
        frm_m = ttk.Frame(self)
        frm_m.grid(row=3, column=1, sticky="ew", padx=5)
        self.var_month_col = tk.StringVar()
        self.cmb_month_col = ttk.Combobox(frm_m, textvariable=self.var_month_col, width=15)
        self.cmb_month_col.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(frm_m, text="=").pack(side=tk.LEFT, padx=2)
        self.var_month_val = tk.StringVar()
        ttk.Entry(frm_m, textvariable=self.var_month_val, width=10).pack(side=tk.LEFT, padx=5)

        ttk.Label(self, text="Filtro Base: Settimana").grid(row=4, column=0, sticky="w", pady=2)
        frm_w = ttk.Frame(self)
        frm_w.grid(row=4, column=1, sticky="ew", padx=5)
        self.var_week_col = tk.StringVar()
        self.cmb_week_col = ttk.Combobox(frm_w, textvariable=self.var_week_col, width=15)
        self.cmb_week_col.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(frm_w, text="=").pack(side=tk.LEFT, padx=2)
        self.var_week_val = tk.StringVar()
        ttk.Entry(frm_w, textvariable=self.var_week_val, width=10).pack(side=tk.LEFT, padx=5)

        ttk.Separator(self, orient=tk.HORIZONTAL).grid(row=5, column=0, columnspan=2, sticky="ew", pady=5)

        ttk.Label(self, text="Numero giorni attesi (es. 7):").grid(row=6, column=0, sticky="w", pady=2)
        self.var_expected_count = tk.IntVar(value=7)
        ttk.Entry(self, textvariable=self.var_expected_count, width=10).grid(row=6, column=1, sticky="w", padx=5)
        
        ttk.Label(self, text="Data Inizio Settimana (Opzionale, formato gg/mm/aaaa):").grid(row=7, column=0, sticky="w", pady=2)
        self.var_start_date = tk.StringVar()
        ttk.Entry(self, textvariable=self.var_start_date, width=15).grid(row=7, column=1, sticky="w", padx=5)

        ttk.Label(self, text="Senza 'Data Inizio', il tool si limiterà a contare i giorni. Con la 'Data Inizio' indicherà le date esatte mancanti.", foreground="gray", font=("Segoe UI", 8, "italic")).grid(row=8, column=0, columnspan=2, sticky="w", pady=(0, 10))

        # Re-use MultiConditionBuilder lists for conditions
        ttk.Separator(self, orient=tk.HORIZONTAL).grid(row=9, column=0, columnspan=2, sticky="ew", pady=5)
        self.filter_lbl = ttk.Label(self, text="Filtri ed Esclusioni aggiuntivi", font=("Segoe UI", 9, "bold"))
        self.filter_lbl.grid(row=10, column=0, columnspan=2, sticky="w")
        self._filter_rows = []
        self._exclude_cond_rows = []
        self._frm_filters = ttk.Frame(self)
        self._frm_filters.grid(row=11, column=0, columnspan=2, sticky="ew", padx=10)
        # Frame per le esclusioni: mancava (bug) e _add_exclude_cond_row
        # crashava con AttributeError al primo click su "+ Esclusione".
        self._frm_exclude_conds = ttk.Frame(self)
        self._frm_exclude_conds.grid(row=13, column=0, columnspan=2, sticky="ew", padx=10)
        btn_frm = ttk.Frame(self)
        btn_frm.grid(row=12, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Button(btn_frm, text="+ Filtro", command=self._add_filter_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frm, text="+ Esclusione", command=self._add_exclude_cond_row).pack(side=tk.LEFT, padx=2)
        
        self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)

    def _on_table_sel(self, _evt=None):
        t = self.var_table.get()
        if t and self.db:
            cols = self.db.columns(t)
            self.cmb_day_col["values"] = cols
            self.cmb_month_col["values"] = cols
            self.cmb_week_col["values"] = cols
            for row in self._filter_rows: row["cmb_col"]["values"] = cols
            for row in self._exclude_cond_rows: row["cmb_col"]["values"] = cols
            if self.on_table_change: self.on_table_change(t)
            
    def _add_filter_row(self, col="", op="=", val=""):
        frm = ttk.Frame(self._frm_filters)
        frm.pack(fill=tk.X, pady=1)
        cols_list = self.db.columns(self.var_table.get()) if (self.db and self.var_table.get()) else []
        logic_var = tk.StringVar(value="AND")
        if self._filter_rows:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS, state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text="FILTRO", width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols_list, width=18)
        cmb_col.pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar(value=op)
        ttk.Combobox(frm, textvariable=var_op, values=["=", "<>", ">", ">=", "<", "<=", "LIKE", "NOT LIKE", "IS NULL", "IS NOT NULL"], state="readonly", width=12).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=18).pack(side=tk.LEFT, padx=2)
        d = {"frm": frm, "logic": logic_var, "col": var_col, "cmb_col": cmb_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2, command=lambda: self._remove_row(d, self._filter_rows)).pack(side=tk.LEFT)
        self._filter_rows.append(d)

    def _add_exclude_cond_row(self, col="", op="=", val="", logic="AND"):
        frm = ttk.Frame(self._frm_exclude_conds)
        frm.pack(fill=tk.X, pady=1)
        cols_list = self.db.columns(self.var_table.get()) if (self.db and self.var_table.get()) else []
        logic_var = tk.StringVar(value=logic)
        if self._exclude_cond_rows:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS, state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text="ESCLUDI", width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols_list, width=18)
        cmb_col.pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar(value=op)
        ttk.Combobox(frm, textvariable=var_op, values=["=", "<>", ">", ">=", "<", "<=", "LIKE", "NOT LIKE", "IS NULL", "IS NOT NULL"], state="readonly", width=12).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=18).pack(side=tk.LEFT, padx=2)
        d = {"frm": frm, "logic": logic_var, "col": var_col, "cmb_col": cmb_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2, command=lambda: self._remove_row(d, self._exclude_cond_rows)).pack(side=tk.LEFT)
        self._exclude_cond_rows.append(d)

    def _remove_row(self, r, target_list):
        r["frm"].destroy()
        target_list.remove(r)
        
    def _parse_rows(self, row_list):
        res = []
        for r in row_list:
            c, op, v, l = r["col"].get(), r["op"].get(), r["val"].get(), r["logic"].get()
            if c: res.append({"column": c, "operator": op, "value": v, "logic": l})
        return res

    def validate(self):
        if not self.var_table.get() or not self.var_day_col.get():
            return False, "Tabella e Colonna Giorno sono obbligatori."
        return True, ""

    def get_config(self):
        conds = self._parse_rows(self._filter_rows)
        # Integriamo mese e settimana nei conds
        if self.var_month_col.get() and self.var_month_val.get():
            conds.append({"column": self.var_month_col.get(), "operator": "=", "value": self.var_month_val.get(), "logic": "AND" if conds else "AND"})
        if self.var_week_col.get() and self.var_week_val.get():
            conds.append({"column": self.var_week_col.get(), "operator": "=", "value": self.var_week_val.get(), "logic": "AND"})

        cfg = {
            "table": self.var_table.get(),
            "day_column": self.var_day_col.get(),
            "month_column": self.var_month_col.get(),
            "month_value": self.var_month_val.get(),
            "week_column": self.var_week_col.get(),
            "week_value": self.var_week_val.get(),
            "expected_count": self.var_expected_count.get(),
            "start_date": self.var_start_date.get(),
            "conditions": conds,
            "exclude_conditions": self._parse_rows(self._exclude_cond_rows)
        }
        return cfg

    def set_config(self, c):
        self.var_table.set(c.get("table") or c.get("source_table", ""))
        self._on_table_sel()
        self.var_day_col.set(c.get("day_column", ""))
        self.var_month_col.set(c.get("month_column", ""))
        self.var_month_val.set(c.get("month_value", ""))
        self.var_week_col.set(c.get("week_column", ""))
        self.var_week_val.set(c.get("week_value", ""))
        self.var_expected_count.set(c.get("expected_count", 7))
        self.var_start_date.set(c.get("start_date", ""))
        
        # Filtra month/week dai conditions per rimetterli nelle regular conditions form
        m_col = c.get("month_column")
        w_col = c.get("week_column")
        
        for r in list(self._filter_rows): self._remove_row(r, self._filter_rows)
        for r in list(self._exclude_cond_rows): self._remove_row(r, self._exclude_cond_rows)
        
        for cond in c.get("conditions", []):
            if (m_col and cond.get("column") == m_col) or (w_col and cond.get("column") == w_col):
                continue
            self._add_filter_row(col=cond["column"], op=cond["operator"], val=cond.get("value", ""))
        for cond in c.get("exclude_conditions", []):
            self._add_exclude_cond_row(col=cond["column"], op=cond["operator"], val=cond.get("value", ""))


class MandatoryRecordBuilder(ttk.Frame):
    """Builder per il Controllo Requisito Settimanale / Obbligatorio."""
    def __init__(self, parent, db, on_table_change=None):
        super().__init__(parent, padding=5)
        self.db = db
        self.on_table_change = on_table_change
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Tabella Sorgente:").grid(row=0, column=0, sticky="w", pady=2)
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(self, textvariable=self.var_table, state="readonly", width=30)
        self.cmb_table.grid(row=0, column=1, sticky="ew", padx=5)
        if self.db and self.db.connected: self.cmb_table["values"] = self.db.tables
        
        ttk.Label(self, text="(Tabella dove si cerca il record obbligatorio)", foreground="gray", font=("Segoe UI", 8, "italic")).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 5))

        self._filter_rows = []
        self._frm_filters = ttk.Frame(self)
        self._frm_filters.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10)
        ttk.Button(self, text="+ Filtro Tab Sorgente", command=self._add_filter_row).grid(row=3, column=0, columnspan=2, sticky="w", pady=5)

        self._excl_rows = []
        self._frm_excl = ttk.Frame(self)
        self._frm_excl.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10)
        ttk.Button(self, text="+ Esclusione Tab Sorgente", command=self._add_excl_row).grid(row=5, column=0, columnspan=2, sticky="w", pady=2)

        ttk.Separator(self, orient=tk.HORIZONTAL).grid(row=6, column=0, columnspan=2, sticky="ew", pady=10)

        ttk.Label(self, text="Incrocio Destinazione (Opzionale):", font=("Segoe UI", 9, "bold")).grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Label(self, text="Se per soddisfare il requisito serve un incrocio (es. esistere in Volontariato E in Diffusori).").grid(row=8, column=0, columnspan=2, sticky="w", pady=(0, 5))

        ttk.Label(self, text="Destinazione:").grid(row=9, column=0, sticky="w", pady=2)
        self.var_dest_table = tk.StringVar()
        self.cmb_dest_table = ttk.Combobox(self, textvariable=self.var_dest_table, state="readonly", width=30)
        self.cmb_dest_table.grid(row=9, column=1, sticky="ew", padx=5)
        if self.db and self.db.connected: self.cmb_dest_table["values"] = self.db.tables
        
        frm_keys = ttk.Frame(self)
        frm_keys.grid(row=10, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Label(frm_keys, text="Collega Tab Sorgente (").pack(side=tk.LEFT)
        self.var_link_src = tk.StringVar()
        self.cmb_link_src = ttk.Combobox(frm_keys, textvariable=self.var_link_src, width=15)
        self.cmb_link_src.pack(side=tk.LEFT, padx=2)
        ttk.Label(frm_keys, text=") a Tab Destinazione (").pack(side=tk.LEFT)
        self.var_link_dest = tk.StringVar()
        self.cmb_link_dest = ttk.Combobox(frm_keys, textvariable=self.var_link_dest, width=15)
        self.cmb_link_dest.pack(side=tk.LEFT, padx=2)
        ttk.Label(frm_keys, text=")").pack(side=tk.LEFT)

        self._dest_filter_rows = []
        self._frm_dest_filters = ttk.Frame(self)
        self._frm_dest_filters.grid(row=11, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        ttk.Button(self, text="+ Filtro Tab Destinazione", command=self._add_dest_filter_row).grid(row=12, column=0, columnspan=2, sticky="w", pady=5)

        self._dest_excl_rows = []
        self._frm_dest_excl = ttk.Frame(self)
        self._frm_dest_excl.grid(row=13, column=0, columnspan=2, sticky="ew", padx=10)
        ttk.Button(self, text="+ Esclusione Tab Destinazione", command=self._add_dest_excl_row).grid(row=14, column=0, columnspan=2, sticky="w", pady=2)

        self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)
        self.cmb_dest_table.bind("<<ComboboxSelected>>", self._on_dest_table_sel)

    def _on_table_sel(self, _evt=None):
        t = self.var_table.get()
        if t and self.db:
            cols = self.db.columns(t)
            self.cmb_link_src["values"] = cols
            for row in self._filter_rows: row["cmb_col"]["values"] = cols
            for row in self._excl_rows: row["cmb_col"]["values"] = cols
            if self.on_table_change: self.on_table_change(t)
            
    def _on_dest_table_sel(self, _evt=None):
        t = self.var_dest_table.get()
        if t and self.db:
            cols = self.db.columns(t)
            self.cmb_link_dest["values"] = cols
            for row in self._dest_filter_rows: row["cmb_col"]["values"] = cols
            for row in self._dest_excl_rows: row["cmb_col"]["values"] = cols

    def _add_filter_row(self, col="", op="=", val="", target_list=None, parent_frame=None, table_var=None, label="FILTRO"):
        if target_list is None:
            target_list = self._filter_rows
            parent_frame = self._frm_filters
            table_var = self.var_table
            
        frm = ttk.Frame(parent_frame)
        frm.pack(fill=tk.X, pady=1)
        cols_list = self.db.columns(table_var.get()) if (self.db and table_var.get()) else []
        logic_var = tk.StringVar(value="AND")
        if target_list:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS, state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text=label, width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols_list, width=18)
        cmb_col.pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar(value=op)
        ttk.Combobox(frm, textvariable=var_op, values=["=", "<>", ">", ">=", "<", "<=", "LIKE", "NOT LIKE", "IS NULL", "IS NOT NULL"], state="readonly", width=12).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=18).pack(side=tk.LEFT, padx=2)
        d = {"frm": frm, "logic": logic_var, "col": var_col, "cmb_col": cmb_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2, command=lambda: self._remove_row(d, target_list)).pack(side=tk.LEFT)
        target_list.append(d)

    def _add_dest_filter_row(self, col="", op="=", val=""):
        self._add_filter_row(col, op, val, self._dest_filter_rows, self._frm_dest_filters, self.var_dest_table)

    def _add_excl_row(self, col="", op="=", val=""):
        self._add_filter_row(col, op, val, self._excl_rows, self._frm_excl, self.var_table, label="ESCLUDI")

    def _add_dest_excl_row(self, col="", op="=", val=""):
        self._add_filter_row(col, op, val, self._dest_excl_rows, self._frm_dest_excl, self.var_dest_table, label="ESCLUDI")

    def _remove_row(self, r, t_list):
        r["frm"].destroy()
        t_list.remove(r)

    def _parse_rows(self, row_list):
        res = []
        for r in row_list:
            c, op, v, l = r["col"].get(), r["op"].get(), r["val"].get(), r["logic"].get()
            if c: res.append({"column": c, "operator": op, "value": v, "logic": l})
        return res

    def validate(self):
        if not self.var_table.get():
            return False, "Selezionare una Tabella Sorgente."
        if self.var_dest_table.get() and not self.var_link_src.get():
            return False, "Specificare la chiave di collegamento della Tabella Sorgente."
        return True, ""

    def get_config(self):
        cfg = {
            "table": self.var_table.get(),
            "conditions": self._parse_rows(self._filter_rows),
            "dest_table": self.var_dest_table.get(),
            "link_key_src": self.var_link_src.get(),
            "link_key_dest": self.var_link_dest.get(),
            "dest_conditions": self._parse_rows(self._dest_filter_rows)
        }
        excl = self._parse_rows(self._excl_rows)
        if excl:
            cfg["exclude_conditions"] = excl
        dest_excl = self._parse_rows(self._dest_excl_rows)
        if dest_excl:
            cfg["exclude_dest_conditions"] = dest_excl
        return cfg

    def set_config(self, c):
        self.var_table.set(c.get("table") or c.get("source_table", ""))
        self._on_table_sel()
        self.var_dest_table.set(c.get("dest_table", ""))
        self._on_dest_table_sel()
        self.var_link_src.set(c.get("link_key_src", ""))
        self.var_link_dest.set(c.get("link_key_dest", ""))
        
        for r in list(self._filter_rows): self._remove_row(r, self._filter_rows)
        for r in list(self._dest_filter_rows): self._remove_row(r, self._dest_filter_rows)
        for r in list(self._excl_rows): self._remove_row(r, self._excl_rows)
        for r in list(self._dest_excl_rows): self._remove_row(r, self._dest_excl_rows)
        
        for cond in c.get("conditions", []):
            self._add_filter_row(cond["column"], cond["operator"], cond.get("value", ""))
            
        for cond in c.get("dest_conditions", []):
            self._add_dest_filter_row(cond["column"], cond["operator"], cond.get("value", ""))

        for cond in c.get("exclude_conditions", []):
            self._add_excl_row(cond.get("column", ""), cond.get("operator", "="), cond.get("value", ""))

        for cond in c.get("exclude_dest_conditions", []):
            self._add_dest_excl_row(cond.get("column", ""), cond.get("operator", "="), cond.get("value", ""))


# ======================================================================== #
#  BUILDER AVANZATI                                                          #
# ======================================================================== #

class DependentConditionBuilder(ttk.Frame):
    """Builder per il controllo SE...ALLORA.
    Usa due istanze di MultiConditionBuilder: antecedente e conseguente."""

    def __init__(self, parent, db=None, on_table_change=None):
        super().__init__(parent, padding=5)
        self.db = db
        self.on_table_change = on_table_change

        # --- Selezione tabella ---
        top = ttk.Frame(self)
        top.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(top, text="Tabella:").pack(side=tk.LEFT)
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(top, textvariable=self.var_table, state="readonly", width=32)
        self.cmb_table.pack(side=tk.LEFT, padx=5)
        if self.db and self.db.connected:
            self.cmb_table["values"] = self.db.tables
        self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)

        # --- Colonne da visualizzare ---
        disp_frm = ttk.Frame(self)
        disp_frm.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(disp_frm, text="Colonne risultato (opz.):").pack(side=tk.LEFT)
        self.var_disp = tk.StringVar()
        self.cmb_disp = ttk.Combobox(disp_frm, textvariable=self.var_disp, width=20)
        self.cmb_disp.pack(side=tk.LEFT, padx=5)
        ttk.Button(disp_frm, text="+ Aggiungi", command=self._add_display_col).pack(side=tk.LEFT)
        self._display_cols = []
        self._disp_lbl = ttk.Label(disp_frm, text="(nessuna)", foreground="gray")
        self._disp_lbl.pack(side=tk.LEFT, padx=8)

        # --- SE (antecedente) ---
        frm_ante = ttk.LabelFrame(self, text="SE (antecedente) — la condizione di partenza", padding=5)
        frm_ante.pack(fill=tk.X, pady=4)
        self.ante_builder = MultiConditionBuilder(frm_ante, db=self.db)
        self.ante_builder.pack(fill=tk.X)

        # --- ALLORA (conseguente) ---
        frm_cons = ttk.LabelFrame(self, text="ALLORA (conseguente) — deve essere VERA, altrimenti è una violazione", padding=5)
        frm_cons.pack(fill=tk.X, pady=4)
        self.cons_builder = MultiConditionBuilder(frm_cons, db=self.db)
        self.cons_builder.pack(fill=tk.X)

        ttk.Label(self,
                  text="Il controllo segnala le righe dove il SE è vero ma l'ALLORA è falso.",
                  foreground="gray", font=("Segoe UI", 8, "italic")).pack(anchor=tk.W, pady=(4, 0))

    def _on_table_sel(self, _evt=None):
        table = self.var_table.get()
        cols = self.db.columns(table) if (self.db and table) else []
        self.cmb_disp["values"] = cols
        self.ante_builder.set_table(table)
        self.cons_builder.set_table(table)
        if self.on_table_change:
            self.on_table_change(table)

    def _add_display_col(self):
        col = self.var_disp.get().strip()
        if col and col not in self._display_cols:
            self._display_cols.append(col)
            self._disp_lbl.config(text=", ".join(self._display_cols))

    def validate(self):
        if not self.var_table.get():
            return False, "Selezionare la tabella."
        if not self.ante_builder.get_conditions():
            return False, "Definire almeno una condizione SE."
        if not self.cons_builder.get_conditions():
            return False, "Definire almeno una condizione ALLORA."
        return True, ""

    def get_config(self):
        return {
            "table": self.var_table.get(),
            "antecedent": self.ante_builder.get_conditions(),
            "consequent": self.cons_builder.get_conditions(),
            "display_columns": list(self._display_cols),
        }

    def set_config(self, c):
        self.var_table.set(c.get("table") or c.get("source_table", ""))
        self._on_table_sel()
        self._display_cols = list(c.get("display_columns", []))
        self._disp_lbl.config(text=", ".join(self._display_cols) if self._display_cols else "(nessuna)")
        self.ante_builder.set_conditions(c.get("antecedent", []))
        self.cons_builder.set_conditions(c.get("consequent", []))

    def clear(self):
        self.var_table.set("")
        self._display_cols = []
        self._disp_lbl.config(text="(nessuna)")
        self.ante_builder.clear()
        self.cons_builder.clear()


class RowCrossColumnBuilder(ttk.Frame):
    """Builder per il Controllo Coerenza tra due colonne della stessa riga.
    Esempio: DataScadenza >= DataRegistrazione."""

    _OPERATORS = [">=", ">", "<=", "<", "=", "<>"]

    def __init__(self, parent, db=None, on_table_change=None):
        super().__init__(parent, padding=5)
        self.db = db
        self.on_table_change = on_table_change
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Tabella:").grid(row=0, column=0, sticky="w", pady=3)
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(self, textvariable=self.var_table, state="readonly", width=32)
        self.cmb_table.grid(row=0, column=1, sticky="ew", padx=5)
        if self.db and self.db.connected:
            self.cmb_table["values"] = self.db.tables
        self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)

        # Riga: [Colonna Sinistra] [Operatore] [Colonna Destra]
        ttk.Label(self, text="Regola:").grid(row=1, column=0, sticky="w", pady=3)
        rule_frm = ttk.Frame(self)
        rule_frm.grid(row=1, column=1, sticky="ew", padx=5)

        self.var_left = tk.StringVar()
        self.cmb_left = ttk.Combobox(rule_frm, textvariable=self.var_left, width=20)
        self.cmb_left.pack(side=tk.LEFT, padx=(0, 4))

        ttk.Label(rule_frm, text="DEVE essere").pack(side=tk.LEFT, padx=2)

        self.var_op = tk.StringVar(value=">=")
        ttk.Combobox(rule_frm, textvariable=self.var_op,
                     values=self._OPERATORS, state="readonly", width=5).pack(side=tk.LEFT, padx=4)

        self.var_right = tk.StringVar()
        self.cmb_right = ttk.Combobox(rule_frm, textvariable=self.var_right, width=20)
        self.cmb_right.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(self,
                  text="Il controllo segnala le righe che VIOLANO questa regola.",
                  foreground="gray", font=("Segoe UI", 8, "italic")).grid(row=2, column=0, columnspan=2, sticky="w", pady=2)

        # Opzioni
        ttk.Label(self, text="Opzioni:").grid(row=3, column=0, sticky="w", pady=3)
        opt_frm = ttk.Frame(self)
        opt_frm.grid(row=3, column=1, sticky="ew", padx=5)
        self.var_ignore_nulls = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frm, text="Ignora righe con valori nulli",
                        variable=self.var_ignore_nulls).pack(side=tk.LEFT)

        # Colonne da mostrare
        ttk.Label(self, text="Colonne risultato:").grid(row=4, column=0, sticky="w", pady=3)
        disp_frm = ttk.Frame(self)
        disp_frm.grid(row=4, column=1, sticky="ew", padx=5)
        self.var_disp_sel = tk.StringVar()
        self.cmb_disp = ttk.Combobox(disp_frm, textvariable=self.var_disp_sel, width=18)
        self.cmb_disp.pack(side=tk.LEFT)
        ttk.Button(disp_frm, text="+", width=2, command=self._add_disp).pack(side=tk.LEFT, padx=3)
        self._display_cols = []
        self._disp_lbl = ttk.Label(disp_frm, text="(nessuna)", foreground="gray")
        self._disp_lbl.pack(side=tk.LEFT, padx=6)

        # Pre-filtri
        ttk.Separator(self, orient=tk.HORIZONTAL).grid(row=5, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(self, text="Filtri aggiuntivi:", font=("Segoe UI", 9, "bold")).grid(row=6, column=0, columnspan=2, sticky="w")
        self._filter_rows = []
        self._excl_rows = []
        self._frm_filters = ttk.Frame(self)
        self._frm_filters.grid(row=7, column=0, columnspan=2, sticky="ew", padx=8)
        btn_f = ttk.Frame(self)
        btn_f.grid(row=8, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Button(btn_f, text="+ Filtro", command=self._add_filter).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_f, text="+ Esclusione", command=self._add_excl).pack(side=tk.LEFT, padx=2)

    def _on_table_sel(self, _evt=None):
        table = self.var_table.get()
        cols = self.db.columns(table) if (self.db and table) else []
        self.cmb_left["values"] = cols
        self.cmb_right["values"] = cols
        self.cmb_disp["values"] = cols
        for r in self._filter_rows + self._excl_rows:
            r["cmb_col"]["values"] = cols
        if self.on_table_change:
            self.on_table_change(table)

    def _add_disp(self):
        col = self.var_disp_sel.get().strip()
        if col and col not in self._display_cols:
            self._display_cols.append(col)
            self._disp_lbl.config(text=", ".join(self._display_cols))

    def _add_row(self, target_list, label, col="", op="=", val=""):
        cols_list = self.db.columns(self.var_table.get()) if (self.db and self.var_table.get()) else []
        frm = ttk.Frame(self._frm_filters)
        frm.pack(fill=tk.X, pady=1)
        logic_var = tk.StringVar(value="AND")
        if target_list:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS, state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text=label, width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols_list, width=18)
        cmb_col.pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar(value=op)
        ttk.Combobox(frm, textvariable=var_op,
                     values=["=", "<>", ">", ">=", "<", "<=", "LIKE", "NOT LIKE", "IS NULL", "IS NOT NULL"],
                     state="readonly", width=12).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=18).pack(side=tk.LEFT, padx=2)
        d = {"frm": frm, "logic": logic_var, "col": var_col, "cmb_col": cmb_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2, command=lambda: self._rm_row(d, target_list)).pack(side=tk.LEFT)
        target_list.append(d)

    def _add_filter(self): self._add_row(self._filter_rows, "FILTRO")
    def _add_excl(self):   self._add_row(self._excl_rows, "ESCLUDI")

    def _rm_row(self, r, lst):
        r["frm"].destroy()
        lst.remove(r)

    def _parse_rows(self, lst):
        return [{"column": r["col"].get(), "operator": r["op"].get(), "value": r["val"].get(), "logic": r["logic"].get()}
                for r in lst if r["col"].get()]

    def validate(self):
        if not self.var_table.get(): return False, "Selezionare la tabella."
        if not self.var_left.get():  return False, "Selezionare la Colonna Sinistra."
        if not self.var_right.get(): return False, "Selezionare la Colonna Destra."
        if self.var_left.get() == self.var_right.get():
            return False, "Le due colonne devono essere diverse."
        return True, ""

    def get_config(self):
        return {
            "table":           self.var_table.get(),
            "left_column":     self.var_left.get(),
            "operator":        self.var_op.get(),
            "right_column":    self.var_right.get(),
            "ignore_nulls":    self.var_ignore_nulls.get(),
            "display_columns": list(self._display_cols),
            "conditions":      self._parse_rows(self._filter_rows),
            "exclude_conditions": self._parse_rows(self._excl_rows),
        }

    def set_config(self, c):
        self.var_table.set(c.get("table") or c.get("source_table", ""))
        self._on_table_sel()
        self.var_left.set(c.get("left_column", ""))
        self.var_op.set(c.get("operator", ">="))
        self.var_right.set(c.get("right_column", ""))
        self.var_ignore_nulls.set(c.get("ignore_nulls", True))
        self._display_cols = list(c.get("display_columns", []))
        self._disp_lbl.config(text=", ".join(self._display_cols) if self._display_cols else "(nessuna)")
        for r in list(self._filter_rows): self._rm_row(r, self._filter_rows)
        for r in list(self._excl_rows):   self._rm_row(r, self._excl_rows)
        for cond in c.get("conditions", []):
            self._add_row(self._filter_rows, "FILTRO", cond["column"], cond["operator"], cond.get("value", ""))
        for cond in c.get("exclude_conditions", []):
            self._add_row(self._excl_rows, "ESCLUDI", cond["column"], cond["operator"], cond.get("value", ""))

    def clear(self):
        self.var_table.set("")
        self.var_left.set("")
        self.var_right.set("")
        self._display_cols = []
        self._disp_lbl.config(text="(nessuna)")
        for r in list(self._filter_rows): self._rm_row(r, self._filter_rows)
        for r in list(self._excl_rows):   self._rm_row(r, self._excl_rows)


class LookupValidationBuilder(ttk.Frame):
    """Builder per il Dizionario Obbligato (Lookup Validation).
    Segnala i record dove il valore di una colonna non appartiene alla lista ammessa."""

    def __init__(self, parent, db=None, on_table_change=None):
        super().__init__(parent, padding=5)
        self.db = db
        self.on_table_change = on_table_change
        self.columnconfigure(1, weight=1)

        # Tabella e Colonna
        ttk.Label(self, text="Tabella:").grid(row=0, column=0, sticky="w", pady=3)
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(self, textvariable=self.var_table, state="readonly", width=32)
        self.cmb_table.grid(row=0, column=1, sticky="ew", padx=5)
        if self.db and self.db.connected:
            self.cmb_table["values"] = self.db.tables
        self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)

        ttk.Label(self, text="Colonna da validare:").grid(row=1, column=0, sticky="w", pady=3)
        self.var_col = tk.StringVar()
        self.cmb_col = ttk.Combobox(self, textvariable=self.var_col, width=32)
        self.cmb_col.grid(row=1, column=1, sticky="ew", padx=5)

        # Valori ammessi
        ttk.Label(self, text="Valori ammessi\n(uno per riga):").grid(row=2, column=0, sticky="nw", pady=3)
        dict_frm = ttk.Frame(self)
        dict_frm.grid(row=2, column=1, sticky="ew", padx=5)

        self.txt_allowed = tk.Text(dict_frm, height=5, width=35, wrap=tk.WORD)
        self.txt_allowed.pack(side=tk.LEFT, fill=tk.BOTH)
        scrollbar = ttk.Scrollbar(dict_frm, orient=tk.VERTICAL, command=self.txt_allowed.yview)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)
        self.txt_allowed.configure(yscrollcommand=scrollbar.set)

        btn_auto = ttk.Button(self, text="Auto-popola dai valori distinti del DB",
                              command=self._auto_populate)
        btn_auto.grid(row=3, column=1, sticky="w", padx=5, pady=2)

        # Opzioni
        ttk.Label(self, text="Opzioni:").grid(row=4, column=0, sticky="w", pady=3)
        opt_frm = ttk.Frame(self)
        opt_frm.grid(row=4, column=1, sticky="ew", padx=5)
        self.var_case = tk.BooleanVar(value=True)
        self.var_trim = tk.BooleanVar(value=True)
        self.var_ignore_empty = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frm, text="Case-insensitive", variable=self.var_case).pack(side=tk.LEFT, padx=3)
        ttk.Checkbutton(opt_frm, text="Ignora spazi", variable=self.var_trim).pack(side=tk.LEFT, padx=3)
        ttk.Checkbutton(opt_frm, text="Ignora vuoti", variable=self.var_ignore_empty).pack(side=tk.LEFT, padx=3)

        # Fuzzy suggestion
        ttk.Label(self, text="Suggerimento fuzzy:").grid(row=5, column=0, sticky="w", pady=3)
        fz_frm = ttk.Frame(self)
        fz_frm.grid(row=5, column=1, sticky="ew", padx=5)
        self.var_suggest = tk.BooleanVar(value=True)
        ttk.Checkbutton(fz_frm, text="Abilita (mostra il valore simile più vicino)",
                        variable=self.var_suggest, command=self._toggle_fuzzy).pack(side=tk.LEFT)
        ttk.Label(fz_frm, text="  Soglia:").pack(side=tk.LEFT)
        self.var_sim_thresh = tk.IntVar(value=60)
        self.spin_thresh = ttk.Spinbox(fz_frm, textvariable=self.var_sim_thresh,
                                       from_=1, to=100, width=5)
        self.spin_thresh.pack(side=tk.LEFT, padx=3)
        ttk.Label(fz_frm, text="%").pack(side=tk.LEFT)

        # Colonne da mostrare
        ttk.Label(self, text="Colonne risultato:").grid(row=6, column=0, sticky="w", pady=3)
        disp_frm = ttk.Frame(self)
        disp_frm.grid(row=6, column=1, sticky="ew", padx=5)
        self.var_disp_sel = tk.StringVar()
        self.cmb_disp = ttk.Combobox(disp_frm, textvariable=self.var_disp_sel, width=18)
        self.cmb_disp.pack(side=tk.LEFT)
        ttk.Button(disp_frm, text="+", width=2, command=self._add_disp).pack(side=tk.LEFT, padx=3)
        self._display_cols = []
        self._disp_lbl = ttk.Label(disp_frm, text="(nessuna)", foreground="gray")
        self._disp_lbl.pack(side=tk.LEFT, padx=6)

        # Pre-filtri
        ttk.Separator(self, orient=tk.HORIZONTAL).grid(row=7, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(self, text="Filtri aggiuntivi:", font=("Segoe UI", 9, "bold")).grid(row=8, column=0, columnspan=2, sticky="w")
        self._filter_rows = []
        self._excl_rows = []
        self._frm_filters = ttk.Frame(self)
        self._frm_filters.grid(row=9, column=0, columnspan=2, sticky="ew", padx=8)
        btn_f = ttk.Frame(self)
        btn_f.grid(row=10, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Button(btn_f, text="+ Filtro", command=self._add_filter).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_f, text="+ Esclusione", command=self._add_excl).pack(side=tk.LEFT, padx=2)

    def _toggle_fuzzy(self):
        state = "normal" if self.var_suggest.get() else "disabled"
        self.spin_thresh.config(state=state)

    def _on_table_sel(self, _evt=None):
        table = self.var_table.get()
        cols = self.db.columns(table) if (self.db and table) else []
        self.cmb_col["values"] = cols
        self.cmb_disp["values"] = cols
        for r in self._filter_rows + self._excl_rows:
            r["cmb_col"]["values"] = cols
        if self.on_table_change:
            self.on_table_change(table)

    def _auto_populate(self):
        table = self.var_table.get()
        col = self.var_col.get()
        if not table or not col:
            messagebox.showwarning("Attenzione", "Selezionare prima Tabella e Colonna.")
            return
        try:
            _, rows = self.db.fetch(f"SELECT DISTINCT [{col}] FROM [{table}] WHERE [{col}] IS NOT NULL ORDER BY [{col}]")
            values = [str(r[0]).strip() for r in rows if r[0] is not None]
            self.txt_allowed.delete("1.0", tk.END)
            self.txt_allowed.insert("1.0", "\n".join(values))
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    def _add_disp(self):
        col = self.var_disp_sel.get().strip()
        if col and col not in self._display_cols:
            self._display_cols.append(col)
            self._disp_lbl.config(text=", ".join(self._display_cols))

    def _add_row(self, target_list, label, col="", op="=", val=""):
        cols_list = self.db.columns(self.var_table.get()) if (self.db and self.var_table.get()) else []
        frm = ttk.Frame(self._frm_filters)
        frm.pack(fill=tk.X, pady=1)
        logic_var = tk.StringVar(value="AND")
        if target_list:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS, state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text=label, width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols_list, width=18)
        cmb_col.pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar(value=op)
        ttk.Combobox(frm, textvariable=var_op,
                     values=["=", "<>", ">", ">=", "<", "<=", "LIKE", "NOT LIKE", "IS NULL", "IS NOT NULL"],
                     state="readonly", width=12).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=18).pack(side=tk.LEFT, padx=2)
        d = {"frm": frm, "logic": logic_var, "col": var_col, "cmb_col": cmb_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2, command=lambda: self._rm_row(d, target_list)).pack(side=tk.LEFT)
        target_list.append(d)

    def _add_filter(self): self._add_row(self._filter_rows, "FILTRO")
    def _add_excl(self):   self._add_row(self._excl_rows, "ESCLUDI")

    def _rm_row(self, r, lst):
        r["frm"].destroy()
        lst.remove(r)

    def _parse_rows(self, lst):
        return [{"column": r["col"].get(), "operator": r["op"].get(), "value": r["val"].get(), "logic": r["logic"].get()}
                for r in lst if r["col"].get()]

    def _get_allowed_values(self):
        raw = self.txt_allowed.get("1.0", tk.END)
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def validate(self):
        if not self.var_table.get(): return False, "Selezionare la tabella."
        if not self.var_col.get():   return False, "Selezionare la colonna da validare."
        if not self._get_allowed_values():
            return False, "Inserire almeno un valore nel dizionario ammesso."
        return True, ""

    def get_config(self):
        return {
            "table":                self.var_table.get(),
            "column":               self.var_col.get(),
            "allowed_values":       self._get_allowed_values(),
            "case_insensitive":     self.var_case.get(),
            "trim":                 self.var_trim.get(),
            "ignore_empty":         self.var_ignore_empty.get(),
            "suggest_similar":      self.var_suggest.get(),
            "similarity_threshold": self.var_sim_thresh.get(),
            "display_columns":      list(self._display_cols),
            "conditions":           self._parse_rows(self._filter_rows),
            "exclude_conditions":   self._parse_rows(self._excl_rows),
        }

    def set_config(self, c):
        self.var_table.set(c.get("table") or c.get("source_table", ""))
        self._on_table_sel()
        self.var_col.set(c.get("column", ""))
        self.txt_allowed.delete("1.0", tk.END)
        self.txt_allowed.insert("1.0", "\n".join(c.get("allowed_values", [])))
        self.var_case.set(c.get("case_insensitive", True))
        self.var_trim.set(c.get("trim", True))
        self.var_ignore_empty.set(c.get("ignore_empty", True))
        self.var_suggest.set(c.get("suggest_similar", True))
        self.var_sim_thresh.set(c.get("similarity_threshold", 60))
        self._display_cols = list(c.get("display_columns", []))
        self._disp_lbl.config(text=", ".join(self._display_cols) if self._display_cols else "(nessuna)")
        for r in list(self._filter_rows): self._rm_row(r, self._filter_rows)
        for r in list(self._excl_rows):   self._rm_row(r, self._excl_rows)
        for cond in c.get("conditions", []):
            self._add_row(self._filter_rows, "FILTRO", cond["column"], cond["operator"], cond.get("value", ""))
        for cond in c.get("exclude_conditions", []):
            self._add_row(self._excl_rows, "ESCLUDI", cond["column"], cond["operator"], cond.get("value", ""))

    def clear(self):
        self.var_table.set("")
        self.var_col.set("")
        self.txt_allowed.delete("1.0", tk.END)
        self._display_cols = []
        self._disp_lbl.config(text="(nessuna)")
        for r in list(self._filter_rows): self._rm_row(r, self._filter_rows)
        for r in list(self._excl_rows):   self._rm_row(r, self._excl_rows)


class AggregateThresholdBuilder(ttk.Frame):
    """Builder per il Controllo Soglia Aggregata.
    Raggruppa per N colonne, calcola SUM/COUNT/AVG/MIN/MAX e segnala i gruppi fuori soglia."""

    _AGG_FUNCTIONS = ["SUM", "COUNT", "AVG", "MIN", "MAX"]
    _OPERATORS = [">", ">=", "<", "<=", "=", "<>", "tra"]

    def __init__(self, parent, db=None, on_table_change=None):
        super().__init__(parent, padding=5)
        self.db = db
        self.on_table_change = on_table_change
        self.columnconfigure(1, weight=1)

        # Tabella
        ttk.Label(self, text="Tabella:").grid(row=0, column=0, sticky="w", pady=3)
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(self, textvariable=self.var_table, state="readonly", width=32)
        self.cmb_table.grid(row=0, column=1, sticky="ew", padx=5)
        if self.db and self.db.connected:
            self.cmb_table["values"] = self.db.tables
        self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)

        # Raggruppa per (listbox selezionabile)
        ttk.Label(self, text="Raggruppa per:").grid(row=1, column=0, sticky="nw", pady=3)
        grp_frm = ttk.Frame(self)
        grp_frm.grid(row=1, column=1, sticky="ew", padx=5)

        self.var_grp_sel = tk.StringVar()
        self.cmb_grp = ttk.Combobox(grp_frm, textvariable=self.var_grp_sel, width=20)
        self.cmb_grp.pack(side=tk.LEFT)
        ttk.Button(grp_frm, text="+ Aggiungi", command=self._add_group_col).pack(side=tk.LEFT, padx=4)
        ttk.Button(grp_frm, text="- Rimuovi ultimo", command=self._remove_last_group).pack(side=tk.LEFT)

        self._group_by = []
        self._grp_lbl = ttk.Label(self, text="Colonne gruppo: (nessuna)", foreground="gray")
        self._grp_lbl.grid(row=2, column=0, columnspan=2, sticky="w", padx=5)

        # Funzione aggregata + colonna + operatore + soglia
        ttk.Label(self, text="Aggregazione:").grid(row=3, column=0, sticky="w", pady=3)
        agg_frm = ttk.Frame(self)
        agg_frm.grid(row=3, column=1, sticky="ew", padx=5)

        self.var_agg_fn = tk.StringVar(value="SUM")
        self.cmb_agg_fn = ttk.Combobox(agg_frm, textvariable=self.var_agg_fn,
                                        values=self._AGG_FUNCTIONS, state="readonly", width=8)
        self.cmb_agg_fn.pack(side=tk.LEFT, padx=(0, 4))
        self.cmb_agg_fn.bind("<<ComboboxSelected>>", self._on_fn_change)

        ttk.Label(agg_frm, text="(").pack(side=tk.LEFT)
        self.var_agg_col = tk.StringVar()
        self.cmb_agg_col = ttk.Combobox(agg_frm, textvariable=self.var_agg_col, width=18)
        self.cmb_agg_col.pack(side=tk.LEFT, padx=2)
        ttk.Label(agg_frm, text=")").pack(side=tk.LEFT)

        ttk.Label(self, text="Soglia:").grid(row=4, column=0, sticky="w", pady=3)
        thr_frm = ttk.Frame(self)
        thr_frm.grid(row=4, column=1, sticky="ew", padx=5)

        self.var_op = tk.StringVar(value=">")
        self.cmb_op = ttk.Combobox(thr_frm, textvariable=self.var_op, values=self._OPERATORS,
                                   state="readonly", width=6)
        self.cmb_op.pack(side=tk.LEFT, padx=(0, 4))
        self.cmb_op.bind("<<ComboboxSelected>>", self._on_op_change)
        self.var_threshold = tk.StringVar(value="0")
        ttk.Entry(thr_frm, textvariable=self.var_threshold, width=10).pack(side=tk.LEFT)
        # Secondo estremo, visibile solo con operatore "tra" (intervallo)
        self._lbl_and = ttk.Label(thr_frm, text=" e ")
        self.var_threshold_max = tk.StringVar(value="")
        self._ent_threshold_max = ttk.Entry(thr_frm, textvariable=self.var_threshold_max, width=10)
        self._lbl_thr_hint = ttk.Label(thr_frm, text="(es. 48; con 'tra' = intervallo X–Y)")
        self._lbl_thr_hint.pack(side=tk.LEFT, padx=8)

        # Note funzione COUNT
        self._lbl_count_note = ttk.Label(self,
                                          text="Con COUNT la colonna è opzionale (conta le righe del gruppo).",
                                          foreground="gray", font=("Segoe UI", 8, "italic"))
        self._lbl_count_note.grid(row=5, column=0, columnspan=2, sticky="w", padx=5)
        self._lbl_count_note.grid_remove()

        # Pre-filtri
        ttk.Separator(self, orient=tk.HORIZONTAL).grid(row=6, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(self, text="Filtri aggiuntivi (WHERE):", font=("Segoe UI", 9, "bold")).grid(row=7, column=0, columnspan=2, sticky="w")
        self._filter_rows = []
        self._excl_rows = []
        self._frm_filters = ttk.Frame(self)
        self._frm_filters.grid(row=8, column=0, columnspan=2, sticky="ew", padx=8)
        btn_f = ttk.Frame(self)
        btn_f.grid(row=9, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Button(btn_f, text="+ Filtro", command=self._add_filter).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_f, text="+ Esclusione", command=self._add_excl).pack(side=tk.LEFT, padx=2)

    def _on_fn_change(self, _evt=None):
        if self.var_agg_fn.get() == "COUNT":
            self.cmb_agg_col.config(state="disabled")
            self._lbl_count_note.grid()
        else:
            self.cmb_agg_col.config(state="normal")
            self._lbl_count_note.grid_remove()

    def _on_op_change(self, _evt=None):
        """Mostra il secondo estremo solo per l'operatore 'tra' (intervallo)."""
        if self.var_op.get() == "tra":
            self._lbl_and.pack(side=tk.LEFT, before=self._lbl_thr_hint)
            self._ent_threshold_max.pack(side=tk.LEFT, before=self._lbl_thr_hint)
        else:
            self._ent_threshold_max.pack_forget()
            self._lbl_and.pack_forget()

    def _on_table_sel(self, _evt=None):
        table = self.var_table.get()
        cols = self.db.columns(table) if (self.db and table) else []
        self.cmb_grp["values"] = cols
        self.cmb_agg_col["values"] = cols
        for r in self._filter_rows + self._excl_rows:
            r["cmb_col"]["values"] = cols
        if self.on_table_change:
            self.on_table_change(table)

    def _add_group_col(self):
        col = self.var_grp_sel.get().strip()
        if col and col not in self._group_by:
            self._group_by.append(col)
            self._grp_lbl.config(text="Colonne gruppo: " + ", ".join(self._group_by))

    def _remove_last_group(self):
        if self._group_by:
            self._group_by.pop()
            label = ", ".join(self._group_by) if self._group_by else "(nessuna)"
            self._grp_lbl.config(text="Colonne gruppo: " + label)

    def _add_row(self, target_list, label, col="", op="=", val=""):
        cols_list = self.db.columns(self.var_table.get()) if (self.db and self.var_table.get()) else []
        frm = ttk.Frame(self._frm_filters)
        frm.pack(fill=tk.X, pady=1)
        logic_var = tk.StringVar(value="AND")
        if target_list:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS, state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text=label, width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols_list, width=18)
        cmb_col.pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar(value=op)
        ttk.Combobox(frm, textvariable=var_op,
                     values=["=", "<>", ">", ">=", "<", "<=", "LIKE", "NOT LIKE", "IS NULL", "IS NOT NULL"],
                     state="readonly", width=12).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=18).pack(side=tk.LEFT, padx=2)
        d = {"frm": frm, "logic": logic_var, "col": var_col, "cmb_col": cmb_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2, command=lambda: self._rm_row(d, target_list)).pack(side=tk.LEFT)
        target_list.append(d)

    def _add_filter(self): self._add_row(self._filter_rows, "FILTRO")
    def _add_excl(self):   self._add_row(self._excl_rows, "ESCLUDI")

    def _rm_row(self, r, lst):
        r["frm"].destroy()
        lst.remove(r)

    def _parse_rows(self, lst):
        return [{"column": r["col"].get(), "operator": r["op"].get(), "value": r["val"].get(), "logic": r["logic"].get()}
                for r in lst if r["col"].get()]

    def validate(self):
        if not self.var_table.get():
            return False, "Selezionare la tabella."
        if not self._group_by:
            return False, "Aggiungere almeno una colonna di raggruppamento."
        fn = self.var_agg_fn.get()
        if fn != "COUNT" and not self.var_agg_col.get():
            return False, f"Selezionare la colonna da aggregare per {fn}."
        try:
            float(self.var_threshold.get())
        except ValueError:
            return False, "La soglia deve essere un numero."
        if self.var_op.get() == "tra":
            try:
                float(self.var_threshold_max.get())
            except ValueError:
                return False, "Con l'operatore 'tra' inserire anche il secondo valore (numero)."
        return True, ""

    def get_config(self):
        cfg = {
            "table":           self.var_table.get(),
            "group_by":        list(self._group_by),
            "agg_function":    self.var_agg_fn.get(),
            "agg_column":      self.var_agg_col.get(),
            "operator":        self.var_op.get(),
            "threshold":       float(self.var_threshold.get()) if self.var_threshold.get() else 0,
            "conditions":      self._parse_rows(self._filter_rows),
            "exclude_conditions": self._parse_rows(self._excl_rows),
        }
        if self.var_op.get() == "tra":
            cfg["threshold_max"] = (
                float(self.var_threshold_max.get()) if self.var_threshold_max.get() else cfg["threshold"]
            )
        return cfg

    def set_config(self, c):
        self.var_table.set(c.get("table") or c.get("source_table", ""))
        self._on_table_sel()
        self._group_by = list(c.get("group_by", []))
        label = ", ".join(self._group_by) if self._group_by else "(nessuna)"
        self._grp_lbl.config(text="Colonne gruppo: " + label)
        self.var_agg_fn.set(c.get("agg_function", "SUM"))
        self._on_fn_change()
        self.var_agg_col.set(c.get("agg_column", ""))
        self.var_op.set(c.get("operator", ">"))
        self.var_threshold.set(str(c.get("threshold", 0)))
        if "threshold_max" in c:
            self.var_threshold_max.set(str(c.get("threshold_max", "")))
        self._on_op_change()
        for r in list(self._filter_rows): self._rm_row(r, self._filter_rows)
        for r in list(self._excl_rows):   self._rm_row(r, self._excl_rows)
        for cond in c.get("conditions", []):
            self._add_row(self._filter_rows, "FILTRO", cond["column"], cond["operator"], cond.get("value", ""))
        for cond in c.get("exclude_conditions", []):
            self._add_row(self._excl_rows, "ESCLUDI", cond["column"], cond["operator"], cond.get("value", ""))

    def clear(self):
        self.var_table.set("")
        self._group_by = []
        self._grp_lbl.config(text="Colonne gruppo: (nessuna)")
        self.var_agg_col.set("")
        self.var_threshold.set("0")
        for r in list(self._filter_rows): self._rm_row(r, self._filter_rows)
        for r in list(self._excl_rows):   self._rm_row(r, self._excl_rows)


class AggregateMultiTableBuilder(ttk.Frame):
    """Soglia Aggregata Multi-tabella: somma (o aggrega) un valore per gruppo
    unendo PIU' tabelle dello stesso database, anche con nomi colonna diversi.
    Ogni sorgente mappa la propria colonna gruppo e valore; i filtri sono
    globali (stessi nomi colonna in tutte le tabelle)."""

    _AGG_FUNCTIONS = ["SUM", "COUNT", "AVG", "MIN", "MAX"]
    _OPERATORS = [">", ">=", "<", "<=", "=", "<>", "tra"]

    def __init__(self, parent, db=None, on_table_change=None):
        super().__init__(parent, padding=5)
        self.db = db
        self.on_table_change = on_table_change

        ttk.Label(self, text="Tabelle sorgente (somma unita su più tabelle):",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(self, text="Per ogni tabella scegli la colonna gruppo (es. Diffusori) e "
                             "la colonna valore (es. mh). I nomi possono differire tra tabelle.",
                  foreground="gray").pack(anchor="w")
        self._frm_sources = ttk.Frame(self)
        self._frm_sources.pack(fill=tk.X, pady=2)
        self._sources = []
        ttk.Button(self, text="+ Aggiungi tabella", command=self._add_source).pack(anchor="w", pady=2)

        agg = ttk.Frame(self)
        agg.pack(fill=tk.X, pady=(8, 2))
        ttk.Label(agg, text="Aggregazione:").pack(side=tk.LEFT)
        self.var_agg_fn = tk.StringVar(value="SUM")
        ttk.Combobox(agg, textvariable=self.var_agg_fn, values=self._AGG_FUNCTIONS,
                     state="readonly", width=8).pack(side=tk.LEFT, padx=4)
        ttk.Label(agg, text="Soglia:").pack(side=tk.LEFT, padx=(10, 2))
        self.var_op = tk.StringVar(value=">=")
        self.cmb_op = ttk.Combobox(agg, textvariable=self.var_op, values=self._OPERATORS,
                                   state="readonly", width=6)
        self.cmb_op.pack(side=tk.LEFT)
        self.cmb_op.bind("<<ComboboxSelected>>", self._on_op_change)
        self.var_threshold = tk.StringVar(value="0")
        ttk.Entry(agg, textvariable=self.var_threshold, width=8).pack(side=tk.LEFT, padx=4)
        self._lbl_and = ttk.Label(agg, text=" e ")
        self.var_threshold_max = tk.StringVar(value="")
        self._ent_threshold_max = ttk.Entry(agg, textvariable=self.var_threshold_max, width=8)
        self._lbl_hint = ttk.Label(agg, text="(con 'tra' = intervallo X–Y)")
        self._lbl_hint.pack(side=tk.LEFT, padx=8)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)
        ttk.Label(self, text="Filtri globali (WHERE, stessi nomi colonna in tutte le tabelle):",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self._frm_filters = ttk.Frame(self)
        self._frm_filters.pack(fill=tk.X, padx=4)
        self._filter_rows = []
        self._excl_rows = []
        bf = ttk.Frame(self)
        bf.pack(anchor="w", pady=3)
        ttk.Button(bf, text="+ Filtro", command=self._add_filter).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="+ Esclusione", command=self._add_excl).pack(side=tk.LEFT, padx=2)

    def _all_tables(self):
        return self.db.tables if (self.db and getattr(self.db, "connected", False)) else []

    def _filter_cols(self):
        if self.db and self._sources and self._sources[0]["table"].get():
            return self.db.columns(self._sources[0]["table"].get())
        return []

    def _refresh_filter_cols(self):
        cols = self._filter_cols()
        for r in self._filter_rows + self._excl_rows:
            r["cmb_col"]["values"] = cols

    def _add_source(self, table="", group_col="", value_col=""):
        frm = ttk.Frame(self._frm_sources)
        frm.pack(fill=tk.X, pady=1)
        var_t = tk.StringVar(value=table)
        cmb_t = ttk.Combobox(frm, textvariable=var_t, values=self._all_tables(),
                             state="readonly", width=18)
        cmb_t.pack(side=tk.LEFT, padx=2)
        ttk.Label(frm, text="gruppo:").pack(side=tk.LEFT)
        var_g = tk.StringVar(value=group_col)
        cmb_g = ttk.Combobox(frm, textvariable=var_g, width=16)
        cmb_g.pack(side=tk.LEFT, padx=2)
        ttk.Label(frm, text="valore:").pack(side=tk.LEFT)
        var_v = tk.StringVar(value=value_col)
        cmb_v = ttk.Combobox(frm, textvariable=var_v, width=16)
        cmb_v.pack(side=tk.LEFT, padx=2)
        row = {"frm": frm, "table": var_t, "group": var_g, "value": var_v,
               "cmb_g": cmb_g, "cmb_v": cmb_v}
        cmb_t.bind("<<ComboboxSelected>>", lambda _e, r=row: self._refresh_source_cols(r))
        ttk.Button(frm, text="✕", width=2, command=lambda r=row: self._remove_source(r)).pack(side=tk.LEFT)
        self._sources.append(row)
        if table:
            self._refresh_source_cols(row)
        return row

    def _refresh_source_cols(self, row):
        cols = self.db.columns(row["table"].get()) if (self.db and row["table"].get()) else []
        row["cmb_g"]["values"] = cols
        row["cmb_v"]["values"] = cols
        self._refresh_filter_cols()

    def _remove_source(self, row):
        row["frm"].destroy()
        self._sources.remove(row)

    def _on_op_change(self, _evt=None):
        if self.var_op.get() == "tra":
            self._lbl_and.pack(side=tk.LEFT, before=self._lbl_hint)
            self._ent_threshold_max.pack(side=tk.LEFT, before=self._lbl_hint)
        else:
            self._ent_threshold_max.pack_forget()
            self._lbl_and.pack_forget()

    def _add_row(self, target_list, label, col="", op="=", val=""):
        cols = self._filter_cols()
        frm = ttk.Frame(self._frm_filters)
        frm.pack(fill=tk.X, pady=1)
        logic_var = tk.StringVar(value="AND")
        if target_list:
            ttk.Combobox(frm, textvariable=logic_var, values=constants.LOGIC_OPS,
                         state="readonly", width=5).pack(side=tk.LEFT, padx=2)
        else:
            ttk.Label(frm, text=label, width=7).pack(side=tk.LEFT, padx=2)
        var_col = tk.StringVar(value=col)
        cmb_col = ttk.Combobox(frm, textvariable=var_col, values=cols, width=16)
        cmb_col.pack(side=tk.LEFT, padx=2)
        var_op = tk.StringVar(value=op)
        ttk.Combobox(frm, textvariable=var_op,
                     values=["=", "<>", ">", ">=", "<", "<=", "LIKE", "NOT LIKE", "IS NULL", "IS NOT NULL"],
                     state="readonly", width=10).pack(side=tk.LEFT, padx=2)
        var_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=var_val, width=14).pack(side=tk.LEFT, padx=2)
        d = {"frm": frm, "logic": logic_var, "col": var_col, "cmb_col": cmb_col, "op": var_op, "val": var_val}
        ttk.Button(frm, text="✕", width=2, command=lambda: self._rm_row(d, target_list)).pack(side=tk.LEFT)
        target_list.append(d)

    def _add_filter(self): self._add_row(self._filter_rows, "FILTRO")
    def _add_excl(self):   self._add_row(self._excl_rows, "ESCLUDI")

    def _rm_row(self, r, lst):
        r["frm"].destroy()
        lst.remove(r)

    def _parse_rows(self, lst):
        return [{"column": r["col"].get(), "operator": r["op"].get(), "value": r["val"].get(), "logic": r["logic"].get()}
                for r in lst if r["col"].get()]

    def validate(self):
        real = [r for r in self._sources if r["table"].get() and r["group"].get()]
        if not real:
            return False, "Aggiungere almeno una tabella con la colonna gruppo."
        if self.var_agg_fn.get() != "COUNT":
            for r in real:
                if not r["value"].get():
                    return False, "Selezionare la colonna valore in ogni tabella (per SUM/AVG/MIN/MAX)."
        try:
            float(self.var_threshold.get())
        except ValueError:
            return False, "La soglia deve essere un numero."
        if self.var_op.get() == "tra":
            try:
                float(self.var_threshold_max.get())
            except ValueError:
                return False, "Con l'operatore 'tra' inserire anche il secondo valore (numero)."
        return True, ""

    def get_config(self):
        sources = []
        for r in self._sources:
            t = r["table"].get().strip()
            if not t:
                continue
            sources.append({
                "table": t,
                "group_col": r["group"].get().strip(),
                "value_col": r["value"].get().strip(),
            })
        cfg = {
            "sources": sources,
            "agg_function": self.var_agg_fn.get(),
            "operator": self.var_op.get(),
            "threshold": float(self.var_threshold.get()) if self.var_threshold.get() else 0,
            "conditions": self._parse_rows(self._filter_rows),
            "exclude_conditions": self._parse_rows(self._excl_rows),
        }
        if self.var_op.get() == "tra":
            cfg["threshold_max"] = (
                float(self.var_threshold_max.get()) if self.var_threshold_max.get() else cfg["threshold"]
            )
        return cfg

    def set_config(self, c):
        for r in list(self._sources):
            self._remove_source(r)
        for s in c.get("sources", []):
            self._add_source(s.get("table", ""), s.get("group_col", ""), s.get("value_col", ""))
        if not self._sources:
            self._add_source()
        self.var_agg_fn.set(c.get("agg_function", "SUM"))
        self.var_op.set(c.get("operator", ">="))
        self.var_threshold.set(str(c.get("threshold", 0)))
        if "threshold_max" in c:
            self.var_threshold_max.set(str(c.get("threshold_max", "")))
        self._on_op_change()
        for r in list(self._filter_rows): self._rm_row(r, self._filter_rows)
        for r in list(self._excl_rows):   self._rm_row(r, self._excl_rows)
        for cond in c.get("conditions", []):
            self._add_row(self._filter_rows, "FILTRO", cond["column"], cond["operator"], cond.get("value", ""))
        for cond in c.get("exclude_conditions", []):
            self._add_row(self._excl_rows, "ESCLUDI", cond["column"], cond["operator"], cond.get("value", ""))

    def clear(self):
        for r in list(self._sources): self._remove_source(r)
        self.var_threshold.set("0")
        self.var_threshold_max.set("")
        for r in list(self._filter_rows): self._rm_row(r, self._filter_rows)
        for r in list(self._excl_rows):   self._rm_row(r, self._excl_rows)


# ---------------------------------------------------------------------------
# VALUE COMPARISON BUILDER
# Confronto valori multi-condizione: riusa MultiConditionBuilder completamente.
# ---------------------------------------------------------------------------
class ValueComparisonBuilder(MultiConditionBuilder):
    """Builder per 'Confronto valori (multi-condizione)'.
    Identico a MultiConditionBuilder — include tabella, condizioni AND/OR ed esclusioni."""
    def __init__(self, parent, db, on_table_change=None):
        super().__init__(parent, db, on_table_change,
                         title="Condizioni di filtro (AND/OR)")


# ---------------------------------------------------------------------------
# DUPLICATE BUILDER
# Ricerca duplicati esatti o fonetici su una singola colonna.
# ---------------------------------------------------------------------------
class DuplicateBuilder(ttk.Frame):
    """Builder per 'Ricerca duplicati esatti'."""
    def __init__(self, parent, db, on_table_change=None):
        super().__init__(parent, padding=5)
        self.db = db
        self.on_table_change = on_table_change
        self.columnconfigure(1, weight=1)

        # --- Tabella ---
        ttk.Label(self, text="Tabella:").grid(row=0, column=0, sticky="w", pady=2)
        self.var_table = tk.StringVar()
        self.cmb_table = ttk.Combobox(self, textvariable=self.var_table,
                                      state="readonly", width=35)
        self.cmb_table.grid(row=0, column=1, sticky="ew", padx=5)
        if self.db and self.db.connected:
            self.cmb_table["values"] = self.db.tables
        self.cmb_table.bind("<<ComboboxSelected>>", self._on_table_sel)

        # --- Colonna da analizzare ---
        ttk.Label(self, text="Colonna da analizzare:").grid(row=1, column=0, sticky="w", pady=2)
        self.var_col = tk.StringVar()
        self.cmb_col = ttk.Combobox(self, textvariable=self.var_col,
                                    state="readonly", width=35)
        self.cmb_col.grid(row=1, column=1, sticky="ew", padx=5)

        # --- Colonna chiave (ID record) ---
        ttk.Label(self, text="Colonna chiave (ID):").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(self, text="(lascia vuoto = usa colonna analizzata)",
                  foreground="gray", font=("Segoe UI", 8, "italic")).grid(row=2, column=1, sticky="w", padx=5)
        self.var_key = tk.StringVar()
        self.cmb_key = ttk.Combobox(self, textvariable=self.var_key,
                                    state="readonly", width=35)
        self.cmb_key.grid(row=3, column=1, sticky="ew", padx=5)
        ttk.Label(self, text="").grid(row=3, column=0)

        # --- Colonne da mostrare nei risultati ---
        ttk.Label(self, text="Colonne risultato:").grid(row=4, column=0, sticky="w", pady=2)
        ttk.Label(self, text="(separate da virgola, vuoto = tutte)",
                  foreground="gray", font=("Segoe UI", 8, "italic")).grid(row=4, column=1, sticky="w", padx=5)
        self.var_disp = tk.StringVar()
        ttk.Entry(self, textvariable=self.var_disp, width=40).grid(
            row=5, column=1, sticky="ew", padx=5)
        ttk.Label(self, text="").grid(row=5, column=0)

        # --- Opzioni ---
        self.var_phonetic = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Confronto fonetico italiano (ignora differenze di pronuncia)",
                        variable=self.var_phonetic).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=4)

        # --- Eccezioni ---
        ttk.Separator(self, orient=tk.HORIZONTAL).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Label(self, text="Eccezioni (un valore per riga da NON segnalare):").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=2)
        self.txt_exc = tk.Text(self, height=4, width=40)
        self.txt_exc.grid(row=9, column=0, columnspan=2, sticky="ew", padx=5)

        # --- Filtri pre-ricerca ---
        ttk.Separator(self, orient=tk.HORIZONTAL).grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=5)
        self._filter_frame = ttk.LabelFrame(self, text="Filtri pre-ricerca (opzionale)", padding=4)
        self._filter_frame.grid(row=11, column=0, columnspan=2, sticky="ew", padx=2)
        self._filter_rows = []
        self._excl_rows = []
        btn_f = ttk.Frame(self._filter_frame)
        btn_f.pack(fill=tk.X)
        ttk.Button(btn_f, text="+ Filtro",
                   command=lambda: self._add_row(self._filter_rows, "FILTRO")).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_f, text="+ Esclusione",
                   command=lambda: self._add_row(self._excl_rows, "ESCLUDI")).pack(side=tk.LEFT, padx=3)
        self._rows_container = ttk.Frame(self._filter_frame)
        self._rows_container.pack(fill=tk.X)

    def _on_table_sel(self, _evt=None):
        t = self.var_table.get()
        cols = self.db.columns(t) if t and self.db else []
        self.cmb_col["values"] = cols
        self.cmb_key["values"] = [""] + cols
        for r in self._filter_rows + self._excl_rows:
            r["cmb"]["values"] = cols
        if self.on_table_change:
            self.on_table_change(t)

    def _add_row(self, store, label, col="", op="=", val=""):
        frm = ttk.Frame(self._rows_container)
        frm.pack(fill=tk.X, pady=1)
        ttk.Label(frm, text=label, width=7).pack(side=tk.LEFT)
        t = self.var_table.get()
        cols = self.db.columns(t) if t and self.db else []
        v_col = tk.StringVar(value=col)
        cmb = ttk.Combobox(frm, textvariable=v_col, values=cols,
                           state="readonly", width=18)
        cmb.pack(side=tk.LEFT, padx=2)
        v_op = tk.StringVar(value=op)
        ops = list(constants.OPERATORS.keys())
        ttk.Combobox(frm, textvariable=v_op, values=ops,
                     state="readonly", width=12).pack(side=tk.LEFT, padx=2)
        v_val = tk.StringVar(value=val)
        ttk.Entry(frm, textvariable=v_val, width=16).pack(side=tk.LEFT, padx=2)
        ttk.Button(frm, text="✕", width=2,
                   command=lambda f=frm, s=store, e=None: self._rm_row(f, s)).pack(side=tk.LEFT)
        store.append({"frame": frm, "col": v_col, "op": v_op, "val": v_val, "cmb": cmb})

    def _rm_row(self, frm, store):
        store[:] = [r for r in store if r["frame"] is not frm]
        frm.destroy()

    def validate(self):
        if not self.var_table.get(): return False, "Selezionare la Tabella."
        if not self.var_col.get():   return False, "Selezionare la Colonna da analizzare."
        return True, ""

    def get_config(self):
        disp_raw = self.var_disp.get()
        display_cols = [c.strip() for c in disp_raw.split(",") if c.strip()] if disp_raw.strip() else []
        exc = [ln.strip() for ln in self.txt_exc.get("1.0", tk.END).splitlines() if ln.strip()]
        conditions       = [{"column": r["col"].get(), "operator": r["op"].get(),
                             "value": r["val"].get(), "logic": "AND"}
                            for r in self._filter_rows if r["col"].get()]
        exclude_conds = []
        for idx, row in enumerate(r for r in self._excl_rows if r["col"].get()):
            exclude_conds.append({
                "column": row["col"].get(),
                "operator": row["op"].get(),
                "value": row["val"].get(),
                "logic": "AND" if idx == 0 else "OR",
            })
        cfg = {
            "table":          self.var_table.get(),
            "column":         self.var_col.get(),
            "key_column":     self.var_key.get() or self.var_col.get(),
            "display_columns": display_cols,
            "check_phonetic": self.var_phonetic.get(),
            "exceptions":     exc,
            "conditions":     conditions,
        }
        if exclude_conds:
            cfg["exclude_conditions"] = exclude_conds
        return cfg

    def set_config(self, c):
        self.var_table.set(c.get("table") or c.get("source_table", ""))
        self._on_table_sel()
        self.var_col.set(c.get("column", ""))
        self.var_key.set(c.get("key_column", ""))
        disp = c.get("display_columns", [])
        self.var_disp.set(", ".join(disp) if disp else "")
        self.var_phonetic.set(c.get("check_phonetic", False))
        exc = c.get("exceptions", [])
        self.txt_exc.delete("1.0", tk.END)
        if exc:
            self.txt_exc.insert("1.0", "\n".join(str(e) for e in exc))
        for r in list(self._filter_rows):  self._rm_row(r["frame"], self._filter_rows)
        for r in list(self._excl_rows):    self._rm_row(r["frame"], self._excl_rows)
        for cond in c.get("conditions", []):
            self._add_row(self._filter_rows, "FILTRO",
                          cond.get("column", ""), cond.get("operator", "="), cond.get("value", ""))
        for cond in c.get("exclude_conditions", []):
            self._add_row(self._excl_rows, "ESCLUDI",
                          cond.get("column", ""), cond.get("operator", "="), cond.get("value", ""))

    def get_exception_column(self):
        return self.var_key.get().strip() or self.var_col.get().strip()

    def get_exception_targets(self, result_columns=None):
        column = self.get_exception_column()
        return [column] if column else []

    def add_exceptions(self, values, column=None):
        column = column or self.get_exception_column()
        if not column:
            return 0
        existing = {
            (
                r["col"].get().strip().upper(),
                r["op"].get().strip().upper(),
                str(r["val"].get()).strip().upper(),
            )
            for r in self._excl_rows
        }
        count = 0
        for value in values:
            sval = str(value).strip()
            if not sval:
                continue
            key = (column.upper(), "=", sval.upper())
            if key in existing:
                continue
            self._add_row(self._excl_rows, "ESCLUDI", column, "=", sval)
            existing.add(key)
            count += 1
        return count

    def clear(self):
        self.var_table.set("")
        self.var_col.set("")
        self.var_key.set("")
        self.var_disp.set("")
        self.var_phonetic.set(False)
        self.txt_exc.delete("1.0", tk.END)
        for r in list(self._filter_rows):  self._rm_row(r["frame"], self._filter_rows)
        for r in list(self._excl_rows):    self._rm_row(r["frame"], self._excl_rows)
