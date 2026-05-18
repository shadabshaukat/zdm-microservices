import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, type ApiSettings } from '../api/client';
import {
  type FrontendMetadata,
  type JsonRecord,
  type ProjectRecord,
  type ResponseFilePreviewResponse,
  validateFrontendMetadata,
  validateProjectsResponse,
  validateResponseFilePreviewResponse,
  validateResponseFileWriteResponse,
} from '../api/contracts';
import { buildResponseFileRequest } from '../api/payloads';
import { Alert } from '../components/Alert';
import { Button } from '../components/Button';
import { CodeBlock } from '../components/CodeBlock';
import { Field } from '../components/Field';
import { Select } from '../components/Select';

type ResponseFilesPageProps = {
  settings: ApiSettings;
};

type MediaOption = {
  value: string;
  label: string;
  enabled: boolean;
  disabled_reason: string;
  guidance: string;
};

type ResolvedResponseContext = {
  visibleResponseFields: string[];
  requiredResponseFields: string[];
  derivedResponseValues: JsonRecord;
  mediaOptions: MediaOption[];
  additionalDefaultRows: AdditionalDefaultRow[];
};

type ResponseFieldConfig = {
  label: string;
  control: string;
  options?: string[];
  default?: unknown;
};

type AdditionalDefaultRow = {
  key: string;
  value: string;
};

const DEFAULT_MIGRATION_METHOD = 'OFFLINE_LOGICAL';
const DEFAULT_MEDIUM = 'OSS';

