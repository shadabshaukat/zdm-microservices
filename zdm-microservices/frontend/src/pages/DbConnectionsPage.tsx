import { type ChangeEvent, type FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, type ApiSettings } from '../api/client';
import {
  type DbConnectionRecord,
  validateDbConnectionsResponse,
  validateDbConnectionWriteResponse,
  validateTlsWalletUploadResponse,
} from '../api/contracts';
import { Alert } from '../components/Alert';
import { Button } from '../components/Button';
import { Field } from '../components/Field';
import { Select } from '../components/Select';
import { Table } from '../components/Table';

type DbConnectionsPageProps = {
  settings: ApiSettings;
};

const dbPlatformOptions = [
  'ORACLE_DATABASE',
  'ONPREM_EXADATA',
  'ODA',
  'AWS_RDS_ORACLE',
  'OCI_BASEDB',
  'OCI_EXADB_D',
  'OCI_EXADB_XS',
  'OCI_ADB_S',
  'OCI_ADB_D',
  'EXADB_CC',
  'EXADB_CC_ADB_D',
  'ORACLEDB_AZURE_EXADB_D',
  'ORACLEDB_AZURE_EXADB_XS',
  'ORACLEDB_AZURE_BASEDB',
  'ORACLEDB_AZURE_ADB_S',
  'ORACLEDB_AZURE_ADB_D',
  'ORACLEDB_GCP_EXADB_D',
  'ORACLEDB_GCP_EXADB_XS',
  'ORACLEDB_GCP_BASEDB',
  'ORACLEDB_GCP_ADB_S',
  'ORACLEDB_AWS_EXADB_D',
  'ORACLEDB_AWS_ADB_D',
];

export function DbConnectionsPage({ settings }: DbConnectionsPageProps) {
  const [connections, setConnections] = useState<Record<string, DbConnectionRecord>>({});
  const [form, setForm] = useState({
    name: '',
    connection_role: 'source',
    db_type: 'ORACLE_DATABASE',
    host: '',
    port: '1521',
    service_name: '',
    protocol: 'TCP',
    allow_tls_without_wallet: false,
  });
  const [tlsWallet, setTlsWallet] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const loadRequestRef = useRef(0);

  const loadConnections = useCallback(async () => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setLoading(true);
    setError('');
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
    };
  }, [loadConnections]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    setError('');
    let connectionSaved = false;
    try {
      const name = form.name.trim();
      const response = validateDbConnectionWriteResponse(
        await apiFetch(settings, '/dbconnections', {
          method: 'POST',
          body: JSON.stringify({
            name,
            host: form.host.trim(),
            port: Number(form.port),
            service_name: form.service_name.trim(),
            db_type: form.db_type,
            connection_role: form.connection_role,
            protocol: form.protocol,
            allow_tls_without_wallet: form.allow_tls_without_wallet,
          }),
        }),
        name,
      );
      connectionSaved = true;

      let message = response.message;
      if (tlsWallet) {
        const uploadResponse = await uploadTlsWallet(settings, name, tlsWallet);
        message = `${message}. ${uploadResponse.message}`;
      }
      setNotice(message);
      setForm((current) => ({ ...current, name: '', host: '', service_name: '' }));
      setTlsWallet(null);
      setFileInputKey((current) => current + 1);
      await loadConnections();
    } catch (err) {
      if (connectionSaved) {
        await loadConnections();
        setError(
          `Connection was saved, but TLS wallet upload failed: ${
            err instanceof Error ? err.message : String(err)
          }`,
        );
      } else {
        setError(err instanceof Error ? err.message : 'DB connection could not be saved.');
      }
    } finally {
      setSaving(false);
    }
  }

  function updateText(key: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateTlsWallet(event: ChangeEvent<HTMLInputElement>) {
    setTlsWallet(event.target.files?.[0] ?? null);
  }

  const rows = Object.values(connections).map((connection) => ({
    Name: connection.name,
    Role: connection.connection_role,
    'DB Platform': connection.db_type,
    Host: connection.host,
    Port: connection.port,
    Service: connection.service_name,
    Protocol: connection.protocol,
    'TLS w/o wallet': connection.allow_tls_without_wallet ? 'Yes' : 'No',
    'TLS Wallet dir': connection.tls_wallet_uploaded_dir || '',
  }));

  return (
    <section className="zeus-panel">
      <h2 className="page-title">DB Connections</h2>
      <p className="page-caption">Define source and target database connection metadata.</p>
      <div className="split-form">
        <form className="form-grid" onSubmit={submit}>
          <Field
            label="Connection name"
            required
            value={form.name}
            onChange={(event) => updateText('name', event.target.value)}
          />
          <Select
            label="Role"
            value={form.connection_role}
            onChange={(event) => updateText('connection_role', event.target.value)}
            options={[
              { value: 'source', label: 'Source' },
              { value: 'target', label: 'Target' },
            ]}
          />
          <Select
            label="DB Platform"
            value={form.db_type}
            onChange={(event) => updateText('db_type', event.target.value)}
            options={dbPlatformOptions.map((value) => ({ value, label: value }))}
          />
          <Field
            label="Host"
            required
            value={form.host}
            onChange={(event) => updateText('host', event.target.value)}
          />
          <Field
            label="Port"
            required
            type="number"
            min="1"
            max="65535"
            value={form.port}
            onChange={(event) => updateText('port', event.target.value)}
          />
          <Field
            label="Service name"
            required
            value={form.service_name}
            onChange={(event) => updateText('service_name', event.target.value)}
          />
          <Select
            label="Protocol"
            value={form.protocol}
            onChange={(event) => updateText('protocol', event.target.value)}
            options={[
              { value: 'TCP', label: 'TCP' },
              { value: 'TCPS', label: 'TCPS' },
            ]}
          />
          <label className="field checkbox-field">
            <input
              type="checkbox"
              checked={form.allow_tls_without_wallet}
              onChange={(event) =>
                setForm({ ...form, allow_tls_without_wallet: event.target.checked })}
            />
            <span>Allow TLS without wallet</span>
          </label>
          <Field
            key={fileInputKey}
            label="TLS wallet file"
            type="file"
            onChange={updateTlsWallet}
          />
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? 'Saving...' : 'Save connection'}
          </Button>
        </form>
        <div className="status-stack">
          {notice ? <Alert tone="success">{notice}</Alert> : null}
          {error ? <Alert tone="error">{error}</Alert> : null}
          {loading ? <p className="empty-state">Loading connections...</p> : null}
        </div>
      </div>
      <h3>Saved connections</h3>
      <Table
        columns={[
          'Name',
          'Role',
          'DB Platform',
          'Host',
          'Port',
          'Service',
          'Protocol',
          'TLS w/o wallet',
          'TLS Wallet dir',
        ]}
        rows={rows}
        emptyText="No connections saved yet."
      />
    </section>
  );
}

