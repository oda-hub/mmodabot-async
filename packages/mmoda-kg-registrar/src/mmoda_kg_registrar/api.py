from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import HttpUrl

from .graph import KGClient, TurtleFileKGClient
from .models import RegisterResponse, UnregisterResponse, WorkflowServicePayload, WorkflowServiceRecord


def get_kg_client() -> KGClient:
    return TurtleFileKGClient("kg.ttl")


app = FastAPI(title="MMODA KG Registrar", version="0.1.0")


@app.post("/register", status_code=201, response_model=RegisterResponse)
def register(payload: WorkflowServicePayload, client: KGClient = Depends(get_kg_client)) -> RegisterResponse:
    client.upsert_repository(str(payload.project_repo), payload.model_dump(exclude={"project_repo"}))
    record = client.get_repository(str(payload.project_repo))
    return RegisterResponse(status="ok", project_repo=payload.project_repo, record=record)


@app.get("/lookup", response_model=WorkflowServiceRecord)
def lookup(repo: HttpUrl = Query(...), client: KGClient = Depends(get_kg_client)) -> WorkflowServiceRecord:
    record = client.get_repository(str(repo))
    if not record:
        raise HTTPException(status_code=404, detail="not found")
    return WorkflowServiceRecord(project_repo=repo, record=record)


@app.delete("/unregister", response_model=UnregisterResponse)
def unregister(repo: HttpUrl = Query(...), client: KGClient = Depends(get_kg_client)) -> UnregisterResponse:
    deleted = client.delete_repository(str(repo))
    if not deleted:
        raise HTTPException(status_code=404, detail="not found")
    return UnregisterResponse(status="ok", project_repo=repo)
