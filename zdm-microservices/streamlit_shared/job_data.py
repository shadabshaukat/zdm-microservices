from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


JOB_TABLE_COLUMNS = [
    "Project",
    "Migration Method",
    "Job ID",
    "Job Type",
    "Status",
    "Source Node",
    "Source Database",
    "Target Node",
    "Target Database",
    "Current Stage",
    "Started",
    "Ended",
    "Result File",
    "Status Category",
    "Fleet Key",
]

FLEET_TABLE_COLUMNS = [
    "Fleet Key",
    "Project",
    "Migration Method",
    "Source Database",
    "Target Database",
    "Source Node",
    "Target Node",
    "Latest Eval Job",
    "Latest Eval Status",
    "Latest Migrate Job",
    "Latest Migrate Status",
    "Current Job Type",
    "Fleet State",
    "Current Stage",
    "Last Start",
    "Last End",
]

KPI_COLUMNS = ["Total Jobs", "Succeeded", "Running", "Paused", "Suspended", "Failed"]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _first(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            value = value[0] if value else ""
        text = _text(value)
        if text:
            return text
    return ""


def _get_ci(data: Dict[str, Any], *keys: str) -> str:
    if not isinstance(data, dict):
        return ""
    lowered = {str(key).lower(): value for key, value in data.items()}
    for key in keys:
        value = lowered.get(key.lower())
        text = _first(value)
        if text:
            return text
    return ""


def _job_sort_value(job_id: Any) -> int:
    text = _text(job_id)
    return int(text) if text.isdigit() else -1


def zdm_status_category(status: Any) -> str:
    normalized = _text(status).upper().replace("-", "_").replace(" ", "_")
    if normalized in {"SUCCEEDED", "SUCCESS", "DONE", "COMPLETED"}:
        return "Succeeded"
    if normalized in {"RUNNING", "EXECUTING", "IN_PROGRESS", "STARTED"}:
        return "Running"
    if normalized in {"PAUSED", "PAUSING", "PAUSE"}:
        return "Paused"
    if normalized in {"SUSPENDED", "SUSPENDING", "SUSPEND"}:
        return "Suspended"
    if normalized in {"FAILED", "ERROR", "ABORTED"}:
        return "Failed"
    return "Other"


def zdm_migration_method_label(value: Any) -> str:
    normalized = _text(value).upper().replace("-", "_").replace(" ", "_")
    labels = {
        "OFFLINE_LOGICAL": "Logical Offline",
        "ONLINE_LOGICAL": "Logical Online",
        "ONLINE_PHYSICAL": "Physical Online",
        "OFFLINE_PHYSICAL": "Physical Offline",
        "OFFLINE_XTTS": "Hybrid Offline",
        "HYBRID_OFFLINE": "Hybrid Offline",
    }
    if normalized in labels:
        return labels[normalized]
    if normalized:
        return normalized.replace("_", " ").title()
    return "Unknown"


def _migration_method(job: Dict[str, Any], inventory: Dict[str, Any]) -> str:
    project = inventory.get("project") if isinstance(inventory, dict) else {}
    response_file = inventory.get("response_file") if isinstance(inventory, dict) else {}
    attributes = job.get("attributes") if isinstance(job, dict) else {}
    raw = _first(
        _get_ci(project or {}, "migration_method"),
        _get_ci(response_file or {}, "MIGRATION_METHOD"),
        _get_ci(attributes or {}, "migration_method"),
    )
    return zdm_migration_method_label(raw)


def _fleet_key(row: Dict[str, str]) -> str:
    project = row.get("Project", "")
    if project:
        return project
    source_db = row.get("Source Database", "")
    target_db = row.get("Target Database", "")
    if source_db or target_db:
        return f"{source_db or 'unknown source'} -> {target_db or 'unknown target'}"
    source_node = row.get("Source Node", "")
    if source_node:
        return source_node
    return row.get("Job ID", "")


def zdm_job_records_to_dataframe(records: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, str]] = []
    for record in records or []:
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("job"), dict)
            or not isinstance(record.get("inventory"), dict)
        ):
            raise ValueError("zdm_job_records_to_dataframe expects enriched records from GET /jobs with job and inventory objects")
        job = record["job"]
        inventory = record["inventory"]
        scheduled_args = job.get("scheduled_args") or {}
        project = inventory.get("project") or {}
        response_file = inventory.get("response_file") or {}
        source_connection = inventory.get("source_connection") or {}
        target_connection = inventory.get("target_connection") or {}
        times = job.get("times") or {}
        files = job.get("files") or {}

        row = {
            "Project": _first(job.get("project"), _get_ci(project, "name")),
            "Migration Method": _migration_method(job, inventory),
            "Job ID": _text(job.get("job_id")),
            "Job Type": _text(job.get("job_type")).upper(),
            "Status": _text(job.get("status")).upper(),
            "Source Node": _first(
                _get_ci(scheduled_args, "sourcenode"),
                _get_ci(response_file, "SOURCEDATABASE_CONNECTIONDETAILS_HOST"),
                _get_ci(source_connection, "host"),
            ),
            "Source Database": _first(
                _get_ci(scheduled_args, "sourcedb", "sourcesid"),
                _get_ci(response_file, "SOURCEDATABASE_CONNECTIONDETAILS_SERVICENAME"),
                _get_ci(source_connection, "service_name"),
            ),
            "Target Node": _first(
                _get_ci(scheduled_args, "targetnode"),
                _get_ci(response_file, "TARGETDATABASE_CONNECTIONDETAILS_HOST"),
                _get_ci(target_connection, "host"),
            ),
            "Target Database": _first(
                _get_ci(scheduled_args, "targetdb", "tgtdb", "targetsid"),
                _get_ci(response_file, "TARGETDATABASE_CONNECTIONDETAILS_SERVICENAME"),
                _get_ci(target_connection, "service_name"),
            ),
            "Current Stage": _text(job.get("current_phase")),
            "Started": _first(_get_ci(times, "execution_start"), _get_ci(times, "scheduled_start")),
            "Ended": _get_ci(times, "execution_end"),
            "Result File": _get_ci(files, "result"),
            "Status Category": zdm_status_category(job.get("status")),
        }
        row["Fleet Key"] = _fleet_key(row)
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=JOB_TABLE_COLUMNS)

    df = pd.DataFrame(rows)
    df = df.reindex(columns=JOB_TABLE_COLUMNS)
    df["_job_sort"] = df["Job ID"].apply(_job_sort_value)
    df = df.sort_values("_job_sort").drop(columns=["_job_sort"]).reset_index(drop=True)
    return df


