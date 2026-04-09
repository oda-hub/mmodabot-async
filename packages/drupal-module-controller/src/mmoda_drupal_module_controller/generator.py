from pathlib import Path
import shutil
from mmoda_tab_generator.tab_generator import MMODATabGenerator

INSTRUMENTS_DIR = Path("/var/www/mmoda/sites/all/modules/mmoda/instruments/")
DISPATCHER_URL = "http://oda-dispatcher:8000"

def create_module(
        instr_name: str,
        title: str,
        messenger: str = "",
        creative_work_status: str = "development",
        acknowledgement: str = "",
        instrument_version: str | None = None,
        instrument_version_link: str | None = None,
        help_html: str | None = None
        ):
    generator = MMODATabGenerator(DISPATCHER_URL)
    generator.generate(
        instrument_name=instr_name,
        instruments_dir_path=INSTRUMENTS_DIR,
        frontend_name=instr_name,
        title=title,
        messenger=messenger,
        roles=(
            ""
            if creative_work_status
            == "production"
            else "oda workflow developer"
        ),
        form_dispatcher_url="dispatch-data/run_analysis",
        weight=200,
        citation=acknowledgement,
        instrument_version=instrument_version,
        instrument_version_link=instrument_version_link,
        help_page=help_html,
    )


def delete_module(instr_name: str):
    shutil.rmtree(INSTRUMENTS_DIR / f"mmoda_{instr_name}", ignore_errors=True)