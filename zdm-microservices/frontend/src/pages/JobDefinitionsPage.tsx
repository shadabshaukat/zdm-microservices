import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, type ApiSettings } from '../api/client';
import {
  type FrontendMetadata,
  type JsonRecord,
  type ProjectRecord,
  type SavedJobRecord,
  validateFrontendMetadata,
  validateProjectsResponse,
  validateSavedJobSaveResponse,
  validateSavedJobsResponse,
} from '../api/contracts';
import { buildSavedJobRequest, type SavedJobRunType } from '../api/payloads';
import { Alert } from '../components/Alert';
import { Button } from '../components/Button';
import { Field } from '../components/Field';
import { Select } from '../components/Select';
import { Table } from '../components/Table';

type JobDefinitionsPageProps = {
  settings: ApiSettings;
};

const defaultMethod = 'OFFLINE_LOGICAL';
const runTypes: SavedJobRunType[] = ['EVAL', 'MIGRATE'];

type RunControlState = {
  advisor_mode: string;
  flow_control: string;
  flow_phase: string;
  genfixup: string;
  ignore: string[];
  schedule: string;
  listphases: boolean;
  custom_args: string;
};

type RunControlName = keyof RunControlState;

const defaultControls: RunControlState = {
  advisor_mode: 'NONE',
  flow_control: 'NONE',
  flow_phase: '',
  genfixup: '',
  ignore: [],
  schedule: '',
  listphases: false,
  custom_args: '',
};

