import json
import pytest
from mcp_datovka import config, credentials_gui


@pytest.fixture
def account(tmp_path, monkeypatch):
    monkeypatch.setenv('DATOVKA_PRIVATE_DIR', str(tmp_path))
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'version': 1, 'boxes': [dict(alias='demo', box_id='abc1234',
        username='oldusr', environment='test', allow_receive=False, allow_send=False)]}), encoding='utf-8')
    return path


def test_failed_login_preserves_credentials(account, monkeypatch):
    import keyring
    before = account.read_bytes()
    def reject(candidate):
        raise PermissionError('401')
    monkeypatch.setattr(credentials_gui, 'verify_sender', reject)
    monkeypatch.setattr(keyring, 'set_password', lambda *a: pytest.fail('Must not save rejected credentials'))
    with pytest.raises(PermissionError):
        credentials_gui.verify_and_save('demo', 'newusr', 'fictional-secret')
    assert account.read_bytes() == before


def test_success_verifies_before_saving(account, monkeypatch):
    import keyring
    calls=[]
    def verify(candidate):
        calls.append('verify')
        assert candidate.password == 'fictional-secret'
        assert 'fictional-secret' not in repr(candidate)
    monkeypatch.setattr(credentials_gui, 'verify_sender', verify)
    monkeypatch.setattr(keyring, 'set_password', lambda *a: calls.append('save'))
    credentials_gui.verify_and_save('demo', 'newusr', 'fictional-secret')
    assert calls == ['verify', 'save']
    assert config.get_box('demo').username == 'newusr'
    assert not config.get_box('demo').allow_receive
    assert 'fictional-secret' not in account.read_text()
