from fastapi import FastAPI, Query, Body, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from models import Run, Base, Tray, db_path
import datetime


### DB Connection
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

### FastAPI

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# API Model
# -----------------------------
class RunRequest(BaseModel):
    TrayLabel: str = "MTD-TrayNULL"
    RU: int
    run_type: str
    run_number: int
    serenity_stdout: str = ""
    serenity_stderr: str = ""


class SerenityFailedRequest(BaseModel):
    TrayLabel: str = "MTD-TrayNULL"
    RU: int
    run_type: str
    serenity_stdout: str = ""
    serenity_stderr: str = ""


class TrayRegisterRequest(BaseModel):
    label: str
    RU0: bool = True
    RU1: bool = True
    RU2: bool = True
    RU3: bool = True
    RU4: bool = True
    RU5: bool = True


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# -----------------------------
# Endpoints
# -----------------------------
@app.post("/submit_run")
async def submit_run(req: RunRequest):
    async with SessionLocal() as session:
        tray_obj = await session.execute(
            text("SELECT 1 FROM trays WHERE label = :label"), {"label": req.TrayLabel}
        )
        if not tray_obj.first():
            raise HTTPException(
                status_code=404, detail=f"Tray '{req.TrayLabel}' not found in database."
            )
        new_run = Run(
            Tray=req.TrayLabel,
            RU=req.RU,
            run_type=req.run_type,
            run_number=req.run_number,
            status="queued",
            serenity_stdout=req.serenity_stdout,
            serenity_stderr=req.serenity_stderr,
        )
        session.add(new_run)
        await session.commit()
        await session.refresh(new_run)
    return {"id": new_run.id, "status": "queued"}


@app.post("/submit_serenity_failed")
async def submit_serenity_failed(req: SerenityFailedRequest):
    async with SessionLocal() as session:
        tray_obj = await session.execute(
            text("SELECT 1 FROM trays WHERE label = :label"), {"label": req.TrayLabel}
        )
        if not tray_obj.first():
            raise HTTPException(
                status_code=404, detail=f"Tray '{req.TrayLabel}' not found in database."
            )
        new_run = Run(
            Tray=req.TrayLabel,
            RU=req.RU,
            run_type=req.run_type,
            run_number=None,
            status="failed on serenity",
            serenity_stdout=req.serenity_stdout,
            serenity_stderr=req.serenity_stderr,
        )
        session.add(new_run)
        await session.commit()
        await session.refresh(new_run)
    return {"id": new_run.id, "status": "failed on serenity"}


@app.post("/register_tray")
async def register_tray(req: TrayRegisterRequest):
    async with SessionLocal() as session:
        # Check if tray already exists
        tray_obj = await session.execute(
            text("SELECT 1 FROM trays WHERE label = :label"), {"label": req.label}
        )
        if tray_obj.first():
            raise HTTPException(
                status_code=400, detail=f"Tray '{req.label}' already exists."
            )
        tray = Tray(
            label=req.label,
            RU0=req.RU0,
            RU1=req.RU1,
            RU2=req.RU2,
            RU3=req.RU3,
            RU4=req.RU4,
            RU5=req.RU5,
        )
        session.add(tray)
        await session.commit()
        await session.refresh(tray)
    return {
        "label": tray.label,
        "RU0": tray.RU0,
        "RU1": tray.RU1,
        "RU2": tray.RU2,
        "RU3": tray.RU3,
        "RU4": tray.RU4,
        "RU5": tray.RU5,
    }


