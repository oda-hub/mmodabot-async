import uuid
from fastapi import FastAPI, BackgroundTasks, HTTPException

from .models import ModuleCreate, ModuleJobCreated, JobStatus
from .generator import create_module, delete_module
from .drush import enable_module, disable_module, uninstall_module, clear_cache, is_module_enabled
from .jobs import create_job, update_job, get_job, append_log
from .lock import drush_lock

app = FastAPI()


def get_module_name(instr_name: str) -> str:
    """Generate the full Drupal module name from instrument name."""
    return f"mmoda_{instr_name}"


def install_module_job(
    job_id: str,
    instr_name: str,
    title: str,
    messenger: str = "",
    creative_work_status: str = "development",
    acknowledgement: str = "",
    instrument_version: str | None = None,
    instrument_version_link: str | None = None,
    help_html: str | None = None,
):
    try:
        update_job(job_id, status="running")

        append_log(job_id, "Waiting for lock...")
        with drush_lock():
            append_log(job_id, "Lock acquired")

            module_name = get_module_name(instr_name)

            # Check if module is already installed/enabled
            if is_module_enabled(module_name):
                append_log(job_id, "Module already exists, performing reinstall...")

                # Disable and uninstall to clear database configuration
                append_log(job_id, "Disabling existing module")
                disable_module(job_id, module_name)

                append_log(job_id, "Uninstalling existing module")
                uninstall_module(job_id, module_name)

                # Remove existing files
                append_log(job_id, "Removing existing files")
                delete_module(instr_name)

                append_log(job_id, "Clearing cache after uninstall")
                clear_cache(job_id)
            else:
                append_log(job_id, "Installing new module")

            # Create new module files
            append_log(job_id, "Creating module")
            create_module(
                instr_name=instr_name,
                title=title,
                messenger=messenger,
                creative_work_status=creative_work_status,
                acknowledgement=acknowledgement,
                instrument_version=instrument_version,
                instrument_version_link=instrument_version_link,
                help_html=help_html,
            )

            # Enable the module
            append_log(job_id, "Enabling module")
            enable_module(job_id, module_name)

            # Clear cache to ensure changes take effect
            append_log(job_id, "Clearing cache")
            clear_cache(job_id)

        update_job(job_id, status="done", result="installed")

    except Exception as e:
        update_job(job_id, status="failed", error=str(e))


def delete_module_job(job_id: str, instr_name: str):
    try:
        update_job(job_id, status="running")

        append_log(job_id, "Waiting for lock...")
        with drush_lock():
            append_log(job_id, "Lock acquired")

            append_log(job_id, "Disabling module")
            disable_module(job_id, get_module_name(instr_name))

            append_log(job_id, "Uninstalling module")
            uninstall_module(job_id, get_module_name(instr_name))

            append_log(job_id, "Removing files")
            delete_module(instr_name)

            append_log(job_id, "Clearing cache")
            clear_cache(job_id)

        update_job(job_id, status="done", result="removed")

    except Exception as e:
        update_job(job_id, status="failed", error=str(e))



@app.post("/modules", status_code=202, response_model=ModuleJobCreated)
def create_module_endpoint(payload: ModuleCreate, bg: BackgroundTasks):
    job_id = str(uuid.uuid4())
    create_job(job_id)

    bg.add_task(
        install_module_job,
        job_id,
        payload.instr_name,
        payload.title,
        payload.messenger,
        payload.creative_work_status,
        payload.acknowledgement,
        payload.instrument_version,
        payload.instrument_version_link,
        payload.help_html,
    )

    return {"job_id": job_id, "status": "queued"}


@app.delete("/modules/{instr_name}", status_code=202, response_model=ModuleJobCreated)
def delete_module_endpoint(instr_name: str, bg: BackgroundTasks):
    job_id = str(uuid.uuid4())
    create_job(job_id)

    bg.add_task(delete_module_job, job_id, instr_name)

    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job