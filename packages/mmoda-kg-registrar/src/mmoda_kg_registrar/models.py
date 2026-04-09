from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, HttpUrl


class WorkflowServicePayload(BaseModel):
    project_repo: HttpUrl
    project_title: str
    last_activity_timestamp: str
    last_deployed_timestamp: str
    service_name: str
    deployment_name: str
    deployment_namespace: str
    creative_work_status: str
# TODO: some info (e.g. messenger) currently only passed to frontend generator.
# With new client-side front in should end up in dispatcher metadata.

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
