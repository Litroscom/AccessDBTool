import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import logging

logger = logging.getLogger("AccessDBTool.ResultsView")


class ResultsView(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._current_title = ""
        self._build_ui()

    def _build_ui(self):
        self._build_action_bar()

        filter_frame = ttk.Frame(self, padding=6)
        filter_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.res_lbl = ttk.Label(filter_frame, text="Nessun risultato", font=("", 10, "bold"))
        self.res_lbl.pack(side=tk.LEFT)

        ttk.Label(filter_frame, text="Filtra:").pack(side=tk.RIGHT, padx=(0, 4))
        self.var_filter = tk.StringVar()
        self.entry_filter = ttk.Entry(filter_frame, textvariable=self.var_filter, width=25)
        self.entry_filter.pack(side=tk.RIGHT, padx=4)
        self.entry_filter.bind("<KeyRelease>", self._apply_filter)

        tree_frame = ttk.Frame(self, padding=4)
        tree_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        self.res_tree = ttk.Treeview(tree_frame, show="headings", selectmode="extended")
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.res_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.res_tree.xview)
        self.res_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.res_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.res_tree.tag_configure("error", foreground="#ffb3b3")
        self.res_tree.tag_configure("ok", foreground="#b3ffcc")

        self.res_tree.bind("<Button-3>", self._on_context_menu)

    def _build_action_bar(self):
        action_frame = ttk.Frame(self, padding=4)
        action_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(action_frame, text="Esporta CSV",
                   command=self._export_csv,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        ttk.Button(action_frame, text="Modifica record",
                   command=self._edit_record,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        ttk.Button(action_frame, text="Sost. massiva",
                   command=self._bulk_replace,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        ttk.Button(action_frame, text="Aggiungi a esclusioni",
                   command=self._add_to_exclusions,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

        ttk.Button(action_frame, text="Apri nel builder",
                   command=self._open_in_builder,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=2)

    def _on_context_menu(self, event):
        self.app._show_res_menu(event)

    def _apply_filter(self, _evt=None):
        query = self.var_filter.get().lower()
        if not self.app.current_result:
            return
        rows = self.app.current_result.get("rows", [])
        self.res_tree.delete(*self.res_tree.get_children())
        count = 0
        for i, r in enumerate(rows):
            if not query:
                self.res_tree.insert("", tk.END, iid=str(i), values=r)
                count += 1
            else:
                for val in r:
                    if query in str(val).lower():
                        self.res_tree.insert("", tk.END, iid=str(i), values=r)
                        count += 1
                        break

        self.res_lbl.config(
            text=f"{self.app.current_result.get('title', '?')} ({count} filtrati su {len(rows)})"
        )

    def show_results(self, res):
        if not res:
            return
        count = res.get("count", 0)
        self.res_lbl.config(text=f"{res.get('title', '?')} ({count} record)")
        self.res_tree.delete(*self.res_tree.get_children())
        self.res_tree["columns"] = res.get("columns", [])
        for c in res.get("columns", []):
            self.res_tree.heading(c, text=c)
            self.res_tree.column(c, width=150)

        row_tag = "error" if isinstance(count, (int, float)) and count > 0 else "ok"
        for i, r in enumerate(res.get("rows", [])):
            self.res_tree.insert("", tk.END, iid=str(i), values=r, tags=(row_tag,))

        self._current_title = res.get("title", "")

    def _export_csv(self):
        if not self.app.current_result:
            return
        p = filedialog.asksaveasfilename(defaultextension=".csv")
        if not p:
            return
        import csv
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(self.app.current_result["columns"])
            w.writerows(self.app.current_result["rows"])
        messagebox.showinfo("OK", "Esportato")

    def _edit_record(self):
        self.app._edit_res_record()

    def _bulk_replace(self):
        self.app._bulk_replace_results()

    def _add_to_exclusions(self):
        self.app._ensure_active_builder_from_result()
        self.app._add_selected_to_exceptions(target_column="")

    def _open_in_builder(self):
        if self.app.current_result:
            cond = self.app.current_result.get("_condition")
            if cond:
                self.app._load_cond_into_builder(cond)
