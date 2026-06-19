---
name: builder-accordion-state-sync
description: Prevent data loss in BuilderView accordion UI — sync sections before reading builder config, invalidate on type change
triggers: [accordion, _sync_builder_from_sections, filtro, esclusioni, BuilderView, get_config, set_config, _on_ctype_change, load_condition]
---

# BuilderView Accordion State Sync

## The Insight
In `views/builder_view.py`, the accordion sections (Filtri, Esclusioni, Periodicità) are separate `MultiConditionBuilder` widgets whose state must be explicitly synced into the main builder via `_sync_builder_from_sections()` before reading `get_config()`. The sync only happens automatically on accordion COLLAPSE — NOT on action buttons or type changes.

## Why This Matters
If you forget to call `_sync_builder_from_sections()` before "Esegui" or "Salva", any changes made in open accordion sections are silently lost. The user thinks they added a filter, but the query runs without it. No error, no warning — just wrong results.

## Recognition Pattern
- You're modifying `BuilderView` methods (especially `_run_current`, `_save_to_lib`, menu commands)
- You add a new action that reads from `self.state.active_builder.get_config()`
- You notice sections keeping stale widgets after `_on_ctype_change()` or `load_condition()`

## The Approach
1. **Before reading config, always sync**: Any method that calls `active_builder.get_config()` MUST call `_sync_builder_from_sections()` first.
2. **After changing type, invalidate all sections**: Call `_invalidate_accordion_sections()` after `_on_ctype_change()` to force rebuild of filtro/esclusioni/periodicita sections with `built=False`.
3. **After `load_condition`, auto-expand sections with data**: Call `_auto_expand_sections(cond)` to show the user what's configured instead of keeping everything collapsed.

## Key methods to check
```python
# views/builder_view.py
def _run_current(self):
    self._sync_builder_from_sections()  # ← REQUIRED, added in v7.4
    self.result_ctrl.run_current(display_cols)

def _on_ctype_change(self):
    ...
    self._invalidate_accordion_sections()  # ← REQUIRED, added in v7.4

def load_condition(self, cond):
    ...
    self._auto_expand_sections(cond)  # ← REQUIRED, added in v7.4
```

## Anti-pattern
```python
# WRONG: reads builder without syncing accordion sections
config = self.state.active_builder.get_config()

# RIGHT: sync first, then read
self._sync_builder_from_sections()
config = self.state.active_builder.get_config()
```
