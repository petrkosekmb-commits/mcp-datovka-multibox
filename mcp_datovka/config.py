"""Private configuration outside the source tree; passwords in the OS vault."""
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

PRODUCTION_BASE_URL = "https://ws1.mojedatovaschranka.cz"
TEST_BASE_URL = "https://ws1.czebox.cz"
SERVICE = "mcp-datovka-multibox"


def private_dir() -> Path:
    override = os.environ.get("DATOVKA_PRIVATE_DIR")
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise ValueError("DATOVKA_PRIVATE_DIR musi byt absolutni cesta.")
        if path.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
            raise ValueError("Soukroma konfigurace musi byt mimo repozitar.")
        return path
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "DatovkaMultibox"


def load_config() -> dict:
    path = private_dir() / "config.json"
    if not path.exists():
        return {"version": 1, "boxes": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("boxes"), list):
        raise ValueError("Nepodporovana soukroma konfigurace.")
    return data


@dataclass(frozen=True)
class BoxConfig:
    alias: str
    box_id: str
    username: str = field(repr=False)
    environment: str = "test"
    allow_receive: bool = False
    allow_send: bool = False

    @property
    def password(self) -> str:
        import keyring
        value = keyring.get_password(SERVICE, f"{self.environment}:{self.alias}:{self.username}")
        if not value:
            raise ValueError("Heslo chybi v systemovem ulozisti. Spustte nastaveni uctu.")
        return value


def get_boxes() -> list[BoxConfig]:
    return validate_boxes(load_config())


def validate_boxes(data: dict) -> list[BoxConfig]:
    boxes, aliases, identities = [], set(), set()
    for item in data["boxes"]:
        if set(item) - {"alias", "box_id", "username", "environment", "allow_receive", "allow_send"}:
            raise ValueError("Nezname pole konfigurace; hesla do JSON nepatri.")
        box = BoxConfig(**item)
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", box.alias):
            raise ValueError("Neplatny nazev uctu.")
        if not re.fullmatch(r"[a-z0-9]{7}", box.box_id):
            raise ValueError("ID schranky musi mit sedm malych pismen nebo cislic.")
        if box.environment not in {"test", "production"} or not box.username.strip():
            raise ValueError("Neplatne prostredi nebo prihlasovaci jmeno.")
        if type(box.allow_receive) is not bool or type(box.allow_send) is not bool:
            raise ValueError("Opravneni musi byt true nebo false.")
        if box.alias in aliases or (box.environment, box.box_id) in identities:
            raise ValueError("Duplicitni ucet nebo schranka.")
        aliases.add(box.alias)
        identities.add((box.environment, box.box_id))
        boxes.append(box)
    return boxes


def get_box(alias: str) -> BoxConfig:
    for box in get_boxes():
        if box.alias == alias:
            return box
    raise ValueError("Neznamy ucet. Nejprve zobrazte seznam schranek.")


def get_soap_urls(box: BoxConfig) -> dict[str, str]:
    base = TEST_BASE_URL if box.environment == "test" else PRODUCTION_BASE_URL
    return {"operations": f"{base}/DS/dz", "info": f"{base}/DS/dx",
            "search": f"{base}/DS/df", "access": f"{base}/DS/DsManage"}


def require_receive(box: BoxConfig) -> None:
    if not box.allow_receive:
        raise PermissionError("Prijem neni povolen. Synchronizace muze zpusobit doruceni zprav; povolte ji v mistnim nastaveni.")
