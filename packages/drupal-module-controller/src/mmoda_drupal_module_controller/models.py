from pydantic import BaseModel


class ModuleCreate(BaseModel):
    instr_name: str
    title: str
    messenger: str = ""
    creative_work_status: str = "development"
    acknowledgement: str = ""
    instrument_version: str | None = None
    instrument_version_link: str | None = None
    help_html: str | None = None

class ModuleJobCreated(BaseModel):
    job_id: str
    status: str


class JobStatus(BaseModel):
    status: str
    created_at: float
    logs: list[str]
    result: str | None = None
    error: str | None = None