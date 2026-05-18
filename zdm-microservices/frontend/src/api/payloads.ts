export type ResponseFileRequest = {
  project: string;
  migration_method: string;
  values: Record<string, unknown>;
};

export type SavedJobRunType = 'EVAL' | 'MIGRATE';

export type SavedJobRequest = {
  name: string;
  project: string;
  rsp?: string | null;
  run_type: SavedJobRunType;
  job_parameters?: Record<string, unknown> | null;
  advisor_mode?: string | null;
  flow_control?: string | null;
  flow_phase?: string | null;
  genfixup?: string | null;
  ignore?: string[] | null;
  schedule?: string | null;
  listphases?: boolean | null;
  custom_args?: string[] | null;
};

export type SavedJobPayloadRecord = {
  name: string;
  project: string;
  run_type: SavedJobRunType;
  rsp: string | null;
  job_parameters: Record<string, unknown>;
  advisor_mode: string | null;
  flow_control: string | null;
  flow_phase: string | null;
  genfixup: string | null;
  ignore: string[] | null;
  schedule: string | null;
  listphases: boolean | null;
  custom_args: string[] | null;
};

export type RunJobRequest = Omit<SavedJobPayloadRecord, 'name'> & {
  dry_run: boolean;
};

type BuildResponseFileRequestArgs = {
  project: string;
  migrationMethod: string;
  medium: string;
  values: Record<string, unknown>;
  remaps: unknown[][];
  additional: Record<string, unknown>;
};

type BuildSavedJobRequestArgs = {
  name: string;
  project: string;
  rsp?: string | null;
  runType: SavedJobRunType;
  jobParameters: Record<string, unknown>;
  controls: Record<string, unknown>;
};

export function buildResponseFileRequest({
  project,
  migrationMethod,
  medium,
  values,
  remaps,
  additional,
}: BuildResponseFileRequestArgs): ResponseFileRequest {
  const requestValues: Record<string, unknown> = {
    ...values,
    MIGRATION_METHOD: migrationMethod,
    DATA_TRANSFER_MEDIUM: medium,
  };

  if (remaps.length > 0) {
    requestValues.DATAPUMPSETTINGS_METADATAREMAPS = remaps;
  }

  if (Object.keys(additional).length > 0) {
    requestValues.additional = additional;
  }

  return {
    project,
    migration_method: migrationMethod,
    values: requestValues,
  };
}

export function buildSavedJobRequest({
  name,
  project,
  rsp,
  runType,
  jobParameters,
  controls,
}: BuildSavedJobRequestArgs): SavedJobRequest {
  return {
    ...controls,
    name,
    project,
    rsp,
    run_type: runType,
    job_parameters: jobParameters,
  };
}

export function buildRunJobRequest(
  savedJob: SavedJobPayloadRecord,
  dryRun: boolean,
): RunJobRequest {
  return {
    project: savedJob.project,
    run_type: savedJob.run_type,
    rsp: savedJob.rsp,
    job_parameters: savedJob.job_parameters,
    advisor_mode: savedJob.advisor_mode,
    flow_control: savedJob.flow_control,
    flow_phase: savedJob.flow_phase,
    genfixup: savedJob.genfixup,
    ignore: savedJob.ignore,
    schedule: savedJob.schedule,
    listphases: savedJob.listphases,
    custom_args: savedJob.custom_args,
    dry_run: dryRun,
  };
}