export function JobDefinitionsPage({ settings }: JobDefinitionsPageProps) {
  const [metadata, setMetadata] = useState<FrontendMetadata | null>(null);
  const [projects, setProjects] = useState<Record<string, ProjectRecord>>({});
  const [savedJobs, setSavedJobs] = useState<Record<string, SavedJobRecord>>({});
  const [project, setProject] = useState('');
  const [runType, setRunType] = useState<SavedJobRunType>('EVAL');
  const [jobParameters, setJobParameters] = useState<Record<string, string>>({});
  const [controls, setControls] = useState<RunControlState>(defaultControls);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const loadRequestRef = useRef(0);
  const selectedProjectRef = useRef('');

  const loadData = useCallback(async () => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setLoading(true);
    setError('');
    try {
      const [metadataPayload, projectsPayload, savedJobsPayload] = await Promise.all([
        apiFetch(settings, '/metadata/frontend'),
        apiFetch(settings, '/projects'),
        apiFetch(settings, '/saved-jobs'),
      ]);
      if (requestId !== loadRequestRef.current) return;
      const nextMetadata = validateFrontendMetadata(metadataPayload);
      const nextProjects = validateProjectsResponse(projectsPayload);
      const currentProject = selectedProjectRef.current;
      const nextProject = currentProject && Object.prototype.hasOwnProperty.call(nextProjects, currentProject)
        ? currentProject
        : Object.keys(nextProjects).sort()[0] || '';
      setMetadata(nextMetadata);
      setProjects(nextProjects);
      setSavedJobs(validateSavedJobsResponse(savedJobsPayload));
      updateSelectedProject(nextProject);
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      setError(err instanceof Error ? err.message : 'Job definition data could not be loaded.');
      setMetadata(null);
      setProjects({});
      setSavedJobs({});
      updateSelectedProject('');
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, [settings]);

  useEffect(() => {
    void loadData();
    return () => {
      loadRequestRef.current += 1;
    };
  }, [loadData]);

  const migrationMethod = projects[project]?.migration_method || defaultMethod;
  const jobSubmission = useMemo(() => {
    if (!metadata) return null;
    try {
      return validateJobSubmissionMetadata(metadata, migrationMethod);
    } catch (err) {
      return err instanceof Error ? err : new Error('Job submission metadata was invalid.');
    }
  }, [metadata, migrationMethod]);

  const jobFields = jobSubmission instanceof Error || jobSubmission === null ? [] : jobSubmission.fields;
  const runControls = jobSubmission instanceof Error || jobSubmission === null
    ? {}
    : jobSubmission.runControls;
  const metadataError = jobSubmission instanceof Error ? jobSubmission.message : '';

  useEffect(() => {
    if (!jobSubmission || jobSubmission instanceof Error) return;
    setControls((current) => ({
      ...current,
      ...runControlDefaults(jobSubmission.runControls),
    }));
    setJobParameters({});
  }, [jobSubmission]);

  async function saveJob(event: FormEvent) {
    event.preventDefault();
    if (!project) {
      setError('Select a project before saving a job definition.');
      return;
    }
    const selectedProject = projects[project];
    if (!selectedProject) {
      setError('Select a valid project before saving a job definition.');
      return;
    }
    const name = savedJobName(project, runType);
    setSaving(true);
    setNotice('');
    setError('');
    try {
      const payload = await apiFetch(settings, '/saved-jobs', {
        method: 'POST',
        body: JSON.stringify(buildSavedJobRequest({
          name,
          project,
          rsp: selectedProject.rsp || `${project}.rsp`,
          runType,
          jobParameters: compactTextValues(jobParameters),
          controls: controlsPayload(controls),
        })),
      });
      const response = validateSavedJobSaveResponse(payload, name);
      setNotice(response.message);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Job definition could not be saved.');
    } finally {
      setSaving(false);
    }
  }

  const projectOptions = [
    { value: '', label: 'Select project' },
    ...Object.keys(projects).sort().map((name) => ({ value: name, label: name })),
  ];
  const savedJobRows = Object.values(savedJobs).map((job) => ({
    Name: job.name,
    Project: job.project,
    Type: job.run_type,
    RSP: job.rsp || '',
  }));

  return (
    <section className="zeus-panel">
      <h2 className="page-title">ZDM Job Definitions</h2>
      <p className="page-caption">Create reusable job definitions from backend profile metadata.</p>
      <div className="split-form">
        <form className="form-grid" onSubmit={saveJob}>
          <Select
            label="Project"
            required
            value={project}
            onChange={(event) => {
              updateSelectedProject(event.target.value);
              setNotice('');
              setError('');
            }}
            options={projectOptions}
          />
          <Select
            label="Run type"
            value={runType}
            onChange={(event) => setRunType(event.target.value as SavedJobRunType)}
            options={runTypes.map((value) => ({ value, label: value }))}
          />
          {jobFields.map((field) => (
            <Field
              key={field}
              label={field}
              value={jobParameters[field] || ''}
              onChange={(event) =>
                setJobParameters((current) => ({ ...current, [field]: event.target.value }))}
            />
          ))}
          <RunControlsForm
            configs={runControls}
            value={controls}
            onChange={setControls}
          />
          <Button type="submit" variant="primary" disabled={loading || saving || !project || Boolean(metadataError)}>
            {saving ? 'Saving...' : 'Save job definition'}
          </Button>
        </form>
        <div className="status-stack">
          {notice ? <Alert tone="success">{notice}</Alert> : null}
          {error ? <Alert tone="error">{error}</Alert> : null}
          {metadataError ? <Alert tone="error">{metadataError}</Alert> : null}
          {loading ? <p className="empty-state">Loading job definition metadata...</p> : null}
        </div>
      </div>
      <h3>Saved job definitions</h3>
      <Table
        columns={['Name', 'Project', 'Type', 'RSP']}
        rows={savedJobRows}
        emptyText="No saved job definitions yet."
      />
    </section>
  );

  function updateSelectedProject(nextProject: string) {
    if (selectedProjectRef.current !== nextProject) {
      selectedProjectRef.current = nextProject;
      setJobParameters({});
    }
    setProject(nextProject);
  }
}

function RunControlsForm({
  configs,
  value,
  onChange,
}: {
  configs: Record<string, JsonRecord>;
  value: RunControlState;
  onChange: (value: RunControlState) => void;
}) {
  return (
    <>
      {controlNames(configs).map((name) => {
        const config = configs[name] || {};
        const label = typeof config.label === 'string' ? config.label : name;
        const control = typeof config.control === 'string' ? config.control : 'text';
        const options = Array.isArray(config.options)
          ? config.options.filter((option): option is string => typeof option === 'string')
          : [];

        if (control === 'select') {
          return (
            <Select
              key={name}
              label={label}
              value={String(value[name] ?? '')}
              onChange={(event) => onChange({ ...value, [name]: event.target.value })}
              options={options.map((option) => ({ value: option, label: option || 'Blank' }))}
            />
          );
        }
        if (control === 'multiselect') {
          const selected = Array.isArray(value[name]) ? value[name] as string[] : [];
          return (
            <label key={name} className="field">
              <span>{label}</span>
              <select
                multiple
                value={selected}
                onChange={(event) => onChange({
                  ...value,
                  [name]: Array.from(event.target.selectedOptions, (option) => option.value),
                })}
              >
                {options.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>
          );
        }
        if (control === 'checkbox') {
          return (
            <label key={name} className="field checkbox-field">
              <input
                type="checkbox"
                checked={Boolean(value[name])}
                onChange={(event) => onChange({ ...value, [name]: event.target.checked })}
              />
              <span>{label}</span>
            </label>
          );
        }
        if (control === 'schedule') {
          const nowLabel = typeof config.now_label === 'string' ? config.now_label : 'Schedule now';
          const textLabel = typeof config.text_label === 'string' ? config.text_label : label;
          const textHelp = typeof config.text_help === 'string' ? config.text_help : undefined;
          const nowValue = typeof config.now_value === 'string' ? config.now_value : 'NOW';
          const currentValue = String(value[name] ?? '');
          const isNow = currentValue.toUpperCase() === nowValue.toUpperCase();
          return (
            <div key={name} className="form-grid">
              <label className="field checkbox-field">
                <input
                  type="checkbox"
                  checked={isNow}
                  onChange={(event) => onChange({
                    ...value,
                    [name]: event.target.checked ? nowValue : '',
                  })}
                />
                <span>{nowLabel}</span>
              </label>
              <Field
                label={textLabel}
                value={isNow ? '' : currentValue}
                disabled={isNow}
                helper={textHelp}
                onChange={(event) => onChange({ ...value, [name]: event.target.value })}
              />
            </div>
          );
        }
        if (control === 'textarea') {
          return (
            <label key={name} className="field">
              <span>{label}</span>
              <textarea
                rows={3}
                value={String(value[name] ?? '')}
                onChange={(event) => onChange({ ...value, [name]: event.target.value })}
              />
            </label>
          );
        }
        return (
          <Field
            key={name}
            label={label}
            value={String(value[name] ?? '')}
            onChange={(event) => onChange({ ...value, [name]: event.target.value })}
          />
        );
      })}
    </>
  );
}

function validateJobSubmissionMetadata(metadata: FrontendMetadata, method: string) {
  const profile = requireRecord(metadata.migration_profiles[method], `migration_profiles.${method}`);
  const jobSubmission = requireRecord(profile.job_submission, `migration_profiles.${method}.job_submission`);
  const fields = requireStringArray(jobSubmission.fields, `migration_profiles.${method}.job_submission.fields`);
  const runControls = validateRunControls(
    jobSubmission.run_controls,
    `migration_profiles.${method}.job_submission.run_controls`,
  );
  return { fields, runControls };
}

function requireRecord(value: unknown, label: string): JsonRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`GET /metadata/frontend API contract error: ${label} must be an object.`);
  }
  return value as JsonRecord;
}

function requireStringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new Error(`GET /metadata/frontend API contract error: ${label} must be an array of strings.`);
  }
  return value;
}

const supportedRunControlTypes = new Set(['select', 'text', 'multiselect', 'schedule', 'checkbox', 'textarea']);
const runControlNames: RunControlName[] = [
  'advisor_mode',
  'flow_control',
  'flow_phase',
  'genfixup',
  'ignore',
  'schedule',
  'listphases',
  'custom_args',
];

function validateRunControls(value: unknown, label: string): Record<RunControlName, JsonRecord> {
  const controls = requireRecord(value, label);
  for (const [name, rawConfig] of Object.entries(controls)) {
    if (!isRunControlName(name)) {
      throw new Error(`GET /metadata/frontend API contract error: ${label} has unsupported control ${name}.`);
    }
    const config = requireRecord(rawConfig, `${label}.${name}`);
    const control = runControlType(config);
    if (!supportedRunControlTypes.has(control)) {
      throw new Error(`GET /metadata/frontend API contract error: ${label}.${name}.control has unsupported value ${control}.`);
    }
    if (typeof config.label !== 'string' || config.label.trim() === '') {
      throw new Error(`GET /metadata/frontend API contract error: ${label}.${name}.label must be a non-empty string.`);
    }
    if (control === 'select' || control === 'multiselect') {
      const options = requireStringOptions(config.options, `${label}.${name}.options`);
      if (
        control === 'select'
        && Object.prototype.hasOwnProperty.call(config, 'default')
        && config.default !== null
      ) {
        if (typeof config.default !== 'string') {
          throw new Error(`GET /metadata/frontend API contract error: ${label}.${name}.default must be a string or null.`);
        }
        if (!options.includes(config.default)) {
          throw new Error(`GET /metadata/frontend API contract error: ${label}.${name}.default must be listed in options.`);
        }
      }
      if (
        control === 'multiselect'
        && Object.prototype.hasOwnProperty.call(config, 'default')
        && config.default !== null
      ) {
        const defaultValues = requireStringArray(config.default, `${label}.${name}.default`);
        const unsupportedDefault = defaultValues.find((item) => !options.includes(item));
        if (unsupportedDefault !== undefined) {
          throw new Error(`GET /metadata/frontend API contract error: ${label}.${name}.default contains unsupported value ${unsupportedDefault}.`);
        }
      }
    }
    if (
      control === 'checkbox'
      && Object.prototype.hasOwnProperty.call(config, 'default')
      && typeof config.default !== 'boolean'
    ) {
      throw new Error(`GET /metadata/frontend API contract error: ${label}.${name}.default must be a boolean.`);
    }
  }
  return controls as Record<RunControlName, JsonRecord>;
}

