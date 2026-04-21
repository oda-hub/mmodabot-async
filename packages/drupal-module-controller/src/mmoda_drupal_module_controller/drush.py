import os
import subprocess
from .jobs import append_log

DRUPAL_ROOT = os.environ.get('DRUPAL_ROOT', "/var/www/mmoda")
DRUSH_EXECUTABLE = os.environ.get('DRUSH_EXECUTABLE', '/root/.composer/vendor/bin/drush')

def run_drush_stream(job_id: str, args: list[str]):
    cmd = [DRUSH_EXECUTABLE, f"--root={DRUPAL_ROOT}", "-y", *args]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if process.stdout:
        for line in process.stdout:
            append_log(job_id, line.strip())

    process.wait()

    if process.returncode != 0:
        raise RuntimeError("Drush command failed")


def run_drush_capture(args: list[str]) -> str:
    """Run drush command and capture output without logging."""
    cmd = [DRUSH_EXECUTABLE, f"--root={DRUPAL_ROOT}", "-y", *args]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Drush command failed: {result.stderr}")

    return result.stdout


def is_module_enabled(name: str) -> bool:
    """Check if a module is enabled."""
    try:
        output = run_drush_capture(["pm-list", "--status=enabled", f"--package={name}"])
        return name in output
    except RuntimeError:
        return False


def enable_module(job_id: str, name: str):
    run_drush_stream(job_id, ["en", name])


def disable_module(job_id: str, name: str):
    run_drush_stream(job_id, ["dis", name])


def uninstall_module(job_id: str, name: str):
    run_drush_stream(job_id, ["pm-uninstall", name])


def clear_cache(job_id: str):
    run_drush_stream(job_id, ["cc", "all"])