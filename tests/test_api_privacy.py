from fastapi.testclient import TestClient

from server import app


def test_session_admin_endpoints_are_not_public():
    client = TestClient(app)

    assert client.get("/api/v1/sessions").status_code == 404
    assert client.get("/api/v1/sessions/s_demo").status_code == 404
    assert client.delete("/api/v1/sessions/s_demo").status_code == 404
    assert client.delete("/api/v1/sessions").status_code == 404


def test_public_session_creation_still_works():
    client = TestClient(app)

    res = client.post(
        "/api/v1/sessions",
        json={
            "name": "A",
            "gender": "female",
            "date": "1991-08-15",
            "time": "14:30",
            "place": "杭州",
            "question": "看看事业",
        },
    )

    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.json()["session_id"].startswith("s_")