def _latest_row(group: pd.DataFrame) -> Optional[pd.Series]:
    if group.empty:
        return None
    work = group.copy()
    work["_job_sort"] = work["Job ID"].apply(_job_sort_value)
    return work.sort_values("_job_sort").iloc[-1]


def zdm_fleet_dataframe(jobs_df: pd.DataFrame) -> pd.DataFrame:
    if jobs_df is None or jobs_df.empty:
        return pd.DataFrame(columns=FLEET_TABLE_COLUMNS)

    rows: List[Dict[str, str]] = []
    for fleet_key, group in jobs_df.groupby("Fleet Key", dropna=False):
        latest = _latest_row(group)
        eval_latest = _latest_row(group[group["Job Type"] == "EVAL"])
        migrate_latest = _latest_row(group[group["Job Type"] == "MIGRATE"])
        if migrate_latest is not None:
            current = migrate_latest
        elif eval_latest is not None:
            current = eval_latest
        else:
            current = latest
        if current is None:
            continue

        fleet_state = _text(current["Status Category"])

        rows.append({
            "Fleet Key": _text(fleet_key),
            "Project": _first(current["Project"], latest["Project"] if latest is not None else ""),
            "Migration Method": _first(current["Migration Method"], latest["Migration Method"] if latest is not None else ""),
            "Source Database": _first(current["Source Database"], latest["Source Database"] if latest is not None else ""),
            "Target Database": _first(current["Target Database"], latest["Target Database"] if latest is not None else ""),
            "Source Node": _first(current["Source Node"], latest["Source Node"] if latest is not None else ""),
            "Target Node": _first(current["Target Node"], latest["Target Node"] if latest is not None else ""),
            "Latest Eval Job": _text(eval_latest["Job ID"]) if eval_latest is not None else "",
            "Latest Eval Status": _text(eval_latest["Status"]) if eval_latest is not None else "",
            "Latest Migrate Job": _text(migrate_latest["Job ID"]) if migrate_latest is not None else "",
            "Latest Migrate Status": _text(migrate_latest["Status"]) if migrate_latest is not None else "",
            "Current Job Type": _text(current["Job Type"]),
            "Fleet State": fleet_state,
            "Current Stage": _text(current["Current Stage"]),
            "Last Start": _text(current["Started"]),
            "Last End": _text(current["Ended"]),
        })

    return pd.DataFrame(rows).reindex(columns=FLEET_TABLE_COLUMNS)


def zdm_job_kpis(jobs_df: pd.DataFrame, job_type: str) -> Dict[str, int]:
    if jobs_df is None or jobs_df.empty:
        return {key: 0 for key in KPI_COLUMNS}
    subset = jobs_df[jobs_df["Job Type"] == _text(job_type).upper()]
    counts = {"Total Jobs": int(len(subset))}
    for label in KPI_COLUMNS[1:]:
        counts[label] = int((subset["Status Category"] == label).sum())
    return counts
