"""Configurações lembradas entre execuções.

Guarda apenas o tipo de certificado e a aparência.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

SETTINGS_PATH = Path.home() / "Library" / "Application Support" / "HollyAssinadorOffline" / "config.json"

FIELDS: dict[str, type] = {
    "cert_type": str,
    "appearance": str,
}


def load(path: Path | None = None) -> dict:
    path = path or SETTINGS_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    values = {
        key: data[key]
        for key, kind in FIELDS.items()
        if isinstance(data.get(key), kind)
    }
    if values.get("cert_type") not in (None, "A1", "A3"):
        del values["cert_type"]
    if values.get("appearance") not in (None, "invisible", "footer", "manual"):
        del values["appearance"]
    return values


def save(values: dict, path: Path | None = None) -> None:
    path = path or SETTINGS_PATH
    data = {key: values[key] for key in FIELDS if key in values}
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    tmp = Path(handle.name)
    try:
        with handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
