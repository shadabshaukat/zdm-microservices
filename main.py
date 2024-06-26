from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import Optional, List
import subprocess
import os
from passlib.context import CryptContext

app = FastAPI()

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
    eval_script = f"""
    #!/bin/bash
    zdmcli migrate database \\
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

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        # Check if there's any output on stderr
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Evaluation script failed: {e}")


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
    migration_script = f"""
    #!/bin/bash
    zdmcli migrate database \\
        {'-sourcedb ' + params.sourcedb if params.sourcedb else ''} \\
        {'-sourcesid ' + params.sourcesid if params.sourcesid else ''} \\
        -rsp {params.rsp} \\
        -sourcenode {params.sourcenode} \\
        {'-targetnode ' + params.targetnode if params.targetnode else ''} \\
        {'-targethome ' + params.targethome if params.targethome else ''} \\
        {'-eval' if params.eval else ''} \\
        {'-imagetype ' + params.imagetype if params.imagetype else ''} \\
        {'-tdekeystorepasswd' if params.tdekeystorepasswd else ''} \\
        {'-tgttdekeystorepasswd ' + params.tgttdekeystorepasswd if params.tgttdekeystorepasswd else ''} \\
        {'-tdemasterkey ' + params.tdemasterkey if params.tdemasterkey else ''} \\
        {'-useractiondata ' + params.useractiondata if params.useractiondata else ''} \\
        {'-backupuser ' + params.backupuser if params.backupuser else ''} \\
        {'-backuppasswd' if params.backuppasswd else ''} \\
        {'-dvowner ' + params.dvowner if params.dvowner else ''} \\
        {'-srcroot' if params.srcroot else ''} \\
        {'-srccred ' + params.srccred if params.srccred else ''} \\
        {'-srcuser ' + params.srcuser if params.srcuser else ''} \\
        {'-srcsudouser ' + params.srcsudouser if params.srcsudouser else ''} \\
        {'-srcsudopath ' + params.srcsudopath if params.srcsudopath else ''} \\
        {'-srcauth ' + params.srcauth if params.srcauth else ''} \\
        {'-srcarg1 ' + params.srcarg1 if params.srcarg1 else ''} \\
        {'-srcarg2 ' + params.srcarg2 if params.srcarg2 else ''} \\
        {'-srcarg3 ' + params.srcarg3 if params.srcarg3 else ''} \\
        {'-tgtroot' if params.tgtroot else ''} \\
        {'-tgtcred ' + params.tgtcred if params.tgtcred else ''} \\
        {'-tgtuser ' + params.tgtuser if params.tgtuser else ''} \\
        {'-tgtsudouser ' + params.tgtsudouser if params.tgtsudouser else ''} \\
        {'-tgtsudopath ' + params.tgtsudopath if params.tgtsudopath else ''} \\
        {'-tgtauth ' + params.tgtauth if params.tgtauth else ''} \\
        {'-tgtarg1 ' + params.tgtarg1 if params.tgtarg1 else ''} \\
        {'-tgtarg2 ' + params.tgtarg2 if params.tgtarg2 else ''} \\
        {'-tgtarg3 ' + params.tgtarg3 if params.tgtarg3 else ''} \\
        {'-schedule ' + params.schedule if params.schedule else ''} \\
        {'-pauseafter ' + params.pauseafter if params.pauseafter else ''} \\
        {'-stopafter ' + params.stopafter if params.stopafter else ''} \\
        {'-listphases' if params.listphases else ''} \\
        {'-ignoremissingpatches ' + ','.join(params.ignoremissingpatches) if params.ignoremissingpatches else ''} \\
        {'-ignore ' + ','.join(params.ignore) if params.ignore else ''} \\
        {'-incrementalinterval ' + str(params.incrementalinterval) if params.incrementalinterval else ''} \\
        {'-advisor' if params.advisor else ''} \\
        {'-ignoreadvisor' if params.ignoreadvisor else ''} \\
        {'-skipadvisor' if params.skipadvisor else ''} \\
        {'-summary' if params.summary else ''} \\
        {'-genfixup ' + params.genfixup if params.genfixup else ''}
    """
    script_path = "/tmp/migratedb_physical.sh"
    with open(script_path, "w") as script_file:
        script_file.write(migration_script)

    os.chmod(script_path, 0o755)

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        # Check if there's any output on stderr
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Migration script failed: {e}")


@app.get("/query/{jobid}")
def query(jobid: str, username: str = Depends(verify_credentials)):
    query_script = f"""
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli query job -jobid {jobid}
    """
    script_path = "/tmp/query.sh"
    with open(script_path, "w") as script_file:
        script_file.write(query_script)

    os.chmod(script_path, 0o755)

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        # Check if there's any output on stderr
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Query Job failed: {e}")


@app.get("/resume/{jobid}")
def resume(jobid: str, username: str = Depends(verify_credentials)):
    resume_script = f"""
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli resume job -jobid {jobid}
    """
    script_path = "/tmp/resume.sh"
    with open(script_path, "w") as script_file:
        script_file.write(resume_script)

    os.chmod(script_path, 0o755)

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        # Check if there's any output on stderr
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Resume Job failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
