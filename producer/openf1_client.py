from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List
import requests

BASE_URL = "https://api.openf1.org/v1"

@dataclass(frozen=True)
class OpenF1Query:
    endpoint: str
    params: Dict[str, Any]
    fmt: str = "json"

    def cache_key(self) -> str:
        payload = json.dumps({"endpoint": self.endpoint, "params": self.params, "fmt": self.fmt}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def fetch_cached(query: OpenF1Query, cache_dir: str, timeout_s: int = 30) -> List[Dict[str, Any]]:
    _ensure_dir(cache_dir)
    key = query.cache_key()
    cache_path = os.path.join(cache_dir, f"{key}.{query.fmt}")

    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return _read_file(cache_path, query.fmt)

    url = f"{BASE_URL}/{query.endpoint}"
    headers = {"Accept": "application/json"}

    r = requests.get(url, params=query.params, headers=headers, timeout=timeout_s)
    r.raise_for_status()

    with open(cache_path, "wb") as f:
        f.write(r.content)

    return _read_file(cache_path, query.fmt)

def _read_file(path: str, fmt: str) -> List[Dict[str, Any]]:
    if fmt == "json":
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise ValueError(f"Unsupported format: {fmt}")