---
name: access-odbc-identifier-quoting
description: Always use DatabaseManager._qi() to quote SQL identifiers — direct [...] breaks with bracket characters in names, and the function must not be duplicated across modules
triggers: [_qi, DatabaseManager, Access, ODBC, quoting, bracket, identifier, SQL injection]
---

# Access ODBC Identifier Quoting

## The Insight
Access ODBC uses square brackets for identifier quoting: `[TableName]`. If a table or column name contains `]`, it must be escaped as `]]`. The `DatabaseManager._qi()` method handles this. Using direct `[...]` (as `data_profiler.py` did) works until someone names a table `Sales[Europe]` — then the query breaks.

Additionally, the same `_qi()` function was duplicated in both `db_manager.py` and `engines.py`. If one is updated for a new edge case and the other isn't, queries from engines silently break.

## Why This Matters
- Access allows `]` in table/column names (e.g., imported Excel sheets)
- Using `f"[{name}]"` instead of `_qi(name)` causes SQL syntax errors that are hard to debug because Access error messages are cryptic
- Duplicated code means duplicated bugs

## Recognition Pattern
- You're writing a SQL query string for Access/pyodbc
- You're about to write `[{column}]` or `[{table}]`
- You're adding a new module that queries the database
- You see `_qi` defined in more than one place

## The Approach
1. **Always use `_qi()` for identifiers**: Import from `db_manager` and use `DatabaseManager._qi(name)`.
2. **One source of truth**: `_qi` lives in `db_manager.py` only. Other modules alias it: `_qi = DatabaseManager._qi`.
3. **Grep before writing**: Search for `\[.*\]` in new SQL query strings — if you see it outside `_qi()`, it's a bug.
4. **Test with bracket names**: Include a test case with `]` in table/column names.

## Example
```python
# WRONG — breaks if name contains ]
sql = f"SELECT [{column}] FROM [{table}]"

# RIGHT — properly escaped
from db_manager import DatabaseManager
_qi = DatabaseManager._qi
sql = f"SELECT {_qi(column)} FROM {_qi(table)}"

# _qi implementation:
# "test]name" → "[test]]name]"
```

## Where this bit us
- `data_profiler.py:_get_sample()` — had direct `[...]`, fixed in v7.4
- `engines.py` — had duplicate `_qi`, deduplicated in v7.4
