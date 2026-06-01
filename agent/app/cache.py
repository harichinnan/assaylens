"""Response cache for LLM calls — saves tokens by skipping the API entirely
when an identical request (same model + system + messages + max_tokens) has
already been answered.

Keyed by a sha256 of the full request, so it is exact-match (no fuzzy hits).
This is ideal for AssayLens because:
  * intent routing for a repeated question is byte-identical, and
  * summarization over the same (question, tool results) is byte-identical.

In-memory by default, with optional write-through JSON persistence so the cache
survives container restarts (set AGENT_CACHE_PATH + mount a volume). Thread-safe
and bounded (LRU-ish eviction by insertion order) with an optional TTL.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict


class ResponseCache:
    def __init__(self, path: str = "", ttl_seconds: int = 0, max_entries: int = 2000):
        self.path = path or os.getenv("AGENT_CACHE_PATH", "")
        self.ttl = ttl_seconds or int(os.getenv("AGENT_CACHE_TTL_SECONDS", "0"))
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._store: "OrderedDict[str, dict]" = OrderedDict()
        self.hits = 0
        self.misses = 0
        self._load()

    # ---- key ----
    @staticmethod
    def key(model: str, system: str, messages: list, max_tokens: int) -> str:
        blob = json.dumps(
            {"model": model, "system": system, "messages": messages, "max_tokens": max_tokens},
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # ---- get / set ----
    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            if self.ttl and (time.time() - entry["ts"]) > self.ttl:
                # expired
                self._store.pop(key, None)
                self.misses += 1
                return None
            self._store.move_to_end(key)  # mark most-recently-used
            self.hits += 1
            return entry["value"]

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._store[key] = {"value": value, "ts": time.time()}
            self._store.move_to_end(key)
            while len(self._store) > self.max_entries:
                self._store.popitem(last=False)  # evict oldest
            self._save()

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "entries": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
            "persistent": bool(self.path),
        }

    # ---- persistence (best-effort) ----
    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._store = OrderedDict(data.get("store", {}))
        except Exception:
            self._store = OrderedDict()

    def _save(self) -> None:
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"store": self._store}, f)
            os.replace(tmp, self.path)
        except Exception:
            pass  # caching is best-effort; never break a request over it


cache = ResponseCache()
