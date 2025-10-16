import argparse
import os
import subprocess
from models import Run
from sqlalchemy import select
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ruamel.yaml import YAML
yaml = YAML()

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


def process_run(run_id: Run, lyso_peaks_correlate=False):
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
        
        label = f"\"{run.Tray} RU{run.RU} [run {run.run_number}]\""
        
        if run.run_type == "lyso":
            command = f"which python; cd {MTDDAQ_PATH}; . start.sh; {PRE_CMD} tofhir_reco.py {run.run_number}; {plotters[run.run_type]} {run.run_number} {label}"
            if lyso_peaks_correlate:
                command = f"{command}; tofhir_peaks_correlate.py {run.run_number}"
        elif run.run_type == "tp":
            command = f"which python; cd {MTDDAQ_PATH}; . start.sh; {PRE_CMD} tofhir_reco.py {run.run_number}; {plotters[run.run_type]} {run.run_number} {label}"
        elif run.run_type == "calibrate":
            command = f"which python; cd {MTDDAQ_PATH}; . start.sh; {PRE_CMD} {plotters[run.run_type]} {run.run_number} {label}"
        elif run.run_type == "dm_check":
            reco_command = "; ".join(
                [
                    f"{PRE_CMD} tofhir_reco.py {_run_number}"
                    for _run_number in range(run.run_number, run.run_number + 12)
                ]
            )
            
            label = f"\"{run.Tray} RU{run.RU} [runs {run.run_number}-{run.run_number+11}]\""
            command = f"which python; cd {MTDDAQ_PATH}; . start.sh; {reco_command} ; {PRE_CMD} {plotters[run.run_type]} {run.run_number} {run.run_number + 11} {label}"
        else:
            command = f"which python; cd {MTDDAQ_PATH}; . start.sh; {PRE_CMD} {plotters[run.run_type]} {run.run_number} {label}"

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
                link = f"{QAQC_URL}/tofhir/plots_run_{run.run_number}"
            elif run.run_type == "disc":
                link = f"{QAQC_URL}/disc_scan/run_{run.run_number}"
            elif run.run_type == "iv":
                link = f"{QAQC_URL}/iv_scan/run_{run.run_number}"
            elif "calibrate" in run.run_type:
                link = f"{QAQC_URL}/tofhir_calibs/run_{run.run_number}"
            elif run.run_type == "tec":
                link = f"{QAQC_URL}/temps/run_{run.run_number}"
            elif run.run_type == "dm_check":
                link = f"{QAQC_URL}/tofhir/plots_dmPosition_runs_{run.run_number}_{run.run_number + 11}"
        print(link)

        run.plot_link = link

        session.commit()

    print("done")


def poll_db():
    
    parser = argparse.ArgumentParser()
    parser.add_argument("-b","--bac", required = True, type=str, help="BAC", choices = ["MIB", "CIT", "PKU", "UVA", "CERN"])
    args = parser.parse_args()
    
    bac_info_yaml = f"cfg/{args.bac}.yaml"
    with open(bac_info_yaml, "r") as fopen :
        
        d_bac_info = yaml.load(fopen.read())
    
    global automator_path, db_path, DATABASE_URL, engine, SessionLocal, MTDDAQ_PATH, QAQC_URL, PRE_CMD
    
    db_path = d_bac_info["db_path"]
    automator_path = d_bac_info["automator_path"]
    DATABASE_URL = f"sqlite:///{db_path}"
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    MTDDAQ_PATH = d_bac_info["mtd_daq_path"]
    QAQC_URL = d_bac_info["qaqc_url"]
    
    PRE_CMD = d_bac_info["pre_cmd"]
    
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
                process_run(
                    run_id=run.id,
                    lyso_peaks_correlate=d_bac_info["lyso_peaks_correlate"]
                )
            else:
                print(f"[{time.strftime('%H:%M:%S')}] No queued runs.")
        time.sleep(2)


if __name__ == "__main__":
    poll_db()