async function uploadTlsWallet(
  settings: ApiSettings,
  connectionName: string,
  wallet: File,
) {
  const base = settings.apiBase || '';
  const formData = new FormData();
  formData.append('wallet', wallet);

  const response = await fetch(
    `${base}/dbconnections/${encodeURIComponent(connectionName)}/tls-wallet`,
    {
      method: 'POST',
      headers: {
        Authorization: `Basic ${btoa(`${settings.username}:${settings.password}`)}`,
      },
      body: formData,
    },
  );
  const text = await response.text();
  const payload = parseJsonPayload(text);
  if (!response.ok) {
    throw new Error(uploadErrorMessage(response.status, payload, text));
  }
  return validateTlsWalletUploadResponse(payload);
}

function parseJsonPayload(text: string): unknown {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

function uploadErrorMessage(status: number, payload: unknown, text: string) {
  const detail = uploadErrorDetail(payload);
  if (detail) return `POST /dbconnections/{name}/tls-wallet failed (HTTP ${status}): ${detail}`;
  const fallback = text.trim();
  if (fallback) {
    return `POST /dbconnections/{name}/tls-wallet failed (HTTP ${status}): ${fallback.slice(0, 240)}`;
  }
  return `POST /dbconnections/{name}/tls-wallet failed (HTTP ${status}).`;
}

function uploadErrorDetail(payload: unknown): string {
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) return '';
  const detail = (payload as Record<string, unknown>).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (typeof item === 'object' && item !== null && 'msg' in item) {
          const msg = (item as Record<string, unknown>).msg;
          return typeof msg === 'string' ? msg : '';
        }
        return '';
      })
      .filter(Boolean)
      .join('; ');
  }
  if (typeof detail === 'object' && detail !== null) return JSON.stringify(detail);
  return '';
}
