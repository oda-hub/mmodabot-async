from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, HttpUrl

class WorkflowServicePayload(BaseModel):
    project_repo: HttpUrl  # URL of the project repository, URIRef of the backend
    project_title: str | None  # Human-readable name, get from repo title
    project_slug: str | None  # URL-friendly name, will be used as "instrument" by dispatcher plugin
    last_activity_timestamp: str  # last commit
    last_deployed_timestamp: str 
    service_endpoint: str
    deployment_name: str  # Helm release name (of not helm, just k8s deployment name?)
    deployment_namespace: str
    creative_work_status: str = "development"

class WorkflowServiceRecord(BaseModel):
    project_repo: HttpUrl
    record: Dict[str, str]


class RegisterResponse(BaseModel):
    status: str
    project_repo: HttpUrl
    record: Dict[str, str]


class UnregisterResponse(BaseModel):
    status: str
    project_repo: HttpUrl