@app.get("/status")
async def get_status(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=10000),
    sort_by: str = Query("date"),
    sort_dir: str = Query("desc"),
    tray: str = Query(None),
    ru: str = Query(None),
    type: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
):
    valid_columns = {"RU", "run_number", "date"}
    if sort_by not in valid_columns:
        sort_by = "date"
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"
    offset = (page - 1) * per_page

    filters = []
    params = {"limit": per_page, "offset": offset}

    if tray:
        filters.append("Tray = :tray")
        params["tray"] = tray
    if ru:
        filters.append("RU = :ru")
        params["ru"] = ru
    if type:
        filters.append("run_type = :type")
        params["type"] = type
    if date_from:
        filters.append("date >= :date_from")
        date_from = datetime.datetime.strptime(date_from, "%Y-%m-%dT%H:%M").astimezone(
            tz=datetime.timezone.utc
        )
        params["date_from"] = date_from
    if date_to:
        filters.append("date <= :date_to")
        date_to = datetime.datetime.strptime(date_to, "%Y-%m-%dT%H:%M").astimezone(
            tz=datetime.timezone.utc
        )
        params["date_to"] = date_to

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = (
        f"SELECT id, run_type, run_number, Tray, RU, status, plot_link, date "
        f"FROM runs {where_clause} "
        f"ORDER BY {sort_by} {sort_dir.upper()}, rowid DESC LIMIT :limit OFFSET :offset"
    )
    count_query = f"SELECT COUNT(*) FROM runs {where_clause}"

    async with SessionLocal() as session:
        result = await session.execute(text(query), params)
        rows = result.fetchall()
        total_result = await session.execute(text(count_query), params)
        total = total_result.scalar()
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "jobs": [
                {
                    "id": r[0],
                    "run_type": r[1],
                    "run_number": r[2],
                    "Tray": r[3],
                    "RU": r[4],
                    "status": r[5],
                    "plot_link": r[6],
                    "date": r[7],
                }
                for r in rows
            ],
        }


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_info(job_id: str):
    async with SessionLocal() as session:
        run = await session.get(Run, job_id)
        if not run:
            return HTMLResponse("<h1>Job not found</h1>", status_code=404)

        # Format date as ISO string with 'Z' to indicate UTC
        date_str = run.date.isoformat() + "Z" if run.date else ""

        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Job {run.id}</title>
            <style>
                body {{ font-family: sans-serif; padding: 2em; }}
                pre {{ background: #f0f0f0; padding: 1em; white-space: pre-wrap; }}
                .toggle-btn {{ cursor:pointer; color:#0074d9; text-decoration:underline; margin-bottom:0.5em; display:inline-block; }}
                .log-section {{ display:none; }}
            </style>
            <script>
                function toggleLog(id) {{
                    var el = document.getElementById(id);
                    if (el.style.display === "none") {{
                        el.style.display = "block";
                    }} else {{
                        el.style.display = "none";
                    }}
                }}
                function showLocalDate() {{
                    var el = document.getElementById("job-date");
                    if (el && el.dataset.utc) {{
                        var d = new Date(el.dataset.utc);
                        el.textContent = d.toLocaleString();
                    }}
                }}
                document.addEventListener("DOMContentLoaded", showLocalDate);
            </script>
        </head>
        <body>
            <div class="navbar">
                <span class="nav-title"><a href="/" style="color:inherit;text-decoration:none;">DAQ Automator</a></span>
                <span>
                    <a href="/register_tray_page" style="color:#ffe066; text-decoration:underline; margin-right:1.5em;">Register Tray</a>
                    <a href="/display_trays_page" style="color:#ffe066; text-decoration:underline; margin-right:1.5em;">Display Trays</a>
                </span>
            </div>
            <p><a href="/">← Back to status</a></p>
            <h1>Job {run.id}</h1>
            <p><strong>Tray:</strong> {run.Tray}</p>
            <p><strong>RU:</strong> {run.RU}</p>
            <p><strong>Type:</strong> {run.run_type}</p>
            <p><strong>Run Number:</strong> {run.run_number if run.run_number is not None else "-"}</p>
            <p><strong>Date:</strong> <span id="job-date" data-utc="{date_str}"></span></p>
            <p><strong>Status:</strong> {run.status}</p>
            <h2>Logs</h2>
            <div>
                <span class="toggle-btn" onclick="toggleLog('serenity_stdout')">Serenity Stdout ▼</span>
                <div id="serenity_stdout" class="log-section">
                    <pre>{run.serenity_stdout or "(empty)"}</pre>
                </div>
                <span class="toggle-btn" onclick="toggleLog('serenity_stderr')">Serenity Stderr ▼</span>
                <div id="serenity_stderr" class="log-section">
                    <pre>{run.serenity_stderr or "(empty)"}</pre>
                </div>
                <span class="toggle-btn" onclick="toggleLog('daq_stdout')">Runner Stdout ▼</span>
                <div id="daq_stdout" class="log-section">
                    <pre>{run.stdout or "(empty)"}</pre>
                </div>
                <span class="toggle-btn" onclick="toggleLog('daq_stderr')">Runner Stderr ▼</span>
                <div id="daq_stderr" class="log-section">
                    <pre>{run.stderr or "(empty)"}</pre>
                </div>
            </div>
            <script>
                // All log sections are closed by default
                document.addEventListener("DOMContentLoaded", function() {{
                    ["daq_stdout","daq_stderr","serenity_stdout","serenity_stderr"].forEach(function(id) {{
                        var el = document.getElementById(id);
                        if (el) el.style.display = "none";
                    }});
                }});
            </script>
        </body>
        </html>
        """)


run_types = [
    "dm_check",
    "calibrate_qdc",
    "calibrate_tdc",
    "lyso",
    "tp",
    "disc",
    "iv",
    "tec",
]


@app.get("/latest_runs_by_tray")
async def latest_runs_by_tray(tray: str):
    result = {}
    async with SessionLocal() as session:
        for t in run_types:
            row = await session.execute(
                text(
                    "SELECT id, run_number FROM runs WHERE Tray = :tray AND run_type = :type ORDER BY date DESC LIMIT 1"
                ),
                {"tray": tray, "type": t},
            )
            val = row.first()
            if val:
                result[t] = {"run_number": val[1], "id": val[0]}
            else:
                result[t] = {"run_number": "-", "id": None}
    return result


@app.delete("/jobs")
async def delete_jobs(ids: list[int] = Body(...)):
    async with SessionLocal() as session:
        if not ids:
            return {"deleted": []}
        # Build a dynamic SQL string with the correct number of placeholders
        placeholders = ", ".join([str(i) for i in ids])
        await session.execute(text(f"DELETE FROM runs WHERE id IN ({placeholders})"))
        await session.commit()
    return {"deleted": ids}


@app.post("/jobs/set_queued")
async def set_jobs_queued(ids: list[int] = Body(...)):
    async with SessionLocal() as session:
        if not ids:
            return {"updated": []}
        placeholders = ", ".join([str(i) for i in ids])
        await session.execute(
            text(f"UPDATE runs SET status='queued' WHERE id IN ({placeholders})")
        )
        await session.commit()
    return {"updated": ids}


with open("/home/cmsdaq/DAQ/automator/frontend/index.html", "r") as f:
    HTML_PAGE = f.read()

with open("/home/cmsdaq/DAQ/automator/frontend/register_tray.html", "r") as f:
    HTML_PAGE_register_tray = f.read()

with open("/home/cmsdaq/DAQ/automator/frontend/display_trays.html", "r") as f:
    HTML_PAGE_display_trays = f.read()


@app.get("/", response_class=HTMLResponse)
async def status_page():
    return HTML_PAGE


@app.get("/register_tray_page", response_class=HTMLResponse)
async def register_tray_page():
    return HTML_PAGE_register_tray


@app.get("/display_trays_page", response_class=HTMLResponse)
async def display_trays_page():
    return HTML_PAGE_display_trays


@app.get("/api/trays")
async def api_trays():
    async with SessionLocal() as session:
        result = await session.execute(
            text("SELECT label, RU0, RU1, RU2, RU3, RU4, RU5 FROM trays")
        )
        trays = [
            {
                "label": row[0],
                "RU0": row[1],
                "RU1": row[2],
                "RU2": row[3],
                "RU3": row[4],
                "RU4": row[5],
                "RU5": row[6],
            }
            for row in result.fetchall()
        ]
        return trays


if __name__ == "__main__":
    import uvicorn
    # import logging

    # # ....CODE....
    # uvicorn_error = logging.getLogger("uvicorn.error")
    # uvicorn_error.disabled = True
    # uvicorn_access = logging.getLogger("uvicorn.access")
    # uvicorn_access.disabled = True

    uvicorn.run("main:app", host="0.0.0.0", port=5558, reload=False)
    # FIXME
    # uvicorn.run("main:app", host="0.0.0.0", port=5558, reload=True)
