import tkinter as tk
from tkinter import ttk, messagebox
import logging

import constants

logger = logging.getLogger("AccessDBTool.ConditionManagerView")


class ConditionManagerDialog(tk.Toplevel):
    def __init__(self, parent, store, on_refresh, on_load):
        super().__init__(parent)
        self.parent = parent
        self.store = store
        self.on_refresh = on_refresh
        self.on_load = on_load
        self.title("Gestione Condizioni — AccessDBTool v7")
        self.geometry("800x500")
        self.minsize(600, 350)

        self._build_ui()
        self._populate()

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="🔍").pack(side=tk.LEFT, padx=(0, 4))
        self.var_search = tk.StringVar()
        self.entry_search = ttk.Entry(toolbar, textvariable=self.var_search, width=30)
        self.entry_search.pack(side=tk.LEFT, padx=4)
        self.entry_search.bind("<KeyRelease>", lambda _: self._populate())

        ttk.Label(toolbar, text="Ordina:").pack(side=tk.LEFT, padx=(20, 4))
        self.var_sort = tk.StringVar(value="Nome")
        self.cmb_sort = ttk.Combobox(
            toolbar, textvariable=self.var_sort,
            values=["Nome", "Categoria", "Database", "Data"],
            state="readonly", width=12
        )
        self.cmb_sort.pack(side=tk.LEFT, padx=4)
        self.cmb_sort.bind("<<ComboboxSelected>>", lambda _: self._populate())

        ttk.Label(toolbar, text="Filtro:").pack(side=tk.LEFT, padx=(20, 4))
        self.var_filter = tk.StringVar(value="Tutti")
        self.cmb_filter = ttk.Combobox(
            toolbar, textvariable=self.var_filter,
            values=["Tutti"], state="readonly", width=14
        )
        self.cmb_filter.pack(side=tk.LEFT, padx=4)
        self.cmb_filter.bind("<<ComboboxSelected>>", lambda _: self._populate())

        ttk.Button(toolbar, text="📋 Esporta",
                   command=self._export_selected,
                   bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="📂 Importa",
                   command=self._import_conditions,
                   bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=2)

        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        list_frame = ttk.Frame(paned, padding=4)
        paned.add(list_frame, weight=1)

        self.list_tree = ttk.Treeview(
            list_frame, columns=("name", "tag", "db"),
            show="headings", selectmode="browse"
        )
        self.list_tree.heading("name", text="Nome")
        self.list_tree.heading("tag", text="Tag")
        self.list_tree.heading("db", text="Database")
        self.list_tree.column("name", width=180)
        self.list_tree.column("tag", width=100)
        self.list_tree.column("db", width=130)

        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.list_tree.yview)
        self.list_tree.configure(yscrollcommand=scroll.set)
        self.list_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_tree.bind("<<TreeviewSelect>>", self._on_select)

        detail_frame = ttk.Frame(paned, padding=8)
        paned.add(detail_frame, weight=1)

        self.detail_name = ttk.Label(detail_frame, text="", font=("", 12, "bold"))
        self.detail_name.pack(anchor=tk.W)

        self.detail_info = ttk.Frame(detail_frame)
        self.detail_info.pack(fill=tk.X, pady=6)

        self._detail_labels = {}
        for field, label in [
            ("type", "Tipo analisi:"),
            ("tag", "Tag/Macrosettore:"),
            ("db", "Database:"),
            ("table", "Tabella:"),
            ("period", "Periodicità:"),
            ("saved_at", "Salvato il:"),
        ]:
            row = ttk.Frame(self.detail_info)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=label, width=14, font=("", 9, "bold")).pack(side=tk.LEFT)
            lbl = ttk.Label(row, text="")
            lbl.pack(side=tk.LEFT, padx=4)
            self._detail_labels[field] = lbl

        action_frame = ttk.Frame(detail_frame)
        action_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(action_frame, text="✏ Modifica", command=self._edit,
                   bootstyle="primary").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="📋 Duplica", command=self._duplicate,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="🗑 Elimina", command=self._delete,
                   bootstyle="danger").pack(side=tk.LEFT, padx=2)

        footer = ttk.Frame(self, padding=6)
        footer.pack(fill=tk.X)
        self.lbl_count = ttk.Label(footer, text="", bootstyle="info")
        self.lbl_count.pack(side=tk.LEFT)

    def _populate(self):
        self.list_tree.delete(*self.list_tree.get_children())
        query = self.var_search.get().strip().lower()
        sort_by = self.var_sort.get()
        filter_tag = self.var_filter.get().strip()

        items = list(self.store.items)
        if filter_tag and filter_tag != "Tutti":
            items = [c for c in items if c.get("tag", "").strip() == filter_tag]
        if query:
            items = [
                c for c in items
                if query in c.get("name", "").lower()
                or query in c.get("tag", "").lower()
            ]

        if sort_by == "Nome":
            items.sort(key=lambda c: c.get("name", "").lower())
        elif sort_by == "Categoria":
            items.sort(key=lambda c: (c.get("tag", "").lower(), c.get("name", "").lower()))
        elif sort_by == "Database":
            items.sort(key=lambda c: (c.get("database_label", "").lower(), c.get("name", "").lower()))
        elif sort_by == "Data":
            items.sort(key=lambda c: c.get("saved_at", ""), reverse=True)

        for idx, cond in enumerate(items):
            self.list_tree.insert(
                "", tk.END, iid=str(idx),
                values=(
                    cond.get("name", ""),
                    cond.get("tag", ""),
                    cond.get("database_label", ""),
                )
            )

        all_tags = self.store.tags()
        self.cmb_filter["values"] = ["Tutti"] + all_tags
        self.lbl_count.config(text=f"{len(items)} condizioni su {len(self.store.items)}")

    def _on_select(self, _evt=None):
        sel = self.list_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        cond = self._current_items()[idx]
        self._show_detail(cond)

    def _current_items(self):
        return self.store.items

    def _show_detail(self, cond):
        self.detail_name.config(text=cond.get("name", ""))
        type_key = cond.get("type", "")
        type_label = constants.CONDITION_TYPES.get(type_key, type_key)
        self._detail_labels["type"].config(text=type_label)
        self._detail_labels["tag"].config(text=cond.get("tag", "") or "-")
        self._detail_labels["db"].config(text=cond.get("database_label", "") or "-")
        self._detail_labels["table"].config(text=cond.get("table", "") or "-")
        cycle = cond.get("periodic_review_cycle", "")
        if cond.get("periodic_review_enabled") and cycle:
            self._detail_labels["period"].config(text=f"{cycle.capitalize()} (da aggiornare)")
        else:
            self._detail_labels["period"].config(text="-")
        self._detail_labels["saved_at"].config(text=cond.get("saved_at", "") or "-")

    def _current_filtered_items(self):
        query = self.var_search.get().strip().lower()
        filter_tag = self.var_filter.get().strip()
        items = list(self.store.items)
        if filter_tag and filter_tag != "Tutti":
            items = [c for c in items if c.get("tag", "").strip() == filter_tag]
        if query:
            items = [c for c in items if query in c.get("name", "").lower()]
        return items

    def _edit(self):
        sel = self.list_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        items = self._current_filtered_items()
        if idx >= len(items):
            return
        self.on_load(items[idx])
        self.destroy()

    def _duplicate(self):
        sel = self.list_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        items = self._current_filtered_items()
        if idx >= len(items):
            return
        cond = dict(items[idx])
        cond["name"] = cond.get("name", "") + " (copia)"
        self.store.add(cond)
        self._populate()
        self.on_refresh()

    def _delete(self):
        sel = self.list_tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("Conferma", "Eliminare la condizione selezionata?"):
            return
        idx = int(sel[0])
        items = self._current_filtered_items()
        global_idx = self.store.items.index(items[idx])
        self.store.delete(global_idx)
        self._populate()
        self.on_refresh()

    def _export_selected(self):
        if not self.store.items:
            messagebox.showwarning("Attenzione", "Nessuna condizione da esportare.")
            return
        if hasattr(self.parent, "_export_conditions"):
            self.parent._export_conditions(self.store.items)

    def _import_conditions(self):
        if hasattr(self.parent, "_import_conditions"):
            self.parent._import_conditions()
            self._populate()
