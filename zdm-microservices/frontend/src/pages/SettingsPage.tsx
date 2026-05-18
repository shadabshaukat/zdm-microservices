import { type FormEvent, useState } from 'react';
import {
  apiFetch,
  loadApiSettings,
  saveApiSettings,
  validateHealthResponse,
  type ApiSettings,
} from '../api/client';

type SettingsPageProps = {
  onSettingsSaved?: (settings: ApiSettings) => void;
};

export function SettingsPage({ onSettingsSaved }: SettingsPageProps) {
  const [settings, setSettings] = useState<ApiSettings>(() => loadApiSettings());
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setStatus('');
    setError('');
    try {
      saveApiSettings(settings);
      const payload = validateHealthResponse(await apiFetch(settings, '/health'));
      onSettingsSaved?.(loadApiSettings());
      setStatus(`Backend healthy: ${payload.status}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ZEUS backend is not reachable.');
    }
  }

  return (
    <section className="zeus-panel">
      <h2 className="page-title">ZEUS Settings</h2>
      <p className="page-caption">Configure the React console connection to the FastAPI backend.</p>
      <form className="form-grid" onSubmit={submit}>
        <label>
          API base URL
          <input
            value={settings.apiBase}
            onChange={(event) => setSettings({ ...settings, apiBase: event.target.value })}
            placeholder="https://localhost:8001"
          />
        </label>
        <label>
          Username
          <input
            value={settings.username}
            onChange={(event) => setSettings({ ...settings, username: event.target.value })}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={settings.password}
            onChange={(event) => setSettings({ ...settings, password: event.target.value })}
          />
        </label>
        <button className="primary-button" type="submit">
          Save and test
        </button>
      </form>
      {status ? <p className="success-text">{status}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
    </section>
  );
}
