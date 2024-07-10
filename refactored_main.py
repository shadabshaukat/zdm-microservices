"""
############################################################
# DO NOT USE THIS!! Use the main.py for now
# Code Contributors
# Shadab Mohammad, Master Principal Cloud Architect
# Organization: Oracle
############################################################
"""

from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import Optional, List
import subprocess
import os
from passlib.context import CryptContext
import logging

# Initialize FastAPI app
app = FastAPI()

# Set up logging
logging.basicConfig(level=logging.INFO)

# Ensure ZDM_HOME is set
def ensure_zdm_home():
    if not os.getenv("ZDM_HOME"):
        raise HTTPException(status_code=500, detail="ZDM_HOME environment variable is not set")

# Basic authentication
security = HTTPBasic()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
USER_CREDENTIALS = {
    "zdmuser": pwd_context.hash("YourPassword123#_"),
    "user1": pwd_context.hash("YourPassword123#_")
}

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    if not (pwd_context.verify(credentials.password, USER_CREDENTIALS.get(credentials.username))):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username

@app.on_event("startup")
async def display_routes():
    routes = [route.path for route in app.routes]
    logging.info(f"Available API routes: {routes}")

# Helper function to execute shell scripts
def run_shell_script(script_path: str) -> str:
    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return output
    except subprocess.CalledProcessError as e:
        error_message = f"Shell script failed with return code {e.returncode}: {e.output}"
        logging.error(error_message)
        raise HTTPException(status_code=500, detail=error_message)

# Models for request bodies
class EvalParams(BaseModel):
    sourcedb: str
    sourcenode: str
    srcauth: str
    srcarg1: str
    srcarg2: str
    srcarg3: str
    targetnode: str
    tgtauth: str
    tgtarg1: str
    tgtarg2: str
    tgtarg3: str
    rsp: str
    sourcesyswallet: str

@app.post("/eval")
def eval(params: EvalParams, username: str = Depends(verify_credentials)):
    ensure_zdm_home()

    eval_script = f"""
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli migrate database \\
        -sourcedb {params.sourcedb} \\
        -sourcenode {params.sourcenode} \\
        -srcauth {params.srcauth} \\
        -srcarg1 {params.srcarg1} \\
        -srcarg2 {params.srcarg2} \\
        -srcarg3 {params.srcarg3} \\
        -targetnode {params.targetnode} \\
        -tgtauth {params.tgtauth} \\
        -tgtarg1 {params.tgtarg1} \\
        -tgtarg2 {params.tgtarg2} \\
        -tgtarg3 {params.tgtarg3} \\
        -rsp {params.rsp} \\
        -sourcesyswallet {params.sourcesyswallet} \\
        -eval
    """
    script_path = "/tmp/eval.sh"
    with open(script_path, "w") as script_file:
        script_file.write(eval_script)
    os.chmod(script_path, 0o755)
    return {"status": "success", "output": run_shell_script(script_path)}

class DBMigrationParams(BaseModel):
    sourcedb: Optional[str]
    sourcesid: Optional[str]
    rsp: str
    sourcenode: str
    targetnode: Optional[str]
    targethome: Optional[str]
    eval: Optional[bool] = False
    imagetype: Optional[str]
    tdekeystorepasswd: Optional[str]
    tgttdekeystorepasswd: Optional[str]
    tdemasterkey: Optional[str]
    useractiondata: Optional[str]
    backupuser: Optional[str]
    backuppasswd: Optional[str]
    dvowner: Optional[str]
    srcroot: Optional[bool] = False
    srccred: Optional[str]
    srcuser: Optional[str]
    srcsudouser: Optional[str]
    srcsudopath: Optional[str]
    srcauth: Optional[str]
    srcarg1: Optional[str]
    srcarg2: Optional[str]
    srcarg3: Optional[str]
    sourcesyswallet: str
    tgtroot: Optional[bool] = False
    tgtcred: Optional[str]
    tgtuser: Optional[str]
    tgtsudouser: Optional[str]
    tgtsudopath: Optional[str]
    tgtauth: Optional[str]
    tgtarg1: Optional[str]
    tgtarg2: Optional[str]
    tgtarg3: Optional[str]
    schedule: Optional[str]
    pauseafter: Optional[str]
    stopafter: Optional[str]
    listphases: Optional[bool] = False
    ignoremissingpatches: Optional[List[str]]
    ignore: Optional[List[str]]
    incrementalinterval: Optional[int]
    advisor: Optional[bool] = False
    ignoreadvisor: Optional[bool] = False
    skipadvisor: Optional[bool] = False
    summary: Optional[bool] = False
    genfixup: Optional[str]

