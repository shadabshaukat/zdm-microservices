import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, type ApiSettings } from '../api/client';
import {
  type JobsDashboardRecord,
  type JobsDashboardResponse,
  type JsonRecord,
  validateJobsDashboardResponse,
} from '../api/contracts';
import { Alert } from '../components/Alert';
import { Button } from '../components/Button';
import { Table } from '../components/Table';

type MigrationDashboardPageProps = {
  settings: ApiSettings;
};

const dashboardColumns = ['Project', 'Job ID', 'Type', 'Status', 'Stage'];

export function MigrationDashboardPage({ settings }: MigrationDashboardPageProps) {
  const [payload, setPayload] = useState<JobsDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const loadRequestRef = useRef(0);

  const loadJobs = useCallback(async (refresh = false) => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setLoading(true);
    setError('');
    try {
      const path = refresh ? '/jobs?refresh=true' : '/jobs';
      const response = await apiFetch(settings, path);
      if (requestId !== loadRequestRef.current) return;
      setPayload(validateJobsDashboardResponse(response));
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      setPayload(null);
      setError(err instanceof Error ? err.message : 'Jobs dashboard data could not be loaded.');
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, [settings]);

  useEffect(() => {
    void loadJobs(false);
    return () => {
      loadRequestRef.current += 1;
    };
  }, [loadJobs]);

  const rows = useMemo(() => {
    return (payload?.jobs || []).map(dashboardRow);
  }, [payload]);
  const counts = useMemo(() => jobCounts(rows), [rows]);

  return (
    <section className="zeus-panel">
      <h2 className="page-title">Migration Dashboard</h2>
      <p className="page-caption">Fleet view from enriched GET /jobs records only.</p>
      <div className="toolbar-row">
        <Button
          type="button"
          variant="primary"
          disabled={loading}
          onClick={() => void loadJobs(true)}
        >
          {loading ? 'Loading...' : 'Refresh Jobs'}
        </Button>
      </div>
      <div className="status-stack">
        {error ? <Alert tone="error">{error}</Alert> : null}
        {payload ? (
          <p className="empty-state">
            <span>Source: {payload.source}</span>
            {payload.last_refreshed ? <span> Last refreshed: {payload.last_refreshed}</span> : null}
          </p>
        ) : null}
      </div>
      {payload?.warnings.length ? (
        <Alert tone="warning">{payload.warnings.map((warning) => String(warning)).join('\n')}</Alert>
      ) : null}
      {payload ? (
        <>
          <div className="kpi-grid">
            <Kpi label="Total Jobs" value={counts.total} />
            <Kpi label="Succeeded" value={counts.succeeded} />
            <Kpi label="Running" value={counts.running} />
            <Kpi label="Failed" value={counts.failed} />
          </div>
          <Table
            columns={dashboardColumns}
            rows={rows}
            emptyText="No jobs returned."
          />
        </>
      ) : null}
    </section>
  );
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="kpi">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function dashboardRow(record: JobsDashboardRecord) {
  const job = record.job;
  const inventory = record.inventory;
  const project = asRecord(inventory.project);
  return {
    Project: firstText(job.project, project?.name),
    'Job ID': text(job.job_id),
    Type: text(job.job_type).toUpperCase(),
    Status: text(job.status).toUpperCase(),
    Stage: text(job.current_phase),
  };
}

function jobCounts(rows: Array<Record<string, unknown>>) {
  return {
    total: rows.length,
    succeeded: rows.filter((row) => statusCategory(row.Status) === 'succeeded').length,
    running: rows.filter((row) => statusCategory(row.Status) === 'running').length,
    failed: rows.filter((row) => statusCategory(row.Status) === 'failed').length,
  };
}

function statusCategory(value: unknown) {
  const normalized = text(value).toUpperCase().replace(/[-\s]+/g, '_');
  if (['SUCCEEDED', 'SUCCESS', 'DONE', 'COMPLETED'].includes(normalized)) return 'succeeded';
  if (['RUNNING', 'EXECUTING', 'IN_PROGRESS', 'STARTED'].includes(normalized)) return 'running';
  if (['FAILED', 'ERROR', 'ABORTED'].includes(normalized)) return 'failed';
  return 'other';
}

function asRecord(value: unknown): JsonRecord | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as JsonRecord
    : null;
}

function firstText(...values: unknown[]) {
  for (const value of values) {
    const candidate = text(value);
    if (candidate) return candidate;
  }
  return '';
}

function text(value: unknown) {
  if (value === null || value === undefined) return '';
  return String(value).trim();
}
