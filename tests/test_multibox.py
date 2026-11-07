import base64
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
import pytest
from mcp_datovka import config, drafts
from mcp_datovka.services import isds


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATOVKA_PRIVATE_DIR", str(tmp_path))
    data = {"version": 1, "boxes": [
        {"alias": "osobni", "box_id": "abc1234", "username": "test-user",
         "environment": "test", "allow_receive": False, "allow_send": True},
        {"alias": "firma", "box_id": "xyz5678", "username": "other-user",
         "environment": "production", "allow_receive": True, "allow_send": False}]}
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    # Test suite must never contact ISDS, including on accidental fallback paths.
    import requests
    monkeypatch.setattr(requests.sessions.Session, "request", lambda *a, **kw: pytest.fail("Network forbidden"))


def draft():
    return drafts.prepare("osobni", "def5678", "Test", "Cely text zpravy")


def approve(d):
    drafts.approve(d["draft_id"], d["digest"])


def test_accounts_and_environment_are_explicit():
    assert len(config.get_boxes()) == 2
    with pytest.raises(ValueError):
        config.get_box("")
    assert "czebox.cz" in config.get_soap_urls(config.get_box("osobni"))["info"]
    assert "mojedatovaschranka.cz" in config.get_soap_urls(config.get_box("firma"))["info"]
    assert "test-user" not in repr(config.get_box("osobni"))


def test_no_plaintext_password_in_configuration(tmp_path):
    data = config.load_config()
    data["boxes"][0]["password"] = "not-a-real-password"
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="hesla"):
        config.get_boxes()


def test_receive_disabled():
    with pytest.raises(PermissionError):
        config.require_receive(config.get_box("osobni"))


def test_draft_without_approval_cannot_send():
    d = draft()
    with pytest.raises(PermissionError):
        drafts.send(d["draft_id"])


def test_preview_full_text_no_credentials():
    d = drafts.prepare("osobni", "def5678", "Test", "x" * 1000)
    assert len(d["message"]["body"]) == 1000
    assert "username" not in d["message"]


def test_modified_payload_rejected():
    d = draft()
    with drafts.database() as db:
        db.execute("UPDATE drafts SET payload='{}' WHERE id=?", (d["draft_id"],))
        db.commit()
    with pytest.raises(ValueError, match="zmenen"):
        approve(d)


def test_sender_change_rejected(monkeypatch):
    d = draft()
    approve(d)
    box = config.get_box("osobni")
    monkeypatch.setattr(drafts, "get_box", lambda _: replace(box, box_id="xxx1234"))
    with pytest.raises(PermissionError, match="odesilatele"):
        drafts.send(d["draft_id"])


def test_expired_approval_rejected():
    d = draft()
    approve(d)
    with drafts.database() as db:
        db.execute("UPDATE drafts SET expires=0 WHERE id=?", (d["draft_id"],))
        db.commit()
    with pytest.raises(PermissionError):
        drafts.send(d["draft_id"])


def test_one_send_even_concurrently(monkeypatch):
    d = draft()
    approve(d)
    calls = []
    def fake(*a, **k):
        calls.append(a)
        return {"message_id": "123", "status": "sent"}
    monkeypatch.setattr(isds, "send_message", fake)
    def attempt():
        try:
            return drafts.send(d["draft_id"])
        except PermissionError:
            return "blocked"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert len(calls) == 1
    assert "blocked" in results
    assert drafts.preview(d["draft_id"])["state"] == "sent"


def test_uncertain_never_retried(monkeypatch):
    d = draft()
    approve(d)
    def timeout(*a, **k):
        raise TimeoutError("private details must not escape")
    monkeypatch.setattr(isds, "send_message", timeout)
    with pytest.raises(RuntimeError, match="nejisty"):
        drafts.send(d["draft_id"])
    assert drafts.preview(d["draft_id"])["state"] == "uncertain"
    with pytest.raises(PermissionError):
        drafts.send(d["draft_id"])


