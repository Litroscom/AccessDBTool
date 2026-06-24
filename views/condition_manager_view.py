import tkinter as tk
from tkinter import ttk, messagebox
import logging

import constants
from storage import apply_value_replacement

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
            show="headings", selectmode="extended"
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
        ttk.Button(action_frame, text="🏷 Assegna tag...", command=self._assign_tag,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="🔁 Sostituisci valori...", command=self._bulk_replace_values,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=2)

        footer = ttk.Frame(self, padding=6)
        footer.pack(fill=tk.X)
        self.lbl_count = ttk.Label(footer, text="", bootstyle="info")
        self.lbl_count.pack(side=tk.LEFT)
        self.lbl_tags = ttk.Label(footer, text="", font=("", 8, "italic"))
        self.lbl_tags.pack(side=tk.LEFT, padx=8)

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
        self.lbl_count.config(text=f"{len(self.store.items)} condizioni totali")
        tag_counts = {}
        for c in self.store.items:
            tag = c.get("tag", "") or "Nessuno"
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        breakdown = " | ".join(f"{t}: {n}" for t, n in sorted(tag_counts.items()))
        self.lbl_tags.config(text=breakdown)

    def _on_select(self, _evt=None):
        sel = self.list_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        items = self._current_filtered_items()
        if idx < len(items):
            cond = items[idx]
            self._show_detail(cond)

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
        indices = self._selected_store_indices()
        if not indices:
            return
        self.on_load(self.store.items[indices[0]])
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
        indices = self._selected_store_indices()
        if not indices:
            return
        if not messagebox.askyesno("Conferma", f"Eliminare {len(indices)} condizioni?"):
            return
        for i in sorted(indices, reverse=True):
            del self.store.items[i]
        self.store._save()
        self._populate()
        self.on_refresh()

    def _assign_tag(self):
        indices = self._selected_store_indices()
        if not indices:
            messagebox.showwarning("Attenzione", "Seleziona almeno una condizione.")
            return
        from tkinter import simpledialog
        new_tag = simpledialog.askstring("Assegna tag", "Nuovo tag per le condizioni selezionate:")
        if not new_tag:
            return
        new_tag = new_tag.strip()
        for i in indices:
            self.store.items[i]["tag"] = new_tag
        self.store._save()
        self._populate()
        self.on_refresh()

    def _plan_replacement(self, indices, column, old_value, new_value):
        """Calcola le modifiche (senza applicarle) sulle condizioni indicate.
        Ritorna lista di (store_idx, nuova_cond, changes) per le sole
        condizioni con almeno una sostituzione."""
        plan = []
        for i in indices:
            new_cond, changes = apply_value_replacement(
                self.store.items[i], column, old_value, new_value)
            if changes:
                plan.append((i, new_cond, changes))
        return plan

    def _apply_replacement(self, plan):
        """Applica un piano di sostituzione e salva. Ritorna il numero totale
        di valori sostituiti."""
        for i, new_cond, _changes in plan:
            self.store.items[i] = new_cond
        if plan:
            self.store._save()
        return sum(len(changes) for _i, _c, changes in plan)

    def _bulk_replace_values(self):
        indices = self._selected_store_indices()
        if not indices:
            messagebox.showwarning("Attenzione", "Seleziona almeno una condizione.")
            return
        dlg = BulkReplaceDialog(self, len(indices))
        if not dlg.result:
            return
        column = dlg.result["column"]
        old_value = dlg.result["old"]
        new_value = dlg.result["new"]
        plan = self._plan_replacement(indices, column, old_value, new_value)
        if not plan:
            scope = f"colonna '{column}', " if column else ""
            messagebox.showinfo(
                "Nessuna corrispondenza",
                f"Nessun valore '{old_value}' ({scope}su {len(indices)} condizioni) "
                "da sostituire.",
            )
            return
        total = sum(len(changes) for _i, _c, changes in plan)
        lines = []
        for _i, _c, changes in plan:
            for ch in changes:
                where = ch["where"]
                col = ch["column"] or "(qualsiasi)"
                lines.append(f"• {ch['name']}: [{col}] '{ch['old']}' → '{ch['new']}' ({where})")
        preview = "\n".join(lines[:25])
        if len(lines) > 25:
            preview += f"\n… e altre {len(lines) - 25}"
        if not messagebox.askyesno(
            "Conferma sostituzione",
            f"{total} sostituzioni in {len(plan)} condizioni:\n\n{preview}\n\nProcedere?",
        ):
            return
        applied = self._apply_replacement(plan)
        self._populate()
        self.on_refresh()
        messagebox.showinfo("OK", f"{applied} valori sostituiti in {len(plan)} condizioni.")

    def _selected_store_indices(self):
        selected = []
        for iid in self.list_tree.selection():
            items = self._current_filtered_items()
            try:
                idx = items[int(iid)]
                global_idx = self.store.items.index(idx)
                selected.append(global_idx)
            except Exception:
                continue
        return selected

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


class BulkReplaceDialog(tk.Toplevel):
    """Input per la sostituzione massiva: colonna (opzionale), valore attuale,
    nuovo valore. Imposta self.result = {column, old, new} su conferma."""

    def __init__(self, parent, n_selected):
        super().__init__(parent)
        self.result = None
        self.title("Sostituisci valori")
        self.resizable(False, False)
        self.transient(parent)

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frm,
            text=f"Sostituzione su {n_selected} condizioni selezionate.",
            font=("", 9, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.var_col = tk.StringVar()
        self.var_old = tk.StringVar()
        self.var_new = tk.StringVar()
        for r, (label, var) in enumerate([
            ("Colonna (vuoto = qualsiasi):", self.var_col),
            ("Valore attuale:", self.var_old),
            ("Nuovo valore:", self.var_new),
        ], start=1):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=3, padx=2)
            ttk.Entry(frm, textvariable=var, width=24).grid(row=r, column=1, pady=3, padx=2)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(btns, text="Annulla", command=self.destroy,
                   bootstyle="secondary").pack(side=tk.RIGHT, padx=2)
        ttk.Button(btns, text="Anteprima…", command=self._confirm,
                   bootstyle="primary").pack(side=tk.RIGHT, padx=2)

        self.bind("<Return>", lambda _e: self._confirm())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.wait_window(self)

    def _confirm(self):
        old = self.var_old.get().strip()
        if not old:
            messagebox.showwarning("Attenzione", "Inserire il valore attuale da sostituire.", parent=self)
            return
        self.result = {
            "column": self.var_col.get().strip(),
            "old": old,
            "new": self.var_new.get().strip(),
        }
        self.destroy()
