"""
core/column_mapper.py  — v9.5
==============================
Column-mapped variable system.

Maps Excel/CSV columns to {variable} names so each row supplies multiple
variables, not just {name}.

Example:
    name   | amount | date       | ref
    Alice  | 5000   | 2026-05-01 | INV001

build() returns:
    names    = ["Alice", ...]
    row_vars = {"Alice": {"amount":"5000", "date":"2026-05-01", "ref":"INV001"}, ...}

FlowExecutor merges row_vars[name] into vmap before each step.
"""
from __future__ import annotations
import os
from typing import Optional

try:
    import pandas as pd
    _PD_OK = True
except ImportError:
    _PD_OK = False


class ColumnMapper:

    def __init__(self):
        self._df:       Optional[object] = None
        self._name_col: str = ""
        self._mapping:  dict[str, str] = {}

    def set_dataframe(self, df, name_col: str) -> None:
        self._df       = df
        self._name_col = name_col
        self._mapping  = {}
        for col in df.columns:
            if col != name_col:
                safe = col.strip().lower().replace(" ", "_")
                self._mapping[col] = safe

    def set_mapping(self, mapping: dict[str, str]) -> None:
        self._mapping = dict(mapping)

    def get_extra_columns(self) -> list[str]:
        if self._df is None:
            return []
        return [c for c in self._df.columns if c != self._name_col]

    def build(self) -> tuple[list[str], dict[str, dict]]:
        if self._df is None or not self._name_col:
            return [], {}
        names:    list[str]       = []
        row_vars: dict[str, dict] = {}
        for _, row in self._df.iterrows():
            name = str(row.get(self._name_col, "")).strip()
            if not name:
                continue
            names.append(name)
            vd = {}
            for col, varname in self._mapping.items():
                if col in row:
                    val = row[col]
                    vd[varname] = "" if (val is None or str(val) == "nan") else str(val).strip()
            row_vars[name] = vd
        return names, row_vars

    @classmethod
    def from_file(cls, path: str, name_col: str = "") -> "ColumnMapper":
        if not _PD_OK:
            raise ImportError("pandas is required for ColumnMapper")
        ext = os.path.splitext(path)[1].lower()
        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(path, dtype=str)
        elif ext == ".csv":
            df = pd.read_csv(path, dtype=str)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
        df.dropna(how="all", inplace=True)
        if not name_col and len(df.columns) > 0:
            name_col = df.columns[0]
        inst = cls()
        inst.set_dataframe(df, name_col)
        return inst
