import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, type ApiSettings } from '../api/client';
import {
  type CredentialWalletRecord,
  validateCredentialWalletsResponse,
  validateWalletCommandResponse,
} from '../api/contracts';
import { Alert } from '../components/Alert';
import { Button } from '../components/Button';
import { Field } from '../components/Field';
import { Select } from '../components/Select';
import { Table } from '../components/Table';

type WalletsPageProps = {
  settings: ApiSettings;
};

export function WalletsPage({ settings }: WalletsPageProps) {
  const [wallets, setWallets] = useState<CredentialWalletRecord[]>([]);
  const [form, setForm] = useState({ wallet_name: '', user: '', password: '' });
  const [selectedWallet, setSelectedWallet] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const loadRequestRef = useRef(0);

  const loadWallets = useCallback(async () => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setLoading(true);
    setError('');
    try {
      const response = validateCredentialWalletsResponse(
        await apiFetch(settings, '/credential-wallets'),
      );
      if (requestId !== loadRequestRef.current) return;
      setWallets(response.wallets);
      setSelectedWallet((current) => (
        current && response.wallets.some((wallet) => wallet.name === current) ? current : ''
      ));
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      setError(err instanceof Error ? err.message : 'Credential wallets could not be loaded.');
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, [settings]);

  useEffect(() => {
    void loadWallets();
    return () => {
      loadRequestRef.current += 1;
    };
  }, [loadWallets]);

  async function createWallet(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    setError('');
    try {
      const response = validateWalletCommandResponse(
        await apiFetch(settings, '/wallets/ora-pki', {
          method: 'POST',
          body: JSON.stringify({ wallet_name: form.wallet_name.trim() }),
        }),
        'POST /wallets/ora-pki',
      );
      setNotice(response.output || 'Credential wallet created.');
      setSelectedWallet(form.wallet_name.trim());
      await loadWallets();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Credential wallet could not be created.');
    } finally {
      setSaving(false);
    }
  }

  async function createCredential(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    setError('');
    try {
      const response = validateWalletCommandResponse(
        await apiFetch(settings, '/wallets/mkstore-credential', {
          method: 'POST',
          body: JSON.stringify({
            wallet_name: selectedWallet,
            user: form.user.trim(),
            password: form.password,
          }),
        }),
        'POST /wallets/mkstore-credential',
      );
      setNotice(response.output || 'Credential saved.');
      setForm((current) => ({ ...current, password: '' }));
      await loadWallets();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Credential could not be saved.');
    } finally {
      setSaving(false);
    }
  }

  const rows = wallets.map((wallet) => ({
    Wallet: wallet.name,
    Path: wallet.path,
    'Credential User': wallet.credential_username || '',
    Status: wallet.credential_username ? 'Ready' : 'Empty',
  }));

  return (
    <section className="zeus-panel">
      <h2 className="page-title">DB Wallets & Credentials</h2>
      <p className="page-caption">Create credential wallets and store database credentials.</p>
      <div className="split-form">
        <form className="form-grid" onSubmit={createWallet}>
          <Field
            label="Credential wallet name"
            required
            value={form.wallet_name}
            onChange={(event) => setForm({ ...form, wallet_name: event.target.value })}
          />
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? 'Saving...' : 'Create wallet'}
          </Button>
        </form>
        <form className="form-grid" onSubmit={createCredential}>
          <Select
            label="Wallet"
            required
            value={selectedWallet}
            onChange={(event) => setSelectedWallet(event.target.value)}
            options={[
              { value: '', label: 'Select wallet' },
              ...wallets.map((wallet) => ({ value: wallet.name, label: wallet.name })),
            ]}
          />
          <Field
            label="Credential user"
            required
            value={form.user}
            onChange={(event) => setForm({ ...form, user: event.target.value })}
          />
          <Field
            label="Credential password"
            type="password"
            required
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? 'Saving...' : 'Create credential'}
          </Button>
        </form>
      </div>
      <div className="status-stack">
        {notice ? <Alert tone="success">{notice}</Alert> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        {loading ? <p className="empty-state">Loading wallets...</p> : null}
      </div>
      <h3>Saved wallets</h3>
      <Table
        columns={['Wallet', 'Path', 'Credential User', 'Status']}
        rows={rows}
        emptyText="No credential wallets saved."
      />
    </section>
  );
}
