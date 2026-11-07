"""Explicit account selection; no MCP operation can approve a draft."""
import json
import base64
import mimetypes
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from ..config import get_boxes, get_box, require_receive
from .. import drafts
from ..services import isds

LOCAL = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
RECEIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)
SEND = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)


def register_tools(mcp: FastMCP):
    @mcp.tool(annotations=LOCAL)
    def datovka_list_boxes() -> list[dict]:
        """Mistni seznam uctu bez pripojeni k ISDS a bez prihlasovacich udaju."""
        return [{"alias": b.alias, "box_id": b.box_id, "environment": b.environment,
                 "allow_receive": b.allow_receive, "allow_send": b.allow_send} for b in get_boxes()]

    @mcp.tool(annotations=RECEIVE)
    def datovka_list_received(box_alias: str, from_date: str | None = None, max_results: int = 50) -> list[dict]:
        """Nacte prijate zpravy. Muze zpusobit doruceni; vyzaduje povoleny prijem."""
        box = get_box(box_alias)
        require_receive(box)
        if not 1 <= max_results <= 1000:
            raise ValueError("Limit musi byt 1 az 1000.")
        return isds.list_received(box, from_date, max_results)

    @mcp.tool(annotations=RECEIVE)
    def datovka_list_sent(box_alias: str, from_date: str | None = None, max_results: int = 50) -> list[dict]:
        """Nacte odeslane zpravy z vybraneho uctu. Vyzaduje povoleny sitovy prijem."""
        box = get_box(box_alias)
        require_receive(box)
        if not 1 <= max_results <= 1000:
            raise ValueError("Limit musi byt 1 az 1000.")
        return isds.list_sent(box, from_date, max_results)

    @mcp.tool(annotations=RECEIVE)
    def datovka_read_message(box_alias: str, message_id: str) -> dict:
        """Stahne prijatou zpravu s prilohami base64; muze zpusobit doruceni."""
        box = get_box(box_alias)
        require_receive(box)
        if not message_id.isdecimal():
            raise ValueError("Neplatne ID zpravy.")
        return isds.read_message(box, message_id)

    @mcp.tool(annotations=RECEIVE)
    def datovka_search_box(box_alias: str, query: str, box_type: str | None = None) -> list[dict]:
        """Vyhleda prijemce pres explicitne zvoleny ucet. Zadny ucet se nehada."""
        return isds.search_box(get_box(box_alias), query, box_type)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    def datovka_prepare_message(from_box_alias: str, to_box_id: str, subject: str,
                               body: str = "", files: str = "[]") -> dict:
        """Ulozi nemenny navrh lokalne; nic neodesila. files je JSON pole priloh.

        Zobrazte uplny nahled. Schvaleni pouze v mistnim okne prikazem
        datovka-config review ID. Nevydavejte pripravu za odeslani.
        """
        items = json.loads(files)
        if not isinstance(items, list):
            raise ValueError("files musi byt JSON seznam.")
        normalized = []
        total = 0
        for item in items:
            if "file_path" in item:
                if set(item) - {"file_path", "filename", "mime_type"}:
                    raise ValueError("file_path nelze kombinovat s content_base64.")
                path = Path(item["file_path"])
                if not path.is_absolute() or not path.is_file():
                    raise ValueError("Priloha musi byt existujici soubor s absolutni cestou.")
                with path.open("rb") as stream:
                    raw = stream.read(drafts.MAX_BYTES + 1)
                total += len(raw)
                if total > drafts.MAX_BYTES:
                    raise ValueError("Prilohy presahuji mistni limit 20 MiB.")
                normalized.append({"filename": item.get("filename", path.name),
                    "mime_type": item.get("mime_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    "content_base64": base64.b64encode(raw).decode("ascii")})
            else:
                normalized.append(item)
        return drafts.prepare(from_box_alias, to_box_id, subject, body, normalized)

    @mcp.tool(annotations=LOCAL)
    def datovka_get_draft(draft_id: str) -> dict:
        """Vrati uplny text, hashe priloh a stav navrhu bez site."""
        return drafts.preview(draft_id)

    @mcp.tool(annotations=SEND)
    def datovka_send_draft(draft_id: str) -> dict:
        """Odesle pouze lokalne schvaleny nemenny navrh, nejvyse jeden pokus.

        Po chybe nejprve overte odeslane zpravy. Nevytvarejte automaticky novy
        navrh pro opakovani. Schvaleni nema MCP nastroj.
        """
        return drafts.send(draft_id)
