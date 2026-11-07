import base64
from types import SimpleNamespace
from datetime import datetime, timezone
from mcp_datovka.services import isds

def test_nested_files_and_outer_delivery_metadata(monkeypatch):
    timestamp=datetime(2026,1,1,tzinfo=timezone.utc)
    response={'dmStatus':{'dmStatusCode':'0000'},'dmReturnedMessage':{
        'dmDm':{'dmID':'123','dmFiles':{'dmFile':[{'dmFileDescr':'notice.pdf',
          'dmMimeType':'application/pdf','dmEncodedContent':b'%PDF-test'}]}},
        'dmDeliveryTime':timestamp,'dmAcceptanceTime':timestamp,
        'dmMessageStatus':7,'dmAttachmentSize':3}}
    client=SimpleNamespace(service=SimpleNamespace(MessageDownload=lambda **kw:response))
    monkeypatch.setattr(isds,'_get_operations_client',lambda _:client)
    result=isds.read_message(None,'123')
    assert result['delivery_time']==timestamp.isoformat()
    assert result['status']=='7'
    assert result['attachments'][0]['filename']=='notice.pdf'
    assert result['attachments'][0]['mime_type']=='application/pdf'
    assert base64.b64decode(result['attachments'][0]['content_base64'])==b'%PDF-test'