export function ResponseFilesPage({ settings }: ResponseFilesPageProps) {
  const [metadata, setMetadata] = useState<FrontendMetadata | null>(null);
  const [projects, setProjects] = useState<Record<string, ProjectRecord>>({});
  const [selectedProject, setSelectedProject] = useState('');
  const [migrationMethod, setMigrationMethod] = useState(DEFAULT_MIGRATION_METHOD);
  const [medium, setMedium] = useState(DEFAULT_MEDIUM);
  const [resolvedContext, setResolvedContext] = useState<ResolvedResponseContext | null>(null);
  const [fieldConfigs, setFieldConfigs] = useState<Record<string, ResponseFieldConfig>>({});
  const [values, setValues] = useState<Record<string, string>>({});
  const [remapText, setRemapText] = useState('');
  const [additionalText, setAdditionalText] = useState('');
  const [preview, setPreview] = useState<ResponseFilePreviewResponse | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState(false);
  const [working, setWorking] = useState(false);
  const loadRequestRef = useRef(0);
  const resolveRequestRef = useRef(0);
  const submitRequestRef = useRef(0);

  const loadInitialData = useCallback(async () => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setLoading(true);
    setError('');
    try {
      const [metadataPayload, projectsPayload] = await Promise.all([
        apiFetch(settings, '/metadata/frontend'),
        apiFetch(settings, '/projects'),
      ]);
      if (requestId !== loadRequestRef.current) return;

      const nextMetadata = validateFrontendMetadata(metadataPayload);
      const nextProjects = validateProjectsResponse(projectsPayload);
      const firstProject = Object.keys(nextProjects).sort()[0] || '';
      const nextMethod = nextProjects[firstProject]?.migration_method || DEFAULT_MIGRATION_METHOD;

      setMetadata(nextMetadata);
      setProjects(nextProjects);
      setSelectedProject(firstProject);
      setMigrationMethod(nextMethod);
      setMedium(defaultMediumForMethod(nextMetadata, nextMethod));
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      setError(err instanceof Error ? err.message : 'Response file data could not be loaded.');
      setMetadata(null);
      setProjects({});
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, [settings]);

  useEffect(() => {
    void loadInitialData();
    return () => {
      loadRequestRef.current += 1;
    };
  }, [loadInitialData]);

  useEffect(() => {
    if (!selectedProject || !migrationMethod || !medium) {
      setResolvedContext(null);
      setFieldConfigs({});
      return;
    }

    const requestId = resolveRequestRef.current + 1;
    resolveRequestRef.current = requestId;
    setResolving(true);
    setError('');

    async function loadResolvedMetadata() {
      try {
        const params = new URLSearchParams({
          project: selectedProject,
          migration_method: migrationMethod,
          medium,
        });
        const payload = await apiFetch(settings, `/metadata/frontend?${params.toString()}`);
        if (requestId !== resolveRequestRef.current) return;

        const nextMetadata = validateFrontendMetadata(payload);
        const nextContext = validateResolvedResponseContext(
          nextMetadata,
          selectedProject,
          migrationMethod,
          medium,
        );
        const nextFieldConfigs = validateResponseFieldConfigs(
          nextMetadata,
          migrationMethod,
          nextContext.visibleResponseFields.filter((field) =>
            !handledByDedicatedControl(field)
            && !isDerivedField(field, nextContext.derivedResponseValues)),
        );

        setResolvedContext(nextContext);
        setFieldConfigs(nextFieldConfigs);
        setValues((current) => valuesWithDefaults(current, nextContext, nextFieldConfigs));
        setAdditionalText(additionalRowsToText(nextContext.additionalDefaultRows));
      } catch (err) {
        if (requestId !== resolveRequestRef.current) return;
        setResolvedContext(null);
        setFieldConfigs({});
        setError(err instanceof Error ? err.message : 'Resolved response-file metadata was invalid.');
      } finally {
        if (requestId === resolveRequestRef.current) setResolving(false);
      }
    }

    void loadResolvedMetadata();

    return () => {
      resolveRequestRef.current += 1;
    };
  }, [medium, migrationMethod, selectedProject, settings]);

  const projectOptions = useMemo(
    () => Object.keys(projects).sort().map((name) => ({ value: name, label: name })),
    [projects],
  );

  const methodOptions = useMemo(() => {
    if (!metadata) return [{ value: DEFAULT_MIGRATION_METHOD, label: DEFAULT_MIGRATION_METHOD }];
    return Object.keys(metadata.migration_profiles)
      .sort()
      .map((method) => ({ value: method, label: method }));
  }, [metadata]);

  const mediaOptions = useMemo(() => {
    if (!resolvedContext) return [{ value: medium, label: medium }];
    return resolvedContext.mediaOptions.map((option) => ({
      value: option.value,
      label: option.label,
      disabled: !option.enabled,
    }));
  }, [medium, resolvedContext]);

  const selectedMediaOption = resolvedContext?.mediaOptions.find((option) => option.value === medium);
  const canSubmit = Boolean(
    selectedProject
    && migrationMethod
    && medium
    && resolvedContext
    && (!selectedMediaOption || selectedMediaOption.enabled)
    && !working
    && !resolving,
  );

  function changeProject(event: ChangeEvent<HTMLSelectElement>) {
    const projectName = event.target.value;
    const nextMethod = projects[projectName]?.migration_method || DEFAULT_MIGRATION_METHOD;
    setSelectedProject(projectName);
    setMigrationMethod(nextMethod);
    setMedium(defaultMediumForMethod(metadata, nextMethod));
    resetResponseState();
  }

  function changeMigrationMethod(event: ChangeEvent<HTMLSelectElement>) {
    const nextMethod = event.target.value;
    setMigrationMethod(nextMethod);
    setMedium(defaultMediumForMethod(metadata, nextMethod));
    resetResponseState();
  }

  function changeMedium(event: ChangeEvent<HTMLSelectElement>) {
    setMedium(event.target.value);
    resetResponseState();
  }

  function updateValue(field: string, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    resetResponseState();
  }

  async function previewResponseFile() {
    await submitResponseFile('preview');
  }

  async function saveResponseFile() {
    await submitResponseFile('save');
  }

  async function submitResponseFile(action: 'preview' | 'save') {
    const requestId = submitRequestRef.current + 1;
    submitRequestRef.current = requestId;
    setWorking(true);
    setNotice('');
    setError('');
    try {
      const request = buildResponseFileRequest({
        project: selectedProject,
        migrationMethod,
        medium,
        values: buildEditableValues(values, fieldConfigs, resolvedContext),
        remaps: parseRemaps(remapText),
        additional: parseAdditional(additionalText),
      });
      const payload = await apiFetch(settings, action === 'preview' ? '/responsefiles/preview' : '/responsefiles', {
        method: 'POST',
        body: JSON.stringify(request),
      });
      if (requestId !== submitRequestRef.current) return;
      if (action === 'preview') {
        const response = validateResponseFilePreviewResponse(payload, selectedProject, migrationMethod);
        setPreview(response);
        setNotice(`Preview planned for ${response.filename}.`);
      } else {
        const response = validateResponseFileWriteResponse(payload, selectedProject, migrationMethod);
        setNotice(response.message);
      }
    } catch (err) {
      if (requestId !== submitRequestRef.current) return;
      setError(err instanceof Error ? err.message : 'Response file request failed.');
    } finally {
      if (requestId === submitRequestRef.current) setWorking(false);
    }
  }

  function resetResponseState() {
    submitRequestRef.current += 1;
    setWorking(false);
    setPreview(null);
    setNotice('');
    setError('');
  }

  return (
    <section className="zeus-panel">
      <h2 className="page-title">ZDM Response Files</h2>
      <p className="page-caption">Build, preview, and save backend-rendered response files for a migration project.</p>

      <div className="response-grid">
        <div className="form-grid">
          <Select
            label="Project"
            required
            value={selectedProject}
            onChange={changeProject}
            options={[{ value: '', label: 'Select project' }, ...projectOptions]}
          />
          <Select
            label="Migration method"
            required
            value={migrationMethod}
            onChange={changeMigrationMethod}
            options={methodOptions}
          />
          <Select
            label="Data transfer medium"
            required
            value={medium}
            onChange={changeMedium}
            options={mediaOptions}
          />
          {selectedMediaOption?.guidance ? (
            <p className="empty-state">
              {selectedMediaOption.guidance}
            </p>
          ) : null}
          {resolvedContext?.mediaOptions
            .filter((option) => !option.enabled && option.disabled_reason)
            .map((option) => (
              <Alert key={option.value} tone="warning">
                {option.disabled_reason}
              </Alert>
            ))}
        </div>

        <div className="status-stack">
          {notice ? <Alert tone="success">{notice}</Alert> : null}
          {error ? <Alert tone="error">{error}</Alert> : null}
          {loading ? <p className="empty-state">Loading response file metadata...</p> : null}
          {resolving ? <p className="empty-state">Resolving project-specific fields...</p> : null}
        </div>
      </div>

      {resolvedContext ? (
        <>
          <h3>Response values</h3>
          <div className="response-grid">
            <div className="form-grid">
              {resolvedContext.visibleResponseFields
                .filter((field) =>
                  !handledByDedicatedControl(field)
                  && !isDerivedField(field, resolvedContext.derivedResponseValues))
                .map((field) => (
                  <ResponseValueField
                    key={field}
                    field={field}
                    config={fieldConfigs[field]}
                    required={resolvedContext.requiredResponseFields.includes(field)}
                    value={values[field] || ''}
                    onChange={updateValue}
                  />
                ))}
              <label className="field">
                <span>Metadata remaps</span>
                <textarea
                  rows={4}
                  value={remapText}
                  onChange={(event) => {
                    setRemapText(event.target.value);
                    resetResponseState();
                  }}
                  placeholder='[["REMAP_SCHEMA","APP","APP_NEW"]]'
                />
                <small>JSON array of remap rows; leave blank when not needed.</small>
              </label>
              <label className="field">
                <span>Additional parameters</span>
                <textarea
                  rows={4}
                  value={additionalText}
                  onChange={(event) => {
                    setAdditionalText(event.target.value);
                    resetResponseState();
                  }}
                  placeholder="RUNCPATREMOTELY=TRUE"
                />
                <small>One KEY=VALUE pair per line; leave blank when not needed.</small>
              </label>
              <div className="button-row">
                <Button type="button" variant="secondary" disabled={!canSubmit} onClick={previewResponseFile}>
                  {working ? 'Working...' : 'Preview'}
                </Button>
                <Button type="button" variant="primary" disabled={!canSubmit} onClick={saveResponseFile}>
                  {working ? 'Working...' : 'Save response file'}
                </Button>
              </div>
            </div>

            <div className="status-stack">
              <h3>Derived values</h3>
              {Object.keys(resolvedContext.derivedResponseValues).length > 0 ? (
                <CodeBlock value={JSON.stringify(resolvedContext.derivedResponseValues, null, 2)} />
              ) : (
                <p className="empty-state">No project-derived response values.</p>
              )}
              <h3>Preview</h3>
              {preview ? (
                <CodeBlock value={preview.lines.join('\n')} />
              ) : (
                <p className="empty-state">Previewed response lines will appear here.</p>
              )}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

type ResponseValueFieldProps = {
  field: string;
  config: ResponseFieldConfig;
  required: boolean;
  value: string;
  onChange: (field: string, value: string) => void;
};

function ResponseValueField({
  field,
  config,
  required,
  value,
  onChange,
}: ResponseValueFieldProps) {
  const label = `${config.label}${required ? ' *' : ''}`;
  if (config.control === 'select' && config.options) {
    return (
      <Select
        label={label}
        required={required}
        value={value}
        onChange={(event) => onChange(field, event.target.value)}
        options={[
          { value: '', label: 'Select value' },
          ...config.options.map((option) => ({ value: option, label: option })),
        ]}
      />
    );
  }

  if (config.control === 'include_schemas') {
    return (
      <Field
        label={label}
        required={required}
        value={value}
        onChange={(event) => onChange(field, event.target.value)}
        helper="Comma-separated schema names."
      />
    );
  }

  return (
    <Field
      label={label}
      required={required}
      type={config.control === 'number' ? 'number' : 'text'}
      value={value}
      onChange={(event) => onChange(field, event.target.value)}
    />
  );
}

function validateResolvedResponseContext(
  metadata: FrontendMetadata,
  expectedProject: string,
  expectedMethod: string,
  expectedMedium: string,
): ResolvedResponseContext {
  const context = requireRecord(metadata.resolved_context, 'resolved_context');
  exactKeys(context, 'resolved_context', [
    'project',
    'migration_method',
    'medium',
    'run_type',
    'decision_input_values',
    'derived_response_values',
    'media_options',
    'response_sections',
    'medium_sections',
    'visible_response_fields',
    'required_response_fields',
    'additional_default_rows',
    'job_sections',
  ]);
  requireMatchingString(context.project, 'resolved_context.project', expectedProject);
  requireMatchingString(context.migration_method, 'resolved_context.migration_method', expectedMethod);
  requireMatchingString(context.medium, 'resolved_context.medium', expectedMedium);
  requireString(context.run_type, 'resolved_context.run_type');
  requireRecord(context.decision_input_values, 'resolved_context.decision_input_values');
  requireRecord(context.response_sections, 'resolved_context.response_sections');
  requireRecord(context.medium_sections, 'resolved_context.medium_sections');
  requireRecord(context.job_sections, 'resolved_context.job_sections');

  return {
    visibleResponseFields: requireStringArray(context.visible_response_fields, 'visible_response_fields'),
    requiredResponseFields: requireStringArray(context.required_response_fields, 'required_response_fields'),
    derivedResponseValues: requireRecord(context.derived_response_values, 'derived_response_values'),
    mediaOptions: requireMediaOptions(context.media_options),
    additionalDefaultRows: requireAdditionalDefaultRows(context.additional_default_rows),
  };
}

function validateResponseFieldConfigs(
  metadata: FrontendMetadata,
  migrationMethod: string,
  visibleFields: string[],
): Record<string, ResponseFieldConfig> {
  const profile = requireRecord(metadata.migration_profiles[migrationMethod], `migration_profiles.${migrationMethod}`);
  const responseFile = requireRecord(profile.response_file, `migration_profiles.${migrationMethod}.response_file`);
  const rawFields = requireRecord(responseFile.fields, `migration_profiles.${migrationMethod}.response_file.fields`);
  const configs: Record<string, ResponseFieldConfig> = {};

  visibleFields
    .filter((field) => field !== 'MIGRATION_METHOD' && field !== 'DATA_TRANSFER_MEDIUM')
    .forEach((field) => {
      const rawConfig = requireRecord(rawFields[field], `response_file.fields.${field}`);
      const label = rawConfig.label;
      if (typeof label !== 'string' || label.trim() === '') {
        throw new Error(`GET /metadata/frontend API contract error: response_file.fields.${field}.label must be a non-empty string.`);
      }
      const control = typeof rawConfig.control === 'string' ? rawConfig.control : 'text';
      const config: ResponseFieldConfig = { label, control };
      if (rawConfig.default !== undefined) config.default = rawConfig.default;
      if (rawConfig.options !== undefined) {
        config.options = requireStringArray(rawConfig.options, `response_file.fields.${field}.options`);
      }
      configs[field] = config;
    });

  return configs;
}

function valuesWithDefaults(
  current: Record<string, string>,
  context: ResolvedResponseContext,
  configs: Record<string, ResponseFieldConfig>,
): Record<string, string> {
  const next: Record<string, string> = {};
  const derivedKeys = new Set(Object.keys(context.derivedResponseValues));

  for (const field of context.visibleResponseFields) {
    if (handledByDedicatedControl(field) || derivedKeys.has(field)) {
      continue;
    }
    const existing = current[field];
    const fallback = configs[field]?.default;
    next[field] = existing !== undefined ? existing : fallback === undefined ? '' : String(fallback);
  }

  return next;
}

function buildEditableValues(
  current: Record<string, string>,
  configs: Record<string, ResponseFieldConfig>,
  context: ResolvedResponseContext | null,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const derivedKeys = new Set(Object.keys(context?.derivedResponseValues || {}));

  for (const [field, value] of Object.entries(current)) {
    if (handledByDedicatedControl(field) || derivedKeys.has(field) || value.trim() === '') continue;
    if (configs[field]?.control === 'include_schemas') {
      const schemas = value.split(',').map((item) => item.trim()).filter(Boolean);
      if (schemas.length > 0) out.include_schemas = schemas;
      continue;
    }
    out[field] = value;
  }

  return out;
}

function parseRemaps(value: string): unknown[][] {
  const trimmed = value.trim();
  if (!trimmed) return [];
  const parsed = JSON.parse(trimmed) as unknown;
  if (!Array.isArray(parsed) || !parsed.every((row) => Array.isArray(row))) {
    throw new Error('Metadata remaps must be a JSON array of arrays.');
  }
  return parsed;
}

function handledByDedicatedControl(field: string): boolean {
  return (
    field === 'MIGRATION_METHOD'
    || field === 'DATA_TRANSFER_MEDIUM'
    || field === 'DATAPUMPSETTINGS_METADATAREMAPS'
  );
}

function isDerivedField(field: string, derivedValues: JsonRecord): boolean {
  return Object.prototype.hasOwnProperty.call(derivedValues, field);
}

function parseAdditional(value: string): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [index, line] of value.split(/\r?\n/).entries()) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const separatorIndex = trimmed.indexOf('=');
    if (separatorIndex <= 0) {
      throw new Error(`Additional parameter line ${index + 1} must use KEY=VALUE.`);
    }
    const key = trimmed.slice(0, separatorIndex).trim();
    const lineValue = trimmed.slice(separatorIndex + 1).trim();
    if (!key) throw new Error(`Additional parameter line ${index + 1} is missing a key.`);
    out[key] = lineValue;
  }
  return out;
}

function additionalRowsToText(rows: AdditionalDefaultRow[]): string {
  return rows
    .filter((row) => row.key.trim() || row.value.trim())
    .map((row) => `${row.key}=${row.value}`)
    .join('\n');
}

function requireRecord(value: unknown, label: string): JsonRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`GET /metadata/frontend API contract error: ${label} must be an object.`);
  }
  return value as JsonRecord;
}

