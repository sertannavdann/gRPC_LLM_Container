"""
POST /bank/upload: a dropped CSV lands in BANK_DATA_DIR and the bank cache reloads.

Mounts the real handler on a bare FastAPI app (auth middleware is not part of
the app here; the production app applies it to every non-public path).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import dashboard_service.main as dashboard_main
from dashboard_service.bank_service import BankService

CSV = (
    "Date,Description,Amount,Payment,Card\n"
    "2026-09-01,COFFEE SHOP,4.50,,4500********1234\n"
    "2026-09-02,GROCERY MART,52.10,,4500********1234\n"
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BANK_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard_main, "_bank_service", BankService(str(tmp_path)))
    cleared = []

    class _Aggregator:
        def clear_cache(self, user_id=None):
            cleared.append(user_id)

    monkeypatch.setattr(dashboard_main, "get_aggregator", lambda user_id: _Aggregator())

    app = FastAPI()
    app.post("/bank/upload")(dashboard_main.upload_bank_csv)
    return TestClient(app), tmp_path, cleared


def test_csv_upload_is_saved_and_reloaded(client):
    c, data_dir, cleared = client
    resp = c.post("/bank/upload", files={"file": ("statement.csv", CSV, "text/csv")})
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["success"] is True
    assert body["file"] == "statement.csv"
    assert body["transactions"] == 2
    assert (data_dir / "statement.csv").read_text() == CSV
    assert cleared == ["default"]


def test_filename_is_sanitised(client):
    c, data_dir, _ = client
    resp = c.post("/bank/upload", files={"file": ("../my bank (sept).csv", CSV, "text/csv")})
    assert resp.status_code == 200, resp.text
    assert resp.json()["file"] == "my_bank__sept_.csv"
    assert (data_dir / "my_bank__sept_.csv").exists()
    assert not (data_dir.parent / "my bank (sept).csv").exists()


def test_non_csv_is_rejected(client):
    c, data_dir, _ = client
    resp = c.post("/bank/upload", files={"file": ("notes.txt", "hello", "text/plain")})
    assert resp.status_code == 400
    assert list(data_dir.iterdir()) == []


def test_empty_file_is_rejected(client):
    c, data_dir, _ = client
    resp = c.post("/bank/upload", files={"file": ("empty.csv", "   \n", "text/csv")})
    assert resp.status_code == 400
    assert list(data_dir.iterdir()) == []
