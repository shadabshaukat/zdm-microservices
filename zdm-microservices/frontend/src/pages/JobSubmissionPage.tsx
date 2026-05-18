import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, type ApiSettings } from '../api/client';
import {
  type RunJobResponse,
  type SavedJobRecord,
  validateRunJobResponse,
  validateSavedJobsResponse,
} from '../api/contracts';
import { buildRunJobRequest } from '../api/payloads';
import { Alert } from '../components/Alert';
import { Button } from '../components/Button';
import { CodeBlock } from '../components/CodeBlock';
import { Select } from '../components/Select';

type JobSubmissionPageProps = {
  settings: ApiSettings;
};

export function JobSubmissionPage({ settings }: JobSubmissionPageProps) {
  const [savedJobs, setSavedJobs] = useState<Record<string, SavedJobRecord>>({});
  const [selectedJob, setSelectedJob] = useState('');
  const [result, setResult] = useState<RunJobResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const loadRequestRef = useRef(0);
  const runRequestRef = useRef(0);
  const selectedJobRef = useRef('');

  const loadSavedJobs = useCallback(async () => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setLoading(true);
    setError('');
    try {
      const payload = await apiFetch(settings, '/saved-jobs');
      if (requestId !== loadRequestRef.current) return;
      const jobs = validateSavedJobsResponse(payload);
      const currentJob = selectedJobRef.current;
      const nextJob = currentJob && Object.prototype.hasOwnProperty.call(jobs, currentJob)
        ? currentJob
        : Object.keys(jobs).sort()[0] || '';
      setSavedJobs(jobs);
      updateSelectedJob(nextJob);
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      setSavedJobs({});
      updateSelectedJob('');
      setError(err instanceof Error ? err.message : 'Saved job definitions could not be loaded.');
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, [settings]);

  useEffect(() => {
    void loadSavedJobs();
    return () => {
      loadRequestRef.current += 1;
      runRequestRef.current += 1;
    };
  }, [loadSavedJobs]);

  async function submit(dryRun: boolean) {
    const job = savedJobs[selectedJob];
    if (!job) {
      setError('Select a saved job definition before submitting.');
      return;
    }
    const requestId = runRequestRef.current + 1;
    runRequestRef.current = requestId;
    setWorking(true);
    setNotice('');
    setError('');
    setResult(null);
    try {
      const payload = await apiFetch(settings, '/jobs', {
        method: 'POST',
        body: JSON.stringify(buildRunJobRequest(job, dryRun)),
      });
      if (requestId !== runRequestRef.current) return;
      const response = validateRunJobResponse(payload, { dryRun });
      setResult(response);
      setNotice(dryRun ? 'Command preview planned.' : 'Saved job submitted.');
    } catch (err) {
      if (requestId !== runRequestRef.current) return;
      setError(err instanceof Error ? err.message : 'Saved job could not be submitted.');
    } finally {
      if (requestId === runRequestRef.current) setWorking(false);
    }
  }

  function changeSelectedJob(value: string) {
    updateSelectedJob(value);
    setError('');
  }

  function updateSelectedJob(value: string) {
    if (selectedJobRef.current === value) {
      setSelectedJob(value);
      return;
    }
    selectedJobRef.current = value;
    runRequestRef.current += 1;
    setSelectedJob(value);
    setResult(null);
    setNotice('');
    setWorking(false);
  }

  const selected = savedJobs[selectedJob];
  const jobOptions = [
    { value: '', label: 'Select saved job' },
    ...Object.keys(savedJobs).sort().map((name) => ({ value: name, label: name })),
  ];

  return (
    <section className="zeus-panel">
      <h2 className="page-title">ZDM Job Submission</h2>
      <p className="page-caption">Preview or submit a saved ZDM job definition.</p>
      <div className="toolbar-row">
        <Select
          label="Saved job definitions"
          value={selectedJob}
          onChange={(event) => changeSelectedJob(event.target.value)}
          options={jobOptions}
        />
        <Button type="button" disabled={working || !selected} onClick={() => submit(true)}>
          Preview command
        </Button>
        <Button type="button" variant="primary" disabled={working || !selected} onClick={() => submit(false)}>
          {working ? 'Working...' : 'Run'}
        </Button>
      </div>
      <div className="status-stack">
        {notice ? <Alert tone="success">{notice}</Alert> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        {loading ? <p className="empty-state">Loading saved job definitions...</p> : null}
      </div>
      {selected ? (
        <>
          <h3>Saved job definition</h3>
          <CodeBlock value={JSON.stringify(selected, null, 2)} />
        </>
      ) : null}
      {result ? (
        <>
          <h3>Submission result</h3>
          <CodeBlock
            value={'command' in result ? result.command.join('\n') : JSON.stringify(result, null, 2)}
          />
          <CodeBlock value={JSON.stringify(result, null, 2)} />
        </>
      ) : null}
    </section>
  );
}
