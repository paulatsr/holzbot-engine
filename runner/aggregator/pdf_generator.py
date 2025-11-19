from __future__ import annotations

import subprocess

from runner.config.settings import RunnerSettings
from runner.utils import logging as runner_logging


def generate(settings: RunnerSettings) -> None:
    cmd = [settings.python_bin, "offer_pdf.py"]
    runner_logging.log("Pornesc generatorul de PDF")
    proc = subprocess.Popen(cmd, cwd=str(settings.project_root))
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"offer_pdf.py failed with exit {ret}")
    runner_logging.log("PDF generat cu succes")


if __name__ == "__main__":
    generate(RunnerSettings.load())
