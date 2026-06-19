---
name: tkinter-pack-parent-mismatch
description: Tkinter pack(in_=new_parent) fails silently when widget was created with a different parent — always create widgets in the parent they'll be displayed in
triggers: [tkinter, pack, in_, parent, TclError, frm_dyn, geometry manager, repack]
---

# Tkinter Pack Parent Mismatch

## The Insight
In Tkinter, `widget.pack(in_=new_parent)` raises `TclError: can't pack .X inside .Y` when the widget was created with a different parent than `new_parent`. The widget's parent is set at CONSTRUCTION time (`Widget(parent)`) and cannot be changed by the geometry manager. You cannot "reparent" a widget via `pack()`.

The `try/except` that catches this error often hides the problem — the widget simply never appears, with no visible error to the user.

## Why This Matters
After refactoring `BuilderView` into `views/builder_view.py`, the `self.frm_dyn` frame was created but never `.pack()`ed. All 14 builder widgets were created as children of `frm_dyn` and were invisible. The `_build_section_base()` method tried to repack them into the accordion body with `pack(in_=body)`, which failed silently. The entire Controls tab was broken — users saw "Seleziona un tipo analisi per iniziare" even after selecting a condition type.

This was only discovered through manual code tracing, not by running the app.

## Recognition Pattern
- You create a widget with parent A, then try to pack/grid/place it into parent B
- You see a `try/except` around a `pack()` call
- A widget that should be visible simply isn't
- You're refactoring UI layout and moving widgets between containers

## The Approach
1. **Create widgets in their final parent**: If a widget needs to appear in `body`, create it with `parent=body`, not `parent=frm_dyn`.
2. **Never rely on `pack(in_=...)` for reparenting**: It doesn't work for widgets with a different constructed parent.
3. **Remove defensive try/except around pack**: These hide bugs. If `pack()` fails, something is structurally wrong.
4. **If you need dynamic parenting**: Use `widget.destroy()` and recreate, or use a `ttk.Frame` container that you reparent (frames are lightweight).

## Verification
```python
# Test: can you repack into a different parent?
import tkinter as tk
root = tk.Tk()
a = tk.Frame(root)
b = tk.Frame(root)
w = tk.Label(a, text="test")
w.pack()
try:
    w.pack(in_=b)  # FAILS: TclError
except tk.TclError as e:
    print(e)  # "can't pack .!frame.!label inside .!frame2"
```
