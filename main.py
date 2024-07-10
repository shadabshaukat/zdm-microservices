"""
############################################################
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

app = FastAPI()

@app.on_event("startup")
async def display_routes():
    routes = [route.path for route in app.routes]
    print("Available API routes:", routes)

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

def ensure_zdm_home():
    if not os.getenv("ZDM_HOME"):
        raise HTTPException(status_code=500, detail="ZDM_HOME environment variable is not set")

ensure_zdm_home()

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

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        # Since stderr=subprocess.PIPE is set, stderr will always be captured
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        # It's better to log the actual error message for debugging purposes
        error_message = f"Query Job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)

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
    migration_script_lines = [
        "#!/bin/bash",
        "$ZDM_HOME/bin/zdmcli migrate database \\",
    ]

    if params.sourcedb:
        migration_script_lines.append(f"    -sourcedb {params.sourcedb} \\")
    if params.sourcesid:
        migration_script_lines.append(f"    -sourcesid {params.sourcesid} \\")

    migration_script_lines.extend([
        f"    -rsp {params.rsp} \\",
        f"    -sourcenode {params.sourcenode} \\",
    ])

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
        ignoremissingpatches_str = ",".join(params.ignoremissingpatches)
        migration_script_lines.append(f"    -ignoremissingpatches {ignoremissingpatches_str} \\")
    if params.ignore:
        ignore_str = ",".join(params.ignore)
        migration_script_lines.append(f"    -ignore {ignore_str} \\")
    if params.incrementalinterval is not None:
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

    # Remove trailing backslash from the last line
    if migration_script_lines[-1].endswith("\\"):
        migration_script_lines[-1] = migration_script_lines[-1][:-1]

    migration_script = "\n".join(migration_script_lines)

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
        # Since stderr=subprocess.PIPE is set, stderr will always be captured
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        # It's better to log the actual error message for debugging purposes
        error_message = f"DB Migration Job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)

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
        # Since stderr=subprocess.PIPE is set, stderr will always be captured
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        # It's better to log the actual error message for debugging purposes
        error_message = f"Query Job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)

@app.post("/resume/{jobid}")
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
        # Since stderr=subprocess.PIPE is set, stderr will always be captured
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        # It's better to log the actual error message for debugging purposes
        error_message = f"Query Job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)

class ResumeParams(BaseModel):
    pauseafter: Optional[str] = None
    skip: Optional[str] = None

## API to Resume a Job and Pause Again at Another Stage
@app.post("/resume_pauseagain/{jobid}")
def resume_pauseagain(jobid: str, params: ResumeParams = Body(None), username: str = Depends(verify_credentials)):
    resume_pauseagain_script = [
        "#!/bin/bash",
        f"$ZDM_HOME/bin/zdmcli resume job -jobid {jobid}"
    ]

    if params.pauseafter:
        resume_pauseagain_script.append(f" -pauseafter {params.pauseafter}")
    if params.skip:
        resume_pauseagain_script.append(f" -skip {params.skip}")

    # Join the script lines into a single command
    resume_script_v2 = " \\\n".join(resume_pauseagain_script)

    script_path = "/tmp/resume_pauseagain.sh"
    with open(script_path, "w") as script_file:
        script_file.write(resume_script_v2)

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
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        error_message = f"Resume Pause Again Job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)


class ResponseFileParams(BaseModel):
    filename: str
    TGT_DB_UNIQUE_NAME: Optional[str] = None
    MIGRATION_METHOD: Optional[str] = None
    DATA_TRANSFER_MEDIUM: Optional[str] = None
    PLATFORM_TYPE: Optional[str] = None
    BACKUP_PATH: Optional[str] = None
    HOST: Optional[str] = None
    OPC_CONTAINER: Optional[str] = None
    NONCDBTOPDB_CONVERSION: Optional[str] = None
    NONCDBTOPDB_SWITCHOVER: Optional[str] = None
    SKIP_FALLBACK: Optional[str] = None
    TGT_SKIP_DATAPATCH: Optional[str] = None
    SRC_RMAN_CHANNELS: Optional[int] = None
    TGT_RMAN_CHANNELS: Optional[int] = None
    ZDM_BACKUP_TAG: Optional[str] = None
    ZDM_RMAN_DIRECT_METHOD: Optional[str] = None
    ZDM_USE_DG_BROKER: Optional[str] = None
    ZDM_TGT_UPGRADE_TIMEZONE: Optional[str] = None
    ZDM_SKIP_TDE_WALLET_MIGRATION: Optional[str] = None

@app.post("/createResponseFile")
def create_response_file(params: ResponseFileParams, username: str = Depends(verify_credentials)):
    rsp_content = (
        f"TGT_DB_UNIQUE_NAME={params.TGT_DB_UNIQUE_NAME or ''}\n"
        f"MIGRATION_METHOD={params.MIGRATION_METHOD or ''}\n"
        f"DATA_TRANSFER_MEDIUM={params.DATA_TRANSFER_MEDIUM or ''}\n"
        f"PLATFORM_TYPE={params.PLATFORM_TYPE or ''}\n"
        f"BACKUP_PATH={params.BACKUP_PATH or ''}\n"
        f"HOST={params.HOST or ''}\n"
        f"OPC_CONTAINER={params.OPC_CONTAINER or ''}\n"
        f"NONCDBTOPDB_CONVERSION={params.NONCDBTOPDB_CONVERSION or ''}\n"
        f"NONCDBTOPDB_SWITCHOVER={params.NONCDBTOPDB_SWITCHOVER or ''}\n"
        f"SKIP_FALLBACK={params.SKIP_FALLBACK or ''}\n"
        f"TGT_SKIP_DATAPATCH={params.TGT_SKIP_DATAPATCH or ''}\n"
        f"SRC_RMAN_CHANNELS={params.SRC_RMAN_CHANNELS or ''}\n"
        f"TGT_RMAN_CHANNELS={params.TGT_RMAN_CHANNELS or ''}\n"
        f"ZDM_BACKUP_TAG={params.ZDM_BACKUP_TAG or ''}\n"
        f"ZDM_RMAN_DIRECT_METHOD={params.ZDM_RMAN_DIRECT_METHOD or ''}\n"
        f"ZDM_USE_DG_BROKER={params.ZDM_USE_DG_BROKER or ''}\n"
        f"ZDM_TGT_UPGRADE_TIMEZONE={params.ZDM_TGT_UPGRADE_TIMEZONE or ''}\n"
        f"ZDM_SKIP_TDE_WALLET_MIGRATION={params.ZDM_SKIP_TDE_WALLET_MIGRATION or ''}\n"
    )

    script_path = f"/tmp/{params.filename}.rsp"
    with open(script_path, "w") as rsp_file:
        rsp_file.write(rsp_content)

    return {"status": "success", "message": f"Response file {params.filename}.rsp created successfully", "path": script_path}

class LogFileParams(BaseModel):
    file_path: str

@app.post("/ReadJobLog")
def read_job_log(params: LogFileParams, username: str = Depends(verify_credentials)):
    file_path = params.file_path
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        with open(file_path, 'r') as file:
            content = file.read()
        return {"status": "success", "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

class WalletFileParams(BaseModel):
    wallet_path: str

@app.post("/OraPKICreateWallet")
def create_wallet(params: WalletFileParams, username: str = Depends(verify_credentials)):
    wallet_path = params.wallet_path
    create_wallet_script = [
        "#!/bin/bash",
        f"$ZDM_HOME/bin/orapki wallet create -wallet {wallet_path} -auto_login_only"
    ]

    # Join the script lines into a single command
    create_wallet_command = " \\\n".join(create_wallet_script)

    script_path = "/tmp/create_wallet.sh"
    with open(script_path, "w") as script_file:
        script_file.write(create_wallet_command)

    os.chmod(script_path, 0o755)

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout.strip()
        error_output = result.stderr.strip()

        if result.returncode == 0:
            return {"status": "success", "output": output}
        else:
            raise HTTPException(status_code=500, detail={"error": error_output, "output": output})
    except subprocess.CalledProcessError as e:
        error_message = f"Create Wallet failed with return code {e.returncode}: {e.stderr}"
        raise HTTPException(status_code=500, detail=error_message)

class MkstoreParams(BaseModel):
    wallet_path: str
    user: str
    password: str

@app.post("/MkstoreCreateCredential")
def create_credential(params: MkstoreParams, username: str = Depends(verify_credentials)):
    wallet_path = params.wallet_path
    user = params.user
    password = params.password
    create_credential_script = [
        "#!/bin/bash",
        f"$ZDM_HOME/bin/mkstore -wrl {wallet_path} -createCredential store {user} {password}"
    ]

    # Join the script lines into a single command
    create_credential_command = " \\\n".join(create_credential_script)

    script_path = "/tmp/create_credential.sh"
    with open(script_path, "w") as script_file:
        script_file.write(create_credential_command)

    os.chmod(script_path, 0o755)

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout.strip()
        error_output = result.stderr.strip()

        if result.returncode == 0:
            return {"status": "success", "output": output}
        else:
            raise HTTPException(status_code=500, detail={"error": error_output, "output": output})
    except subprocess.CalledProcessError as e:
        error_message = f"Create Credential failed with return code {e.returncode}: {e.stderr}"
        raise HTTPException(status_code=500, detail=error_message)

@app.post("/abort/{jobid}")
def abort(jobid: str, username: str = Depends(verify_credentials)):
    abort_script = f"""
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli abort job -jobid {jobid}
    """
    abort_script_path = "/tmp/abort.sh"
    with open(abort_script_path, "w", newline='\n') as script_file:
        script_file.write(abort_script)

    os.chmod(abort_script_path, 0o755)

    try:
        result = subprocess.run(
            ["bash", abort_script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        error_message = f"Abort job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)

@app.post("/suspend/{jobid}")
def suspend(jobid: str, username: str = Depends(verify_credentials)):
    suspend_script = f"""
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli suspend job -jobid {jobid}
    """
    suspend_script_path = "/tmp/suspend.sh"
    with open(suspend_script_path, "w", newline='\n') as script_file:
        script_file.write(suspend_script)

    os.chmod(suspend_script_path, 0o755)

    try:
        result = subprocess.run(
            ["bash", suspend_script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        error_message = f"Suspend job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
