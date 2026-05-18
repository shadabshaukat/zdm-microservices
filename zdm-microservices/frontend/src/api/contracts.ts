export type JsonRecord = Record<string, unknown>;

export type ProjectRecord = {
  name: string;
  rsp: string | null;
  source_connection: string;
  target_connection: string;
  migration_method?: string;
  jobs?: Record<string, string[]>;
};

export type DbConnectionRecord = {
  name: string;
  host: string;
  port: number;
  service_name: string;
  db_type: string;
  connection_role: 'source' | 'target';
  protocol: 'TCP' | 'TCPS';
  allow_tls_without_wallet: boolean;
  tls_wallet_uploaded_dir?: string;
};

export type ProjectWriteResponse = {
  status: 'success';
  message: string;
  project: ProjectRecord;
};

export type DbConnectionWriteResponse = {
  status: 'success';
  message: string;
  connection: DbConnectionRecord;
};

export type CredentialWalletRecord = {
  name: string;
  path: string;
  credential_username: string | null;
};

export type CredentialWalletsResponse = {
  wallets: CredentialWalletRecord[];
};

export type WalletCommandResponse = {
  status: 'success';
  output: string;
};

export type TlsWalletUploadResponse = {
  status: 'success';
  message: string;
  path: string;
  wallet_dir: string;
};

export type DiscoveryResponse = {
  status: 'success';
  message: string;
  snapshot: JsonRecord;
};

export type DiscoveryLatestResponse =
  | { status: 'not_found' }
  | {
    status: 'success';
    file: string;
    snapshot: JsonRecord;
  };

export type JobsDashboardRecord = {
  job: JsonRecord;
  inventory: JsonRecord;
};

export type JobsDashboardResponse = {
  status: 'success';
  source: string;
  last_refreshed: string | null;
  jobs: JobsDashboardRecord[];
  warnings: unknown[];
};

export type JobIdsResponse = {
  job_ids: string[];
};

export type JobQueryResponse = {
  status: 'success';
  output: string;
};

export type JobLogRecord = {
  name: string;
  size_bytes: number;
  modified_time: string;
};

export type JoblogsResponse = {
  status: 'success';
  job_id: string;
  logs: JobLogRecord[];
};

export type JoblogReadResponse = {
  status: 'success';
  job_id: string;
  name: string;
  content: string;
};

export type FrontendNavigationItem = {
  label: string;
  section: string;
  path: string;
};

export type FrontendNavigationGroup = {
  label: string;
  items: FrontendNavigationItem[];
};

export type FrontendMetadata = {
  status: 'success';
  environments: JsonRecord;
  migration_profiles: JsonRecord;
  navigation: {
    groups: FrontendNavigationGroup[];
  };
  resolved_context: JsonRecord | null;
};

export type ResponseFilePreviewResponse = {
  status: 'planned';
  project: string;
  filename: string;
  lines: string[];
  migration_method: string;
};

export type ResponseFileWriteResponse = {
  status: 'success';
  message: string;
  project: string;
  path: string;
  line_count: number;
  sha256: string;
  migration_method: string;
};

export type SavedJobRunType = 'EVAL' | 'MIGRATE';

export type SavedJobRecord = {
  name: string;
  project: string;
  run_type: SavedJobRunType;
  rsp: string | null;
  job_parameters: JsonRecord;
  advisor_mode: string | null;
  flow_control: string | null;
  flow_phase: string | null;
  genfixup: string | null;
  ignore: string[] | null;
  schedule: string | null;
  listphases: boolean | null;
  custom_args: string[] | null;
};

export type SavedJobSaveResponse = {
  status: 'success';
  message: string;
  job: SavedJobRecord;
};

export type RunJobResponse =
  | {
    status: 'planned';
    script_path: string;
    command: string[];
    dry_run: true;
  }
  | {
    status: 'submitted';
    script_path: string;
    output: string;
    command: string[];
    job_id: string | null;
  };

