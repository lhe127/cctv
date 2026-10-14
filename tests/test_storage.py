import json
from unittest.mock import patch

import pytest

from sentinel.storage import JsonStateStore


@pytest.mark.parametrize("payload", [b"", b"   ", b'{"version":1,', b"\xff"])
def test_invalid_state_is_preserved_and_new_history_survives_restart(tmp_path, payload):
    path = tmp_path / "state.json"
    path.write_bytes(payload)
    store = JsonStateStore(path)
    assert store.load_findings() == []
    backups = list(tmp_path.glob("state.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == payload
    assert store.load_events() == []
    store.append_finding({"description": "test finding"})
    assert JsonStateStore(path).load_findings() == [{"description": "test finding"}]
    assert len(list(tmp_path.glob("state.json.corrupt-*"))) == 1


def test_bom_state_preserves_history(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 1, "findings": [{"id": "existing"}]}), encoding="utf-8-sig")
    assert JsonStateStore(path).load_findings() == [{"id": "existing"}]
    assert not list(tmp_path.glob("*.corrupt-*"))


def test_unsupported_version_is_not_reset(tmp_path):
    path = tmp_path / "state.json"
    payload = b'{"version": 99}'
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="unsupported state"):
        JsonStateStore(path).load_findings()
    assert path.read_bytes() == payload


def test_failed_replace_keeps_previous_history(tmp_path):
    path = tmp_path / "state.json"
    store = JsonStateStore(path)
    store.append_finding({"id": "previous"})
    with patch("sentinel.storage.os.replace", side_effect=PermissionError):
        with pytest.raises(PermissionError):
            store.append_finding({"id": "new"})
    assert store.load_findings() == [{"id": "previous"}]
    assert not path.with_suffix(".json.tmp").exists()


def test_startup_with_empty_state(tmp_path):
    from sentinel.api import create_app
    from fastapi.testclient import TestClient

    path = tmp_path / "state.json"
    path.write_bytes(b"")
    with TestClient(create_app("config.example.json", "test-key", str(path))) as client:
        assert client.get("/health").status_code == 200