function exactKeys(record: JsonRecord, label: string, expectedKeys: string[]) {
  const actualKeys = Object.keys(record).sort();
  const sortedExpectedKeys = [...expectedKeys].sort();
  if (
    actualKeys.length !== sortedExpectedKeys.length
    || actualKeys.some((key, index) => key !== sortedExpectedKeys[index])
  ) {
    throw new Error(
      `GET /metadata/frontend API contract error: ${label} expected exact keys: ${sortedExpectedKeys.join(', ')}.`,
    );
  }
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== 'string') {
    throw new Error(`GET /metadata/frontend API contract error: ${label} must be a string.`);
  }
  return value;
}

function requireMatchingString(value: unknown, label: string, expected: string) {
  const actual = requireString(value, label);
  if (actual !== expected) {
    throw new Error(`GET /metadata/frontend API contract error: ${label} must match requested ${label.split('.').pop()}.`);
  }
}

function requireStringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new Error(`GET /metadata/frontend API contract error: ${label} must be an array of strings.`);
  }
  return value;
}

function requireAdditionalDefaultRows(value: unknown): AdditionalDefaultRow[] {
  if (!Array.isArray(value)) {
    throw new Error('GET /metadata/frontend API contract error: additional_default_rows must be an array.');
  }
  return value.map((item, index) => {
    const row = requireRecord(item, `additional_default_rows[${index}]`);
    exactKeys(row, `additional_default_rows[${index}]`, ['key', 'value']);
    if (typeof row.key !== 'string' || typeof row.value !== 'string') {
      throw new Error(`GET /metadata/frontend API contract error: additional_default_rows[${index}] key and value must be strings.`);
    }
    return { key: row.key, value: row.value };
  });
}

function requireMediaOptions(value: unknown): MediaOption[] {
  if (!Array.isArray(value)) {
    throw new Error('GET /metadata/frontend API contract error: media_options must be an array.');
  }
  return value.map((item, index) => {
    const option = requireRecord(item, `media_options[${index}]`);
    for (const key of ['value', 'label', 'disabled_reason', 'guidance'] as const) {
      if (typeof option[key] !== 'string') {
        throw new Error(`GET /metadata/frontend API contract error: media_options[${index}].${key} must be a string.`);
      }
    }
    if (typeof option.enabled !== 'boolean') {
      throw new Error(`GET /metadata/frontend API contract error: media_options[${index}].enabled must be a boolean.`);
    }
    return option as MediaOption;
  });
}

function defaultMediumForMethod(metadata: FrontendMetadata | null, migrationMethod: string): string {
  if (!metadata) return DEFAULT_MEDIUM;
  const profile = metadata.migration_profiles[migrationMethod];
  if (typeof profile !== 'object' || profile === null || Array.isArray(profile)) return DEFAULT_MEDIUM;
  const defaultMedium = (profile as JsonRecord).default_medium;
  return typeof defaultMedium === 'string' && defaultMedium.trim() ? defaultMedium : DEFAULT_MEDIUM;
}
