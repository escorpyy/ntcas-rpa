"""
core/checkpoint.py  — v9.5
===========================
Resume-from-failure checkpoint system.
Saves run state after every name. Used directly by FlowExecutor.start().
File: ~/.swastik/checkpoints/<flow_hash>.json
"""
from __future__ import annotations
import hashlib, json, os, datetime
from typing import Optional

_CHECKPOINT_DIR = os.path.join(os.path.expanduser("~"), ".swastik", "checkpoints")
os.makedirs(_CHECKPOINT_DIR, exist_ok=True)


def flow_hash(flow: list) -> str:
    try:
        raw = json.dumps(flow, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw.encode()).hexdigest()[:8]
    except Exception:
        return "unknown"


class CheckpointManager:
    def __init__(self, names: list, flow: list,
                 settings: dict = None, flow_path: str = ""):
        self.names     = list(names)
        self.fhash     = flow_hash(flow)
        self.settings  = settings or {}
        self.flow_path = flow_path
        self._completed: list[str] = []
        self._failed:    list[str] = []
        self._remaining: list[str] = list(names)
        self._path = os.path.join(_CHECKPOINT_DIR, f"{self.fhash}.json")

    def mark_done(self, name: str, ok: bool) -> None:
        if name in self._remaining:
            self._remaining.remove(name)
        self._completed.append(name)
        if not ok:
            self._failed.append(name)
        self._save()

    def get_remaining(self) -> list[str]:
        return list(self._remaining)

    def summary(self) -> dict:
        saved_at = ""
        try:
            with open(self._path, encoding="utf-8") as f:
                saved_at = json.load(f).get("saved_at", "")
        except Exception:
            pass
        return {
            "total":     len(self.names),
            "completed": len(self._completed),
            "failed":    len(self._failed),
            "remaining": len(self._remaining),
            "flow_path": self.flow_path,
            "saved_at":  saved_at,
        }

    def clear(self) -> None:
        try:
            if os.path.isfile(self._path):
                os.remove(self._path)
        except Exception:
            pass

    def _save(self) -> None:
        data = {
            "fhash":     self.fhash,
            "saved_at":  datetime.datetime.now().isoformat(),
            "total":     len(self.names),
            "all_names": self.names,
            "completed": self._completed,
            "failed":    self._failed,
            "remaining": self._remaining,
            "settings":  self.settings,
            "flow_path": self.flow_path,
        }
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        except Exception as e:
            print(f"[checkpoint] save failed: {e}")
            try:
                os.remove(tmp)
            except Exception:
                pass

    @classmethod
    def load_for_flow(cls, flow: list) -> Optional["CheckpointManager"]:
        fh   = flow_hash(flow)
        path = os.path.join(_CHECKPOINT_DIR, f"{fh}.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            inst            = cls.__new__(cls)
            inst.fhash      = fh
            inst.names      = data.get("all_names", [])
            inst.settings   = data.get("settings", {})
            inst.flow_path  = data.get("flow_path", "")
            inst._completed = data.get("completed", [])
            inst._failed    = data.get("failed", [])
            inst._remaining = data.get("remaining", [])
            inst._path      = path
            return inst
        except Exception as e:
            print(f"[checkpoint] load failed: {e}")
            return None

    @classmethod
    def list_all(cls) -> list[dict]:
        results = []
        try:
            for fname in os.listdir(_CHECKPOINT_DIR):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(_CHECKPOINT_DIR, fname)
                try:
                    with open(path, encoding="utf-8") as f:
                        d = json.load(f)
                    results.append({
                        "fhash":     d.get("fhash", fname[:-5]),
                        "saved_at":  d.get("saved_at", ""),
                        "total":     d.get("total", 0),
                        "completed": len(d.get("completed", [])),
                        "remaining": len(d.get("remaining", [])),
                        "failed":    len(d.get("failed", [])),
                        "flow_path": d.get("flow_path", ""),
                    })
                except Exception:
                    pass
        except Exception:
            pass
        return sorted(results, key=lambda x: x["saved_at"], reverse=True)

    @classmethod
    def delete_by_hash(cls, fhash: str) -> None:
        try:
            os.remove(os.path.join(_CHECKPOINT_DIR, f"{fhash}.json"))
        except Exception:
            pass
