import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, type ApiSettings } from '../api/client';
import {
  type JobLogRecord,
  type JobQueryResponse,
  validateJobIdsResponse,
  validateJoblogReadResponse,
  validateJoblogsResponse,
  validateJobQueryResponse,
} from '../api/contracts';
import { Alert } from '../components/Alert';
import { Button } from '../components/Button';
import { CodeBlock } from '../components/CodeBlock';
import { Field } from '../components/Field';
import { Select } from '../components/Select';

type JobMonitoringPageProps = {
  settings: ApiSettings;
};

export function JobMonitoringPage({ settings }: JobMonitoringPageProps) {
  const [jobIds, setJobIds] = useState<string[]>([]);
  const [jobId, setJobId] = useState('');
  const [result, setResult] = useState<JobQueryResponse | null>(null);
  const [logs, setLogs] = useState<JobLogRecord[]>([]);
  const [logContent, setLogContent] = useState('');
  const [selectedLog, setSelectedLog] = useState('');
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [readingLog, setReadingLog] = useState('');
  const [error, setError] = useState('');
  const loadRequestRef = useRef(0);
  const queryRequestRef = useRef(0);
  const logRequestRef = useRef(0);

  const loadJobIds = useCallback(async () => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setLoading(true);
    setError('');
    try {
      const payload = await apiFetch(settings, '/jobs/ids');
      if (requestId !== loadRequestRef.current) return;
      const response = validateJobIdsResponse(payload);
      setJobIds(response.job_ids);
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      setJobIds([]);
      setError(err instanceof Error ? err.message : 'Job IDs could not be loaded.');
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, [settings]);

  useEffect(() => {
    void loadJobIds();
    return () => {
      loadRequestRef.current += 1;
      queryRequestRef.current += 1;
      logRequestRef.current += 1;
    };
  }, [loadJobIds]);

  function clearJobDetails() {
    setResult(null);
    setLogs([]);
    setLogContent('');
    setSelectedLog('');
  }

  async function query(event: FormEvent) {
    event.preventDefault();
    const cleanJobId = jobId.trim();
    if (!cleanJobId) {
      setError('Enter a Job ID before querying.');
      return;
    }
    const requestId = queryRequestRef.current + 1;
    queryRequestRef.current = requestId;
    setWorking(true);
    setError('');
    clearJobDetails();
    try {
      const payload = await apiFetch(settings, `/jobs/${encodeURIComponent(cleanJobId)}`);
      if (requestId !== queryRequestRef.current) return;
      setResult(validateJobQueryResponse(payload));
      const logsPayload = await apiFetch(settings, `/joblogs?job_id=${encodeURIComponent(cleanJobId)}`);
      if (requestId !== queryRequestRef.current) return;
      setLogs(validateJoblogsResponse(logsPayload, cleanJobId).logs);
    } catch (err) {
      if (requestId !== queryRequestRef.current) return;
      setError(err instanceof Error ? err.message : 'Job query could not be loaded.');
    } finally {
      if (requestId === queryRequestRef.current) setWorking(false);
    }
  }

  async function readLog(name: string) {
    const cleanJobId = jobId.trim();
    if (!cleanJobId) return;
    const requestId = logRequestRef.current + 1;
    logRequestRef.current = requestId;
    setReadingLog(name);
    setError('');
    setLogContent('');
    setSelectedLog(name);
    try {
      const payload = await apiFetch(settings, '/joblogs/read', {
        method: 'POST',
        body: JSON.stringify({ job_id: cleanJobId, name }),
      });
      if (requestId !== logRequestRef.current) return;
      setLogContent(validateJoblogReadResponse(payload, cleanJobId, name).content);
    } catch (err) {
      if (requestId !== logRequestRef.current) return;
      setError(err instanceof Error ? err.message : 'Job log could not be loaded.');
    } finally {
      if (requestId === logRequestRef.current) setReadingLog('');
    }
  }

  return (
    <section className="zeus-panel">
      <h2 className="page-title">ZDM Job Monitoring</h2>
      <p className="page-caption">Query ZDM job status and inspect backend response details.</p>
      <form className="toolbar-row" onSubmit={query}>
        <Field
          label="Job ID"
          value={jobId}
          onChange={(event) => {
            queryRequestRef.current += 1;
            logRequestRef.current += 1;
            setJobId(event.target.value);
            clearJobDetails();
            setError('');
          }}
        />
        <Select
          label="Recent jobs"
          value={jobId}
          onChange={(event) => {
            queryRequestRef.current += 1;
            logRequestRef.current += 1;
            setJobId(event.target.value);
            clearJobDetails();
            setError('');
          }}
          options={[
            { value: '', label: loading ? 'Loading recent jobs...' : 'Select recent job' },
            ...jobIds.map((id) => ({ value: id, label: id })),
          ]}
        />
        <Button type="submit" variant="primary" disabled={working || !jobId.trim()}>
          {working ? 'Querying...' : 'Query'}
        </Button>
      </form>
      <div className="status-stack">
        {error ? <Alert tone="error">{error}</Alert> : null}
      </div>
      {result ? (
        <>
          <h3>Latest result</h3>
          <CodeBlock value={result.output} />
        </>
      ) : null}
      {logs.length > 0 ? (
        <>
          <h3>Job logs</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Size</th>
                  <th>Modified</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.name}>
                    <td>{log.name}</td>
                    <td>{log.size_bytes}</td>
                    <td>{log.modified_time}</td>
                    <td>
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={readingLog === log.name}
                        onClick={() => void readLog(log.name)}
                      >
                        {readingLog === log.name ? 'Loading...' : `View ${log.name}`}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : result ? (
        <p className="empty-state">No log files found for this job.</p>
      ) : null}
      {logContent ? (
        <>
          <h3>{selectedLog}</h3>
          <CodeBlock value={logContent} />
        </>
      ) : null}
    </section>
  );
}
