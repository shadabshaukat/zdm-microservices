import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, type ApiSettings } from '../api/client';
import {
  type DbConnectionRecord,
  validateDbConnectionsResponse,
  validateDiscoveryLatestResponse,
  validateDiscoveryResponse,
} from '../api/contracts';
import { Alert } from '../components/Alert';
import { Button } from '../components/Button';
import { CodeBlock } from '../components/CodeBlock';
import { Field } from '../components/Field';
import { Select } from '../components/Select';
import { Tabs } from '../components/Tabs';

type DiscoveryPageProps = {
  settings: ApiSettings;
};

const migrationTypes = [
  { value: 'OFFLINE_LOGICAL', label: 'Logical Offline' },
  { value: 'ONLINE_LOGICAL', label: 'Logical Online' },
  { value: 'OFFLINE_PHYSICAL', label: 'Physical Offline' },
  { value: 'ONLINE_PHYSICAL', label: 'Physical Online' },
  { value: 'HYBRID_OFFLINE', label: 'Hybrid Offline' },
];

export function DiscoveryPage({ settings }: DiscoveryPageProps) {
  const [connections, setConnections] = useState<Record<string, DbConnectionRecord>>({});
  const [connectionName, setConnectionName] = useState('');
  const [migrationType, setMigrationType] = useState('OFFLINE_LOGICAL');
  const [dbUsername, setDbUsername] = useState('');
  const [dbPassword, setDbPassword] = useState('');
  const [snapshot, setSnapshot] = useState<Record<string, unknown> | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const loadRequestRef = useRef(0);
  const discoveryRequestRef = useRef(0);

  function clearDiscoveryState() {
    setSnapshot(null);
    setNotice('');
    setError('');
  }

  function invalidateDiscoveryRequests() {
    discoveryRequestRef.current += 1;
    setRunning(false);
  }

  const loadConnections = useCallback(async () => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    invalidateDiscoveryRequests();
    setConnections({});
    setConnectionName('');
    clearDiscoveryState();
    setLoading(true);
    try {
      const payload = await apiFetch(settings, '/dbconnections');
      if (requestId !== loadRequestRef.current) return;
      setConnections(validateDbConnectionsResponse(payload));
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      setError(err instanceof Error ? err.message : 'DB connections could not be loaded.');
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, [settings]);

  useEffect(() => {
    void loadConnections();
    return () => {
      loadRequestRef.current += 1;
      discoveryRequestRef.current += 1;
    };
  }, [loadConnections]);

  async function loadLatest() {
    const requestId = discoveryRequestRef.current + 1;
    discoveryRequestRef.current = requestId;
    setNotice('');
    setError('');
    if (!connectionName) {
      setError('Select a connection before loading discovery.');
      return;
    }
    setRunning(true);
    try {
      const payload = await apiFetch(
        settings,
        `/dbconnections/${encodeURIComponent(connectionName)}/discovery/latest`,
      );
      if (requestId !== discoveryRequestRef.current) return;
      const latest = validateDiscoveryLatestResponse(payload);
      setSnapshot(latest);
      setNotice(latest ? 'Loaded latest discovery snapshot.' : 'No discovery snapshot found.');
    } catch (err) {
      if (requestId !== discoveryRequestRef.current) return;
      setError(err instanceof Error ? err.message : 'Discovery snapshot could not be loaded.');
    } finally {
      if (requestId === discoveryRequestRef.current) setRunning(false);
    }
  }

  async function runDiscovery(event: FormEvent) {
    event.preventDefault();
    const requestId = discoveryRequestRef.current + 1;
    discoveryRequestRef.current = requestId;
    setNotice('');
    setError('');
    if (!connectionName || !dbUsername.trim() || !dbPassword) {
      setError('Connection, DB username, and DB password are required to run discovery.');
      return;
    }
    setRunning(true);
    try {
      const payload = await apiFetch(settings, '/dbconnections/discover', {
        method: 'POST',
        body: JSON.stringify({
          name: connectionName,
          migration_type: migrationType,
          auth: {
            method: 'password',
            username: dbUsername.trim(),
            password: dbPassword,
          },
        }),
      });
      if (requestId !== discoveryRequestRef.current) return;
      setSnapshot(validateDiscoveryResponse(payload));
      setNotice('Discovery completed.');
    } catch (err) {
      if (requestId !== discoveryRequestRef.current) return;
      setError(err instanceof Error ? err.message : 'Discovery could not be completed.');
    } finally {
      if (requestId === discoveryRequestRef.current) {
        setDbPassword('');
        setRunning(false);
      }
    }
  }

  function handleConnectionNameChange(value: string) {
    setConnectionName(value);
    setDbPassword('');
    clearDiscoveryState();
    invalidateDiscoveryRequests();
  }

  function handleMigrationTypeChange(value: string) {
    setMigrationType(value);
    clearDiscoveryState();
    invalidateDiscoveryRequests();
  }

  const connectionOptions = [
    { value: '', label: 'Select connection' },
    ...Object.values(connections).map((connection) => ({
      value: connection.name,
      label: connection.name,
    })),
  ];

  return (
    <section className="zeus-panel">
      <h2 className="page-title">DB Discovery</h2>
      <p className="page-caption">Run and inspect discovery snapshots for saved database connections.</p>
      {notice ? <Alert tone="success">{notice}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      {loading ? <p className="empty-state">Loading connections...</p> : null}
      <form className="toolbar-row" onSubmit={runDiscovery}>
        <Select
          label="Connection"
          value={connectionName}
          onChange={(event) => handleConnectionNameChange(event.target.value)}
          options={connectionOptions}
        />
        <Select
          label="Migration type"
          value={migrationType}
          onChange={(event) => handleMigrationTypeChange(event.target.value)}
          options={migrationTypes}
        />
        <Field
          label="DB username"
          value={dbUsername}
          onChange={(event) => setDbUsername(event.target.value)}
        />
        <Field
          label="DB password"
          type="password"
          value={dbPassword}
          onChange={(event) => setDbPassword(event.target.value)}
        />
        <Button type="button" onClick={loadLatest} disabled={running}>
          Load latest
        </Button>
        <Button type="submit" variant="primary" disabled={running}>
          {running ? 'Working...' : 'Run discovery'}
        </Button>
      </form>
      {snapshot ? (
        <Tabs
          tabs={[
            { label: 'Summary', content: <CodeBlock value={JSON.stringify(snapshot, null, 2)} /> },
            { label: 'Profiles', content: <ProfilesTab snapshot={snapshot} /> },
            { label: 'Raw', content: <CodeBlock value={JSON.stringify(snapshot, null, 2)} /> },
          ]}
        />
      ) : (
        <Alert>Select a connection and load or run discovery.</Alert>
      )}
    </section>
  );
}

function ProfilesTab({ snapshot }: { snapshot: Record<string, unknown> }) {
  if (snapshot.extras === undefined) {
    return <Alert>No custom profile DDL returned for this discovery snapshot.</Alert>;
  }
  if (!isRecord(snapshot.extras)) {
    return <Alert tone="error">Unexpected discovery profile payload shape.</Alert>;
  }
  if (snapshot.extras.logical_common === undefined) {
    return <Alert>No custom profile DDL returned for this discovery snapshot.</Alert>;
  }
  if (!isRecord(snapshot.extras.logical_common)) {
    return <Alert tone="error">Unexpected discovery profile payload shape.</Alert>;
  }
  const logicalCommon = snapshot.extras.logical_common;
  const profiles = logicalCommon.db_profiles;
  if (profiles === undefined) {
    return <Alert>No custom profile DDL returned for this discovery snapshot.</Alert>;
  }
  if (!Array.isArray(profiles)) {
    return <Alert tone="error">Unexpected discovery profile payload shape.</Alert>;
  }
  return <CodeBlock value={JSON.stringify(profiles, null, 2)} />;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
