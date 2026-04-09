import time

jobs = {}

def create_job(job_id):
    jobs[job_id] = {
        "status": "queued",
        "created_at": time.time(),
        "logs": [],
        "result": None,
        "error": None,
    }

def update_job(job_id, **kwargs):
    jobs[job_id].update(kwargs)

def append_log(job_id, line):
    jobs[job_id]["logs"].append(line)

def get_job(job_id):
    return jobs.get(job_id)