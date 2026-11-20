"""Localiza contêineres PKCS#12 pelos nomes, sem abrir os arquivos."""
import os
from pathlib import Path
import subprocess


def discover_a1_files(home=None):
    home = Path.home() if home is None else Path(home)
    found = set()

    def add(path):
        if path.suffix.lower() in {".pfx", ".p12"} and path.is_file():
            found.add(path)

    # O Spotlight também pode encontrar arquivos fora das pastas usuais.
    try:
        result = subprocess.run(
            ["/usr/bin/mdfind", "-0", "-onlyin", str(home),
             'kMDItemFSName == "*.pfx"cd || kMDItemFSName == "*.p12"cd'],
            capture_output=True, timeout=6, check=True,
        )
        for entry in result.stdout.split(b"\0"):
            if entry:
                path = Path(os.fsdecode(entry))
                if path.is_relative_to(home) and not any(p.startswith(".") for p in path.relative_to(home).parts):
                    add(path)
    except (OSError, subprocess.SubprocessError):
        pass
    # Inclui locais sem índice e evita seguir atalhos para outros volumes.
    for path in home.glob("*"):
        if not path.name.startswith("."):
            add(path)
    for folder in ("Downloads", "Documents", "Desktop", "Certificados"):
        for root, dirs, files in os.walk(home / folder, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith(".") and not d.endswith((".app", ".bundle"))
                       and d not in {"node_modules", "__pycache__"}]
            for name in files:
                if not name.startswith(".") and name.lower().endswith((".pfx", ".p12")):
                    add(Path(root, name))
    return sorted(found, key=lambda p: str(p).casefold())
