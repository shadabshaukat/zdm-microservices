import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, type ApiSettings } from '../api/client';
import {
  type DbConnectionRecord,
  type ProjectRecord,
  validateDbConnectionsResponse,
  validateProjectsResponse,
  validateProjectWriteResponse,
} from '../api/contracts';
import { Alert } from '../components/Alert';
import { Button } from '../components/Button';
import { Field } from '../components/Field';
import { Select, type SelectOption } from '../components/Select';
import { Table } from '../components/Table';

type ProjectsPageProps = {
  settings: ApiSettings;
};

export function ProjectsPage({ settings }: ProjectsPageProps) {
  const [projects, setProjects] = useState<Record<string, ProjectRecord>>({});
  const [connections, setConnections] = useState<Record<string, DbConnectionRecord>>({});
  const [form, setForm] = useState({ name: '', source_connection: '', target_connection: '' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const loadRequestRef = useRef(0);

  const loadData = useCallback(async () => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setLoading(true);
    setError('');
    try {
      const [projectsPayload, connectionsPayload] = await Promise.all([
        apiFetch(settings, '/projects'),
        apiFetch(settings, '/dbconnections'),
      ]);
      if (requestId !== loadRequestRef.current) return;
      setProjects(validateProjectsResponse(projectsPayload));
      setConnections(validateDbConnectionsResponse(connectionsPayload));
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      setError(err instanceof Error ? err.message : 'Project data could not be loaded.');
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

  const sourceOptions = useMemo(() => connectionOptions(connections, 'source'), [connections]);
  const targetOptions = useMemo(() => connectionOptions(connections, 'target'), [connections]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    setError('');
    try {
      const payload = await apiFetch(settings, '/projects', {
        method: 'POST',
        body: JSON.stringify({
          name: form.name.trim(),
          source_connection: form.source_connection,
          target_connection: form.target_connection,
        }),
      });
      const response = validateProjectWriteResponse(payload, form.name.trim());
      setNotice(response.message);
      setForm((current) => ({ ...current, name: '' }));
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Project could not be saved.');
    } finally {
      setSaving(false);
    }
  }

  const rows = Object.values(projects).map((project) => ({
    Name: project.name,
    Source: project.source_connection,
    Target: project.target_connection,
    'Response File': project.rsp || '',
    'Migration Method': project.migration_method || '',
  }));

  return (
    <section className="zeus-panel">
      <h2 className="page-title">Projects</h2>
      <p className="page-caption">Create migration projects from saved source and target DB connections.</p>
      <div className="split-form">
        <form className="form-grid" onSubmit={submit}>
          <Field
            label="Project name"
            required
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <Select
            label="Source connection"
            required
            value={form.source_connection}
            onChange={(event) => setForm({ ...form, source_connection: event.target.value })}
            options={[{ value: '', label: 'Select source connection' }, ...sourceOptions]}
          />
          <Select
            label="Target connection"
            required
            value={form.target_connection}
            onChange={(event) => setForm({ ...form, target_connection: event.target.value })}
            options={[{ value: '', label: 'Select target connection' }, ...targetOptions]}
          />
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? 'Saving...' : 'Create project'}
          </Button>
        </form>
        <div className="status-stack">
          {notice ? <Alert tone="success">{notice}</Alert> : null}
          {error ? <Alert tone="error">{error}</Alert> : null}
          {loading ? <p className="empty-state">Loading projects...</p> : null}
        </div>
      </div>
      <h3>Existing projects</h3>
      <Table
        columns={['Name', 'Source', 'Target', 'Response File', 'Migration Method']}
        rows={rows}
        emptyText="No projects created yet."
      />
    </section>
  );
}

function connectionOptions(
  connections: Record<string, DbConnectionRecord>,
  role: DbConnectionRecord['connection_role'],
): SelectOption[] {
  return Object.values(connections)
    .filter((connection) => connection.connection_role === role)
    .map((connection) => ({ value: connection.name, label: connection.name }));
}