def test_send_disabled(monkeypatch):
    d = drafts.prepare("firma", "def5678", "Test", "Text")
    approve(d)
    with pytest.raises(PermissionError, match="povolene"):
        drafts.send(d["draft_id"])


def test_body_and_file_both_sent(monkeypatch):
    captured = {}
    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(dmStatus=SimpleNamespace(dmStatusCode="0000", dmStatusMessage="OK"), dmID="123")
    client = SimpleNamespace(get_type=lambda _: lambda **kw: kw,
                             service=SimpleNamespace(CreateMessage=create))
    monkeypatch.setattr(isds, "verify_sender", lambda b: None)
    monkeypatch.setattr(isds, "_get_operations_client", lambda b: client)
    isds.send_message(config.get_box("osobni"), "def5678", "Test", "Text",
        [{"filename": "a.pdf", "mime_type": "application/pdf", "content_base64": base64.b64encode(b"PDF").decode()}])
    files = captured["dmFiles"]["dmFile"]
    assert len(files) == 2
    assert files[1]["dmEncodedContent"] == b"Text"
    assert [f["dmFileMetaType"] for f in files] == ["main", "enclosure"]


@pytest.mark.parametrize("operation", ["list_received", "list_sent"])
def test_isds_error_is_not_empty_inbox(monkeypatch, operation):
    service = SimpleNamespace(GetListOfReceivedMessages=lambda **kw: {"dmStatus": {"dmStatusCode": "9999"}},
                              GetListOfSentMessages=lambda **kw: {"dmStatus": {"dmStatusCode": "9999"}})
    monkeypatch.setattr(isds, "_get_info_client", lambda b: SimpleNamespace(service=service))
    with pytest.raises(RuntimeError, match="9999"):
        getattr(isds, operation)(config.get_box("osobni"))


def test_sender_credentials_verified(monkeypatch):
    service = SimpleNamespace(_binding_options={}, GetOwnerInfoFromLogin=lambda **kw: {
        "dbStatus": {"dbStatusCode": "0000"}, "dbOwnerInfo": {"dbID": "wrongid"}})
    monkeypatch.setattr(isds, "_create_client", lambda *a: SimpleNamespace(service=service))
    with pytest.raises(RuntimeError, match="neodpovida"):
        isds.verify_sender(config.get_box("osobni"))


def test_real_wsdl_serializes_offline(monkeypatch):
    import keyring
    from lxml import etree
    monkeypatch.setattr(keyring, "get_password", lambda *a: "test-only")
    client = isds._get_operations_client(config.get_box("osobni"))
    envelope = client.get_type("{http://isds.czechpoint.cz/v20}tMessageEnvelopeSub")(dbIDRecipient="def5678", dmAnnotation="Test")
    xml = client.create_message(client.service, "CreateMessage", dmEnvelope=envelope,
                               dmFiles={"dmFile": [{"dmEncodedContent": b"Text", "dmMimeType": "text/plain", "dmFileMetaType": "main", "dmFileDescr": "text.txt"}]})
    assert b"def5678" in etree.tostring(xml)


def test_no_approval_tool_exposed():
    import asyncio
    from mcp_datovka.server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "datovka_send_draft" in names
    assert not any("approve" in n or "confirm" in n for n in names)
    assert "datovka_send_message" not in names


def test_file_snapshot_survives_original_change(tmp_path):
    import asyncio
    from mcp_datovka.server import mcp
    path = tmp_path / "document.txt"
    path.write_text("Original", encoding="utf-8")
    async def scenario():
        return await mcp.call_tool("datovka_prepare_message", {
            "from_box_alias": "osobni", "to_box_id": "def5678", "subject": "Test",
            "files": json.dumps([{"file_path": str(path)}])})
    asyncio.run(scenario())
    path.write_text("Changed", encoding="utf-8")
    with drafts.database() as db:
        row = db.execute("SELECT payload FROM drafts").fetchone()
    assert base64.b64decode(json.loads(row["payload"])["files"][0]["content_base64"]) == b"Original"
