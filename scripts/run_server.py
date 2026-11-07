"""Run the installed isolated environment, independent of the working directory."""
import os
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if not python.exists():
    private = Path(os.environ.get("DATOVKA_PRIVATE_DIR") or
                   str(Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "DatovkaMultibox"))
    registry = private / "runtime.json"
    if not registry.exists():
        raise SystemExit("Nejprve spustte instalaci podle README.md (chybi .venv i mistni runtime).")
    python = Path(json.loads(registry.read_text(encoding="utf-8"))["python"])
    if not python.is_absolute() or not python.is_file():
        raise SystemExit("Mistni runtime neni dostupny. Zopakujte instalaci.")
os.execv(str(python), [str(python), "-m", "mcp_datovka"])
