import os
import subprocess
from models import Run, db_path
from sqlalchemy import select
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = f"sqlite:///{db_path}"
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

MTDDAQ_PATH = "/home/cmsdaq/DAQ/mtd_daq/"

plotters = {
    "dm_check": "tofhir_dm_position_plot.py",
    "tp": "tofhir_tp_plot.py",
    "lyso": "tofhir_lyso_plot.py",
    "disc": "tofhir_disc_scan_plot.py",
    "iv": "tofhir_iv_scan_plot.py",
    "tec": "temps_plot.py",
    "calibrate_qdc": "tofhir_qdc_plot.py",
    "calibrate_tdc": "tofhir_tdc_plot.py",
}


def process_run(run_id: Run):
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        if not run:
            print(f"[runner] Run ID {run_id} not found")
            return

        # ➕ Mark as processing
        run.status = "processing"
        session.commit()  # commit to reflect in DB

    time.sleep(0.1)

    with SessionLocal() as session:
        run = session.get(Run, run_id)
        env = os.environ.copy()
        env["PATH"] = ":".join(
            list(filter(lambda k: ".venv" not in k, env["PATH"].split(":")))
        )
        start = time.time()

        if run.run_type == "lyso":
            command = f"which python; cd {MTDDAQ_PATH}; . start.sh; tofhir_reco.py {run.run_number}; {plotters[run.run_type]} {run.run_number}; tofhir_peaks_correlate.py {run.run_number}"
        elif run.run_type == "tp":
            command = f"which python; cd {MTDDAQ_PATH}; . start.sh; tofhir_reco.py {run.run_number}; {plotters[run.run_type]} {run.run_number}"
        elif "calibrate" in run.run_type:
            command = f"which python; cd {MTDDAQ_PATH}; . start.sh; {plotters[run.run_type]} {run.run_number}"
        elif run.run_type == "dm_check":
            reco_command = "; ".join(
                [
                    f"tofhir_reco.py {_run_number}"
                    for _run_number in range(run.run_number, run.run_number + 12)
                ]
            )
            command = f"which python; cd {MTDDAQ_PATH}; . start.sh; {reco_command} ; {plotters[run.run_type]} {run.run_number} {run.run_number + 11}"
        else:
            command = f"which python; cd {MTDDAQ_PATH}; . start.sh; {plotters[run.run_type]} {run.run_number}"

        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            executable="/bin/bash",
            env=env,
        )
        stdout, stderr = proc.communicate()

        elapsed = round((time.time() - start) / 60, 2)
        print("Done subprocess")

        run.status = "failed on runner" if proc.returncode != 0 else "completed"
        run.stdout = (
            f"Done processing in {elapsed} minutes\nOutput:\n" + stdout.decode()
        )
        run.stderr = (
            env["PATH"]
            + "\n"
            + stderr.decode()
            + "\nReturn code: "
            + str(proc.returncode)
        )

        link = "#"
        if proc.returncode == 0:
            if run.run_type in ["lyso", "tp"]:
                link = f"http://pc-mtd-tray/tray_qaqc/tofhir/plots_run_{run.run_number}"
            elif run.run_type == "disc":
                link = f"http://pc-mtd-tray/tray_qaqc/disc_scan/run_{run.run_number}"
            elif run.run_type == "iv":
                link = f"http://pc-mtd-tray/tray_qaqc/iv_scan/run_{run.run_number}"
            elif "calibrate" in run.run_type:
                link = (
                    f"http://pc-mtd-tray/tray_qaqc/tofhir_calibs/run_{run.run_number}"
                )
            elif run.run_type == "tec":
                link = f"http://pc-mtd-tray/tray_qaqc/temps/run_{run.run_number}"
            elif run.run_type == "dm_check":
                link = f"http://pc-mtd-tray/tray_qaqc/tofhir/plots_dmPosition_runs_{run.run_number}_{run.run_number + 11}"
        print(link)

        run.plot_link = link

        session.commit()

    print("done")


def poll_db():
    while True:
        with SessionLocal() as session:
            result = session.execute(
                select(Run).where(Run.status == "queued").order_by(Run.run_number)
            )
            runs = result.scalars().all()

        if runs:
            print(
                f"[{time.strftime('%H:%M:%S')}] Found {len(runs)} run(s) to process..."
            )
            for run in runs:
                process_run(run.id)
            else:
                print(f"[{time.strftime('%H:%M:%S')}] No queued runs.")
        time.sleep(2)


if __name__ == "__main__":
    poll_db()
