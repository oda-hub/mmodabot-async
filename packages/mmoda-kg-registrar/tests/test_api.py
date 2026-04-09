from fastapi.testclient import TestClient

from mmoda_kg_registrar.api import app
from mmoda_kg_registrar.graph import TurtleFileKGClient


def test_register_lookup_unregister(tmp_path):
    # create file-backed client in temporary folder
    client = TurtleFileKGClient(str(tmp_path / "kg.ttl"))

    # monkeypatch the dependency provider in app to avoid cross-tests contamination
    import mmoda_kg_registrar.api as api_module
    api_module.get_kg_client = lambda: client

    tc = TestClient(app)
    payload = {
        "project_repo": "https://example.com/myrepo.git",
        "project_title": "My Project",
        "last_activity_timestamp": "2025-09-17T17:08:03.000+02:00",
        "last_deployed_timestamp": "2025-09-17T17:28:03.000+02:00",
        "service_name": "name",
        "deployment_name": "name",
        "deployment_namespace": "default",
        "creative_work_status": "development",
    }

    r = tc.post("/register", json=payload)
    assert r.status_code == 201
    assert r.json()["status"] == "ok"

    r = tc.get("/lookup", params={"repo": payload["project_repo"]})
    assert r.status_code == 200
    assert r.json()["record"]["http://odahub.io/ontology#service_name"] == "name"

    r = tc.delete("/unregister", params={"repo": payload["project_repo"]})
    assert r.status_code == 200

    r = tc.get("/lookup", params={"repo": payload["project_repo"]})
    assert r.status_code == 404