@app.post("/migratedb/physical")
def migratedb_physical(params: DBMigrationParams, username: str = Depends(verify_credentials)):
    ensure_zdm_home()

    migration_script_lines = [
        "#!/bin/bash",
        "$ZDM_HOME/bin/zdmcli migrate database \\",
        f"    -rsp {params.rsp} \\",
        f"    -sourcenode {params.sourcenode} \\",
    ]

    if params.sourcedb:
        migration_script_lines.append(f"    -sourcedb {params.sourcedb} \\")
    if params.sourcesid:
        migration_script_lines.append(f"    -sourcesid {params.sourcesid} \\")
    if params.targetnode:
        migration_script_lines.append(f"    -targetnode {params.targetnode} \\")
    if params.targethome:
        migration_script_lines.append(f"    -targethome {params.targethome} \\")
    if params.eval:
        migration_script_lines.append(f"    -eval \\")
    if params.imagetype:
        migration_script_lines.append(f"    -imagetype {params.imagetype} \\")
    if params.tdekeystorepasswd:
        migration_script_lines.append(f"    -tdekeystorepasswd {params.tdekeystorepasswd} \\")
    if params.tgttdekeystorepasswd:
        migration_script_lines.append(f"    -tgttdekeystorepasswd {params.tgttdekeystorepasswd} \\")
    if params.tdemasterkey:
        migration_script_lines.append(f"    -tdemasterkey {params.tdemasterkey} \\")
    if params.useractiondata:
        migration_script_lines.append(f"    -useractiondata {params.useractiondata} \\")
    if params.backupuser:
        migration_script_lines.append(f"    -backupuser {params.backupuser} \\")
    if params.backuppasswd:
        migration_script_lines.append(f"    -backuppasswd {params.backuppasswd} \\")
    if params.dvowner:
        migration_script_lines.append(f"    -dvowner {params.dvowner} \\")
    if params.srcroot:
        migration_script_lines.append(f"    -srcroot \\")
    if params.srccred:
        migration_script_lines.append(f"    -srccred {params.srccred} \\")
    if params.srcuser:
        migration_script_lines.append(f"    -srcuser {params.srcuser} \\")
    if params.srcsudouser:
        migration_script_lines.append(f"    -srcsudouser {params.srcsudouser} \\")
    if params.srcsudopath:
        migration_script_lines.append(f"    -srcsudopath {params.srcsudopath} \\")
    if params.srcauth:
        migration_script_lines.append(f"    -srcauth {params.srcauth} \\")
    if params.srcarg1:
        migration_script_lines.append(f"    -srcarg1 {params.srcarg1} \\")
    if params.srcarg2:
        migration_script_lines.append(f"    -srcarg2 {params.srcarg2} \\")
    if params.srcarg3:
        migration_script_lines.append(f"    -srcarg3 {params.srcarg3} \\")
    if params.sourcesyswallet:
        migration_script_lines.append(f"    -sourcesyswallet {params.sourcesyswallet} \\")
    if params.tgtroot:
        migration_script_lines.append(f"    -tgtroot \\")
    if params.tgtcred:
        migration_script_lines.append(f"    -tgtcred {params.tgtcred} \\")
    if params.tgtuser:
        migration_script_lines.append(f"    -tgtuser {params.tgtuser} \\")
    if params.tgtsudouser:
        migration_script_lines.append(f"    -tgtsudouser {params.tgtsudouser} \\")
    if params.tgtsudopath:
        migration_script_lines.append(f"    -tgtsudopath {params.tgtsudopath} \\")
    if params.tgtauth:
        migration_script_lines.append(f"    -tgtauth {params.tgtauth} \\")
    if params.tgtarg1:
        migration_script_lines.append(f"    -tgtarg1 {params.tgtarg1} \\")
    if params.tgtarg2:
        migration_script_lines.append(f"    -tgtarg2 {params.tgtarg2} \\")
    if params.tgtarg3:
        migration_script_lines.append(f"    -tgtarg3 {params.tgtarg3} \\")
    if params.schedule:
        migration_script_lines.append(f"    -schedule {params.schedule} \\")
    if params.pauseafter:
        migration_script_lines.append(f"    -pauseafter {params.pauseafter} \\")
    if params.stopafter:
        migration_script_lines.append(f"    -stopafter {params.stopafter} \\")
    if params.listphases:
        migration_script_lines.append(f"    -listphases \\")
    if params.ignoremissingpatches:
        for patch in params.ignoremissingpatches:
            migration_script_lines.append(f"    -ignoremissingpatches {patch} \\")
    if params.ignore:
        for item in params.ignore:
            migration_script_lines.append(f"    -ignore {item} \\")
    if params.incrementalinterval:
        migration_script_lines.append(f"    -incrementalinterval {params.incrementalinterval} \\")
    if params.advisor:
        migration_script_lines.append(f"    -advisor \\")
    if params.ignoreadvisor:
        migration_script_lines.append(f"    -ignoreadvisor \\")
    if params.skipadvisor:
        migration_script_lines.append(f"    -skipadvisor \\")
    if params.summary:
        migration_script_lines.append(f"    -summary \\")
    if params.genfixup:
        migration_script_lines.append(f"    -genfixup {params.genfixup} \\")

    migration_script = "\n".join(migration_script_lines)
    script_path = "/tmp/migrate_physical.sh"
    with open(script_path, "w") as script_file:
        script_file.write(migration_script)
    os.chmod(script_path, 0o755)
    return {"status": "success", "output": run_shell_script(script_path)}

class ControlJobParams(BaseModel):
    jobid: str

@app.post("/abort")
def abort_job(params: ControlJobParams, username: str = Depends(verify_credentials)):
    ensure_zdm_home()

    abort_script = f"""
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli abort job -jobid {params.jobid}
    """
    script_path = "/tmp/abort.sh"
    with open(script_path, "w") as script_file:
        script_file.write(abort_script)
    os.chmod(script_path, 0o755)
    return {"status": "success", "output": run_shell_script(script_path)}

@app.post("/suspend")
def suspend_job(params: ControlJobParams, username: str = Depends(verify_credentials)):
    ensure_zdm_home()

    suspend_script = f"""
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli suspend job -jobid {params.jobid}
    """
    script_path = "/tmp/suspend.sh"
    with open(script_path, "w") as script_file:
        script_file.write(suspend_script)
    os.chmod(script_path, 0o755)
    return {"status": "success", "output": run_shell_script(script_path)}