function requireStringOptions(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.length === 0 || !value.every((option) => typeof option === 'string')) {
    throw new Error(`GET /metadata/frontend API contract error: ${label} must be a non-empty array of strings.`);
  }
  return value;
}

function runControlDefaults(configs: Record<string, JsonRecord>): Partial<RunControlState> {
  const defaults: Partial<RunControlState> = {};
  for (const name of controlNames(configs)) {
    const config = configs[name];
    if (!config || !Object.prototype.hasOwnProperty.call(config, 'default')) continue;
    const control = runControlType(config);
    if (control === 'checkbox') {
      (defaults as Record<string, string | boolean | string[]>)[name] = Boolean(config.default);
      continue;
    }
    if (control === 'multiselect') {
      (defaults as Record<string, string | boolean | string[]>)[name] = Array.isArray(config.default)
        ? config.default.filter((item): item is string => typeof item === 'string')
        : [];
      continue;
    }
    (defaults as Record<string, string | boolean | string[]>)[name] = String(config.default ?? '');
  }
  return defaults;
}

function runControlType(config: JsonRecord): string {
  return typeof config.control === 'string' && config.control.trim() !== ''
    ? config.control
    : 'text';
}

function isRunControlName(name: string): name is RunControlName {
  return runControlNames.includes(name as RunControlName);
}

function controlNames(configs: Record<string, JsonRecord>): RunControlName[] {
  return runControlNames.filter((name) => Object.prototype.hasOwnProperty.call(configs, name));
}

function compactTextValues(values: Record<string, string>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value.trim() !== ''));
}

function controlsPayload(controls: RunControlState): Record<string, unknown> {
  return {
    advisor_mode: controls.advisor_mode,
    flow_control: controls.flow_control,
    flow_phase: controls.flow_phase,
    genfixup: controls.genfixup,
    ignore: controls.ignore.length > 0 ? controls.ignore : null,
    schedule: controls.schedule,
    listphases: controls.listphases,
    custom_args: lineList(controls.custom_args),
  };
}

function lineList(value: string): string[] | null {
  const items = value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  return items.length > 0 ? items : null;
}

function savedJobName(project: string, runType: SavedJobRunType): string {
  return `${project}_${runType.toLowerCase()}`;
}