function contractError(endpoint: string, detail: string): Error {
  return new Error(`${endpoint} API contract error: ${detail}`);
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, endpoint: string, label: string): JsonRecord {
  if (!isRecord(value)) {
    throw contractError(endpoint, `${label} must be an object.`);
  }
  return value;
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function requireNonEmptyString(
  record: JsonRecord,
  endpoint: string,
  label: string,
  key: string,
) {
  if (!isNonEmptyString(record[key])) {
    throw contractError(endpoint, `${label}.${key} must be a non-empty string.`);
  }
}

function exactTopLevelKeys(
  record: JsonRecord,
  endpoint: string,
  expectedKeys: string[],
) {
  const actualKeys = Object.keys(record).sort();
  const sortedExpectedKeys = [...expectedKeys].sort();
  if (
    actualKeys.length !== sortedExpectedKeys.length
    || actualKeys.some((key, index) => key !== sortedExpectedKeys[index])
  ) {
    throw contractError(
      endpoint,
      `expected exact top-level keys: ${sortedExpectedKeys.join(', ')}.`,
    );
  }
}

function allowedKeys(
  record: JsonRecord,
  endpoint: string,
  label: string,
  requiredKeys: string[],
  optionalKeys: string[] = [],
) {
  const keys = new Set(Object.keys(record));
  const missing = requiredKeys.filter((key) => !keys.has(key));
  const allowed = new Set([...requiredKeys, ...optionalKeys]);
  const extra = [...keys].filter((key) => !allowed.has(key)).sort();
  const details = [];
  if (missing.length > 0) details.push(`missing ${missing.sort().join(', ')}`);
  if (extra.length > 0) details.push(`unexpected ${extra.join(', ')}`);
  if (details.length > 0) {
    throw contractError(endpoint, `${label} has invalid fields (${details.join('; ')}).`);
  }
}

function isAppPath(value: unknown): value is string {
  return typeof value === 'string' && /^\/[A-Za-z0-9][A-Za-z0-9/_-]*$/.test(value);
}

function isResponseFileName(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.rsp$/.test(value);
}

function canonicalSavedJobName(project: string, runType: SavedJobRunType): string {
  return `${project}_${runType.toLowerCase()}`;
}

function requireStringOrNull(
  record: JsonRecord,
  endpoint: string,
  label: string,
  key: string,
) {
  if (record[key] !== null && typeof record[key] !== 'string') {
    throw contractError(endpoint, `${label}.${key} must be a string or null.`);
  }
}

function requireStringArrayOrNull(
  record: JsonRecord,
  endpoint: string,
  label: string,
  key: string,
) {
  const value = record[key];
  if (
    value !== null
    && (!Array.isArray(value) || !value.every((item) => typeof item === 'string'))
  ) {
    throw contractError(endpoint, `${label}.${key} must be an array of strings or null.`);
  }
}

function validateSavedJobRecord(
  value: unknown,
  endpoint: string,
  label: string,
  expectedName?: string,
): SavedJobRecord {
  const record = requireRecord(value, endpoint, label);
  exactTopLevelKeys(record, endpoint, [
    'name',
    'project',
    'run_type',
    'rsp',
    'job_parameters',
    'advisor_mode',
    'flow_control',
    'flow_phase',
    'genfixup',
    'ignore',
    'schedule',
    'listphases',
    'custom_args',
  ]);
  requireNonEmptyString(record, endpoint, label, 'name');
  requireNonEmptyString(record, endpoint, label, 'project');
  if (record.run_type !== 'EVAL' && record.run_type !== 'MIGRATE') {
    throw contractError(endpoint, `${label}.run_type must be EVAL or MIGRATE.`);
  }
  if (expectedName !== undefined && record.name !== expectedName) {
    throw contractError(endpoint, `${label}.name must match expected name.`);
  }
  const project = record.project as string;
  const runType = record.run_type as SavedJobRunType;
  if (record.name !== canonicalSavedJobName(project, runType)) {
    throw contractError(endpoint, `${label}.name must match project and run_type.`);
  }
  requireStringOrNull(record, endpoint, label, 'rsp');
  if (!isRecord(record.job_parameters)) {
    throw contractError(endpoint, `${label}.job_parameters must be an object.`);
  }
  for (const key of ['advisor_mode', 'flow_control', 'flow_phase', 'genfixup', 'schedule'] as const) {
    requireStringOrNull(record, endpoint, label, key);
  }
  requireStringArrayOrNull(record, endpoint, label, 'ignore');
  requireStringArrayOrNull(record, endpoint, label, 'custom_args');
  if (record.listphases !== null && typeof record.listphases !== 'boolean') {
    throw contractError(endpoint, `${label}.listphases must be a boolean or null.`);
  }
  return record as SavedJobRecord;
}

function validateProjectRecord(
  value: unknown,
  endpoint: string,
  label: string,
): ProjectRecord {
  const record = requireRecord(value, endpoint, label);
  allowedKeys(
    record,
    endpoint,
    label,
    ['name', 'rsp', 'source_connection', 'target_connection'],
    ['migration_method', 'jobs'],
  );

  requireNonEmptyString(record, endpoint, label, 'name');
  requireNonEmptyString(record, endpoint, label, 'source_connection');
  requireNonEmptyString(record, endpoint, label, 'target_connection');
  if (record.rsp !== null && typeof record.rsp !== 'string') {
    throw contractError(endpoint, `${label}.rsp must be a string or null.`);
  }
  if (
    record.migration_method !== undefined
    && typeof record.migration_method !== 'string'
  ) {
    throw contractError(
      endpoint,
      `${label}.migration_method must be a string when present.`,
    );
  }
  if (record.jobs !== undefined) {
    const jobs = requireRecord(record.jobs, endpoint, `${label}.jobs`);
    for (const [runType, jobIds] of Object.entries(jobs)) {
      if (runType.toLowerCase() !== 'eval' && runType.toLowerCase() !== 'migrate') {
        throw contractError(endpoint, `${label}.jobs has unsupported run type ${runType}.`);
      }
      if (!Array.isArray(jobIds) || !jobIds.every((jobId) => typeof jobId === 'string')) {
        throw contractError(endpoint, `${label}.jobs.${runType} must be a list of strings.`);
      }
    }
  }

  return record as ProjectRecord;
}

function validateDbConnectionRecord(
  value: unknown,
  endpoint: string,
  label: string,
): DbConnectionRecord {
  const record = requireRecord(value, endpoint, label);
  allowedKeys(
    record,
    endpoint,
    label,
    [
      'name',
      'host',
      'port',
      'service_name',
      'db_type',
      'connection_role',
      'protocol',
      'allow_tls_without_wallet',
    ],
    ['tls_wallet_uploaded_dir'],
  );

  for (const field of ['name', 'host', 'service_name', 'db_type'] as const) {
    requireNonEmptyString(record, endpoint, label, field);
  }
  if (!Number.isInteger(record.port)) {
    throw contractError(endpoint, `${label}.port must be an integer.`);
  }
  if (record.connection_role !== 'source' && record.connection_role !== 'target') {
    throw contractError(endpoint, `${label}.connection_role must be source or target.`);
  }
  if (record.protocol !== 'TCP' && record.protocol !== 'TCPS') {
    throw contractError(endpoint, `${label}.protocol must be TCP or TCPS.`);
  }
  if (typeof record.allow_tls_without_wallet !== 'boolean') {
    throw contractError(endpoint, `${label}.allow_tls_without_wallet must be a boolean.`);
  }
  if (
    record.tls_wallet_uploaded_dir !== undefined
    && typeof record.tls_wallet_uploaded_dir !== 'string'
  ) {
    throw contractError(endpoint, `${label}.tls_wallet_uploaded_dir must be a string when present.`);
  }

  return record as DbConnectionRecord;
}

export function validateProjectsResponse(
  payload: unknown,
): Record<string, ProjectRecord> {
  const endpoint = 'GET /projects';
  const records = requireRecord(payload, endpoint, 'response');

  for (const [key, value] of Object.entries(records)) {
    const record = validateProjectRecord(value, endpoint, `project "${key}"`);

    if (record.name !== key) {
      throw contractError(endpoint, `project "${key}" name must match object key.`);
    }
  }

  return records as Record<string, ProjectRecord>;
}

export function validateProjectWriteResponse(
  payload: unknown,
  expectedName?: string,
  endpoint = 'POST /projects',
): ProjectWriteResponse {
  const response = requireRecord(payload, endpoint, 'response');
  allowedKeys(response, endpoint, 'response', ['status', 'message', 'project']);
  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  requireNonEmptyString(response, endpoint, 'response', 'message');
  const project = validateProjectRecord(response.project, endpoint, 'project');
  if (expectedName !== undefined && project.name !== expectedName) {
    throw contractError(endpoint, 'project.name must match expected name.');
  }
  return response as ProjectWriteResponse;
}

export function validateDbConnectionsResponse(
  payload: unknown,
): Record<string, DbConnectionRecord> {
  const endpoint = 'GET /dbconnections';
  const records = requireRecord(payload, endpoint, 'response');

  for (const [key, value] of Object.entries(records)) {
    const record = validateDbConnectionRecord(value, endpoint, `db connection "${key}"`);

    if (record.name !== key) {
      throw contractError(
        endpoint,
        `db connection "${key}" name must match object key.`,
      );
    }
  }

  return records as Record<string, DbConnectionRecord>;
}

export function validateDbConnectionWriteResponse(
  payload: unknown,
  expectedName?: string,
  endpoint = 'POST /dbconnections',
): DbConnectionWriteResponse {
  const response = requireRecord(payload, endpoint, 'response');
  allowedKeys(response, endpoint, 'response', ['status', 'message', 'connection']);
  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  requireNonEmptyString(response, endpoint, 'response', 'message');
  const connection = validateDbConnectionRecord(response.connection, endpoint, 'connection');
  if (expectedName !== undefined && connection.name !== expectedName) {
    throw contractError(endpoint, 'connection.name must match expected name.');
  }
  return response as DbConnectionWriteResponse;
}

export function validateCredentialWalletsResponse(
  payload: unknown,
): CredentialWalletsResponse {
  const endpoint = 'GET /credential-wallets';
  const response = requireRecord(payload, endpoint, 'response');
  exactTopLevelKeys(response, endpoint, ['wallets']);
  if (!Array.isArray(response.wallets)) {
    throw contractError(endpoint, 'wallets must be an array.');
  }
  response.wallets.forEach((rawWallet, index) => {
    const label = `wallets[${index}]`;
    const wallet = requireRecord(rawWallet, endpoint, label);
    allowedKeys(wallet, endpoint, label, ['name', 'path', 'credential_username']);
    requireNonEmptyString(wallet, endpoint, label, 'name');
    requireNonEmptyString(wallet, endpoint, label, 'path');
    if (
      wallet.credential_username !== null
      && typeof wallet.credential_username !== 'string'
    ) {
      throw contractError(endpoint, `${label}.credential_username must be a string or null.`);
    }
  });
  return response as CredentialWalletsResponse;
}

export function validateWalletCommandResponse(
  payload: unknown,
  endpoint: string,
): WalletCommandResponse {
  const response = requireRecord(payload, endpoint, 'response');
  allowedKeys(response, endpoint, 'response', ['status', 'output']);
  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  if (typeof response.output !== 'string') {
    throw contractError(endpoint, 'output must be a string.');
  }
  return response as WalletCommandResponse;
}

export function validateTlsWalletUploadResponse(
  payload: unknown,
): TlsWalletUploadResponse {
  const endpoint = 'POST /dbconnections/{name}/tls-wallet';
  const response = requireRecord(payload, endpoint, 'response');
  allowedKeys(response, endpoint, 'response', ['status', 'message', 'path', 'wallet_dir']);
  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  for (const field of ['message', 'path', 'wallet_dir'] as const) {
    requireNonEmptyString(response, endpoint, 'response', field);
  }
  return response as TlsWalletUploadResponse;
}

export function validateDiscoveryResponse(payload: unknown): JsonRecord {
  const endpoint = 'POST /dbconnections/discover';
  const response = requireRecord(payload, endpoint, 'response');
  allowedKeys(response, endpoint, 'response', ['status', 'message', 'snapshot']);
  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  requireNonEmptyString(response, endpoint, 'response', 'message');
  if (!isRecord(response.snapshot)) {
    throw contractError(endpoint, 'snapshot must be an object.');
  }
  return response.snapshot;
}

export function validateDiscoveryLatestResponse(payload: unknown): JsonRecord | null {
  const endpoint = 'GET /dbconnections/{name}/discovery/latest';
  const response = requireRecord(payload, endpoint, 'response');
  if (response.status === 'not_found') {
    exactTopLevelKeys(response, endpoint, ['status']);
    return null;
  }
  allowedKeys(response, endpoint, 'response', ['status', 'file', 'snapshot']);
  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  requireNonEmptyString(response, endpoint, 'response', 'file');
  if (!isRecord(response.snapshot)) {
    throw contractError(endpoint, 'snapshot must be an object.');
  }
  return response.snapshot;
}

export function validateJobsDashboardResponse(
  payload: unknown,
): JobsDashboardResponse {
  const endpoint = 'GET /jobs';
  const response = requireRecord(payload, endpoint, 'response');
  exactTopLevelKeys(response, endpoint, [
    'status',
    'source',
    'last_refreshed',
    'jobs',
    'warnings',
  ]);

  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  if (typeof response.source !== 'string') {
    throw contractError(endpoint, 'source must be a string.');
  }
  if (
    response.last_refreshed !== null
    && typeof response.last_refreshed !== 'string'
  ) {
    throw contractError(endpoint, 'last_refreshed must be a string or null.');
  }
  if (!Array.isArray(response.warnings)) {
    throw contractError(endpoint, 'warnings must be an array.');
  }
  if (!Array.isArray(response.jobs)) {
    throw contractError(endpoint, 'jobs must be an array.');
  }

  response.jobs.forEach((jobRow, index) => {
    const row = requireRecord(jobRow, endpoint, `jobs[${index}]`);
    exactTopLevelKeys(row, endpoint, ['job', 'inventory']);
    if (!isRecord(row.job) || !isRecord(row.inventory)) {
      throw contractError(
        endpoint,
        `jobs[${index}] must be an enriched record with job object and inventory object.`,
      );
    }
  });

  return response as JobsDashboardResponse;
}

export function validateJobIdsResponse(payload: unknown): JobIdsResponse {
  const endpoint = 'GET /jobs/ids';
  const response = requireRecord(payload, endpoint, 'response');
  exactTopLevelKeys(response, endpoint, ['job_ids']);
  if (
    !Array.isArray(response.job_ids)
    || !response.job_ids.every((jobId) => typeof jobId === 'string')
  ) {
    throw contractError(endpoint, 'job_ids must be an array of strings.');
  }
  return response as JobIdsResponse;
}

export function validateJobQueryResponse(payload: unknown): JobQueryResponse {
  const endpoint = 'GET /jobs/{jobid}';
  const response = requireRecord(payload, endpoint, 'response');
  exactTopLevelKeys(response, endpoint, ['status', 'output']);
  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  if (typeof response.output !== 'string') {
    throw contractError(endpoint, 'output must be a string.');
  }
  return response as JobQueryResponse;
}

export function validateJoblogsResponse(
  payload: unknown,
  expectedJobId: string,
): JoblogsResponse {
  const endpoint = 'GET /joblogs';
  const response = requireRecord(payload, endpoint, 'response');
  exactTopLevelKeys(response, endpoint, ['status', 'job_id', 'logs']);
  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  if (response.job_id !== expectedJobId) {
    throw contractError(endpoint, 'job_id must match requested job ID.');
  }
  if (!Array.isArray(response.logs)) {
    throw contractError(endpoint, 'logs must be an array.');
  }
  response.logs.forEach((item, index) => {
    const log = requireRecord(item, endpoint, `logs[${index}]`);
    exactTopLevelKeys(log, endpoint, ['name', 'size_bytes', 'modified_time']);
    requireNonEmptyString(log, endpoint, `logs[${index}]`, 'name');
    if (
      typeof log.size_bytes !== 'number'
      || !Number.isInteger(log.size_bytes)
      || log.size_bytes < 0
    ) {
      throw contractError(endpoint, `logs[${index}].size_bytes must be a non-negative integer.`);
    }
    requireNonEmptyString(log, endpoint, `logs[${index}]`, 'modified_time');
  });
  return response as JoblogsResponse;
}

export function validateJoblogReadResponse(
  payload: unknown,
  expectedJobId: string,
  expectedName: string,
): JoblogReadResponse {
  const endpoint = 'POST /joblogs/read';
  const response = requireRecord(payload, endpoint, 'response');
  exactTopLevelKeys(response, endpoint, ['status', 'job_id', 'name', 'content']);
  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  if (response.job_id !== expectedJobId) {
    throw contractError(endpoint, 'job_id must match requested job ID.');
  }
  if (response.name !== expectedName) {
    throw contractError(endpoint, 'name must match requested log name.');
  }
  if (typeof response.content !== 'string') {
    throw contractError(endpoint, 'content must be a string.');
  }
  return response as JoblogReadResponse;
}

export function validateSavedJobsResponse(
  payload: unknown,
): Record<string, SavedJobRecord> {
  const endpoint = 'GET /saved-jobs';
  const response = requireRecord(payload, endpoint, 'response');
  for (const [key, value] of Object.entries(response)) {
    const record = validateSavedJobRecord(value, endpoint, `saved job "${key}"`);
    if (record.name !== key) {
      throw contractError(endpoint, `saved job "${key}" name must match object key.`);
    }
  }
  return response as Record<string, SavedJobRecord>;
}

export function validateSavedJobSaveResponse(
  payload: unknown,
  expectedName: string,
): SavedJobSaveResponse {
  const endpoint = 'POST /saved-jobs';
  const response = requireRecord(payload, endpoint, 'response');
  exactTopLevelKeys(response, endpoint, ['status', 'message', 'job']);
  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  requireNonEmptyString(response, endpoint, 'response', 'message');
  validateSavedJobRecord(response.job, endpoint, 'job', expectedName);
  return response as SavedJobSaveResponse;
}

export function validateRunJobResponse(
  payload: unknown,
  options: { dryRun: boolean },
): RunJobResponse {
  const endpoint = 'POST /jobs';
  const response = requireRecord(payload, endpoint, 'response');
  if (options.dryRun) {
    exactTopLevelKeys(response, endpoint, ['status', 'script_path', 'command', 'dry_run']);
    if (response.status !== 'planned') {
      throw contractError(endpoint, 'status must be planned.');
    }
    if (response.dry_run !== true) {
      throw contractError(endpoint, 'dry_run must be true.');
    }
  } else {
    exactTopLevelKeys(response, endpoint, ['status', 'script_path', 'output', 'command', 'job_id']);
    if (response.status !== 'submitted') {
      throw contractError(endpoint, 'status must be submitted.');
    }
    if (typeof response.output !== 'string') {
      throw contractError(endpoint, 'output must be a string.');
    }
    if (response.job_id !== null && typeof response.job_id !== 'string') {
      throw contractError(endpoint, 'job_id must be a string or null.');
    }
  }
  requireNonEmptyString(response, endpoint, 'response', 'script_path');
  if (!Array.isArray(response.command) || !response.command.every((line) => typeof line === 'string')) {
    throw contractError(endpoint, 'command must be an array of strings.');
  }
  return response as RunJobResponse;
}

export function validateFrontendMetadata(payload: unknown): FrontendMetadata {
  const endpoint = 'GET /metadata/frontend';
  const response = requireRecord(payload, endpoint, 'response');
  exactTopLevelKeys(response, endpoint, [
    'status',
    'environments',
    'migration_profiles',
    'navigation',
    'resolved_context',
  ]);

  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  if (!isRecord(response.environments)) {
    throw contractError(endpoint, 'environments must be an object.');
  }
  if (!isRecord(response.migration_profiles)) {
    throw contractError(endpoint, 'migration_profiles must be an object.');
  }

  const navigation = requireRecord(response.navigation, endpoint, 'navigation');
  allowedKeys(navigation, endpoint, 'navigation', ['groups']);
  if (!Array.isArray(navigation.groups)) {
    throw contractError(endpoint, 'navigation.groups must be an array.');
  }
  navigation.groups.forEach((rawGroup, groupIndex) => {
    const groupLabel = `navigation.groups[${groupIndex}]`;
    const group = requireRecord(rawGroup, endpoint, groupLabel);
    allowedKeys(group, endpoint, groupLabel, ['label', 'items']);
    requireNonEmptyString(group, endpoint, groupLabel, 'label');
    if (!Array.isArray(group.items) || group.items.length === 0) {
      throw contractError(endpoint, `${groupLabel}.items must be a non-empty array.`);
    }
    group.items.forEach((rawItem, itemIndex) => {
      const itemLabel = `${groupLabel}.items[${itemIndex}]`;
      const item = requireRecord(rawItem, endpoint, itemLabel);
      allowedKeys(item, endpoint, itemLabel, ['label', 'section', 'path']);
      requireNonEmptyString(item, endpoint, itemLabel, 'label');
      requireNonEmptyString(item, endpoint, itemLabel, 'section');
      if (!isAppPath(item.path)) {
        throw contractError(endpoint, `${itemLabel}.path must be an app path.`);
      }
    });
  });
  if (
    response.resolved_context !== null
    && !isRecord(response.resolved_context)
  ) {
    throw contractError(endpoint, 'resolved_context must be an object or null.');
  }

  return response as FrontendMetadata;
}

export function validateResponseFilePreviewResponse(
  payload: unknown,
  expectedProject: string,
  expectedMethod: string,
): ResponseFilePreviewResponse {
  const endpoint = 'POST /responsefiles/preview';
  const response = requireRecord(payload, endpoint, 'response');
  exactTopLevelKeys(response, endpoint, [
    'status',
    'project',
    'filename',
    'lines',
    'migration_method',
  ]);

  if (response.status !== 'planned') {
    throw contractError(endpoint, 'status must be planned.');
  }
  requireNonEmptyString(response, endpoint, 'response', 'project');
  if (response.project !== expectedProject) {
    throw contractError(endpoint, 'project must match expected project.');
  }
  if (!isResponseFileName(response.filename)) {
    throw contractError(endpoint, 'filename must be a response file name.');
  }
  if (!Array.isArray(response.lines) || !response.lines.every((line) => typeof line === 'string')) {
    throw contractError(endpoint, 'lines must be an array of strings.');
  }
  requireNonEmptyString(response, endpoint, 'response', 'migration_method');
  if (response.migration_method !== expectedMethod) {
    throw contractError(endpoint, 'migration_method must match expected method.');
  }

  return response as ResponseFilePreviewResponse;
}

export function validateResponseFileWriteResponse(
  payload: unknown,
  expectedProject: string,
  expectedMethod: string,
): ResponseFileWriteResponse {
  const endpoint = 'POST /responsefiles';
  const response = requireRecord(payload, endpoint, 'response');
  allowedKeys(response, endpoint, 'response', [
    'status',
    'message',
    'project',
    'path',
    'line_count',
    'sha256',
    'migration_method',
  ]);

  if (response.status !== 'success') {
    throw contractError(endpoint, 'status must be success.');
  }
  requireNonEmptyString(response, endpoint, 'response', 'message');
  requireNonEmptyString(response, endpoint, 'response', 'project');
  if (response.project !== expectedProject) {
    throw contractError(endpoint, 'project must match expected project.');
  }
  requireNonEmptyString(response, endpoint, 'response', 'path');
  if (
    typeof response.line_count !== 'number'
    || !Number.isInteger(response.line_count)
    || response.line_count < 1
  ) {
    throw contractError(endpoint, 'line_count must be a positive integer.');
  }
  if (typeof response.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(response.sha256)) {
    throw contractError(endpoint, 'sha256 must be 64 lowercase hex characters.');
  }
  requireNonEmptyString(response, endpoint, 'response', 'migration_method');
  if (response.migration_method !== expectedMethod) {
    throw contractError(endpoint, 'migration_method must match expected method.');
  }

  return response as ResponseFileWriteResponse;
}
