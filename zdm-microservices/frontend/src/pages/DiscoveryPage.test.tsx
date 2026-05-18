import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { apiFetch } from '../api/client';
import { DiscoveryPage } from './DiscoveryPage';

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {
    ...actual,
    apiFetch: vi.fn(),
  };
});

const mockApiFetch = vi.mocked(apiFetch);
const settings = { apiBase: '', username: 'zeus', password: 'secret' };

function dbConnection(name: string) {
  return {
    name,
    host: `${name}.example.com`,
    port: 1521,
    service_name: 'ORCLPDB1',
    db_type: 'ORACLE',
    connection_role: 'source' as const,
    protocol: 'TCP' as const,
    allow_tls_without_wallet: false,
  };
}

function discoveryResponse(connectionName: string) {
  return {
    status: 'success',
    file: `${connectionName}.json`,
    snapshot: {
      connection_name: connectionName,
      extras: {
        logical_common: {
          db_profiles: [`profile for ${connectionName}`],
        },
      },
    },
  };
}

function discoveryRunResponse(connectionName: string) {
  return {
    status: 'success',
    message: 'Discovery completed.',
    snapshot: {
      connection_name: connectionName,
      extras: {
        logical_common: {
          db_profiles: [`profile for ${connectionName}`],
        },
      },
    },
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

async function renderLoadedDiscoveryPage() {
  mockApiFetch.mockResolvedValueOnce({
    source_a: dbConnection('source_a'),
    source_b: dbConnection('source_b'),
  });

  render(<DiscoveryPage settings={settings} />);

  await screen.findByRole('option', { name: 'source_a' });
}

describe('DiscoveryPage stale-state safety', () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  test('clears displayed snapshot and stale notices when the selected connection changes', async () => {
    const user = userEvent.setup();
    await renderLoadedDiscoveryPage();

    await user.selectOptions(screen.getByLabelText('Connection'), 'source_a');
    mockApiFetch.mockResolvedValueOnce(discoveryResponse('source_a'));
    await user.click(screen.getByRole('button', { name: 'Load latest' }));

    expect(await screen.findByText(/profile for source_a/)).toBeInTheDocument();
    expect(screen.getByText('Loaded latest discovery snapshot.')).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Connection'), 'source_b');

    expect(screen.queryByText(/profile for source_a/)).not.toBeInTheDocument();
    expect(screen.queryByText('Loaded latest discovery snapshot.')).not.toBeInTheDocument();
    expect(screen.getByText('Select a connection and load or run discovery.')).toBeInTheDocument();
  });

  test('ignores stale load-latest responses after a newer load starts', async () => {
    const user = userEvent.setup();
    const firstLoad = deferred<unknown>();
    const secondLoad = deferred<unknown>();
    await renderLoadedDiscoveryPage();

    await user.selectOptions(screen.getByLabelText('Connection'), 'source_a');
    mockApiFetch.mockReturnValueOnce(firstLoad.promise);
    await user.click(screen.getByRole('button', { name: 'Load latest' }));

    await user.selectOptions(screen.getByLabelText('Connection'), 'source_b');
    mockApiFetch.mockReturnValueOnce(secondLoad.promise);
    await user.click(screen.getByRole('button', { name: 'Load latest' }));

    firstLoad.resolve(discoveryResponse('source_a'));
    await waitFor(() => {
      expect(screen.queryByText(/profile for source_a/)).not.toBeInTheDocument();
      expect(screen.queryByText('Loaded latest discovery snapshot.')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Working...' })).toBeDisabled();
    });

    secondLoad.resolve(discoveryResponse('source_b'));

    expect(await screen.findByText(/profile for source_b/)).toBeInTheDocument();
    expect(screen.queryByText(/profile for source_a/)).not.toBeInTheDocument();
  });

  test('ignores stale discovery completion after the connection changes and clears password', async () => {
    const user = userEvent.setup();
    const run = deferred<unknown>();
    await renderLoadedDiscoveryPage();

    await user.selectOptions(screen.getByLabelText('Connection'), 'source_a');
    await user.type(screen.getByLabelText('DB username'), 'system');
    await user.type(screen.getByLabelText('DB password'), 'oracle');
    mockApiFetch.mockReturnValueOnce(run.promise);
    await user.click(screen.getByRole('button', { name: 'Run discovery' }));

    await user.selectOptions(screen.getByLabelText('Connection'), 'source_b');
    run.resolve(discoveryRunResponse('source_a'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Run discovery' })).toBeEnabled();
    });
    expect(screen.queryByText(/profile for source_a/)).not.toBeInTheDocument();
    expect(screen.queryByText('Discovery completed.')).not.toBeInTheDocument();
    expect(screen.getByLabelText('DB password')).toHaveValue('');
  });

  test('does not let stale discovery completion clear a newer password', async () => {
    const user = userEvent.setup();
    const run = deferred<unknown>();
    await renderLoadedDiscoveryPage();

    await user.selectOptions(screen.getByLabelText('Connection'), 'source_a');
    await user.type(screen.getByLabelText('DB username'), 'system');
    await user.type(screen.getByLabelText('DB password'), 'oracle');
    mockApiFetch.mockReturnValueOnce(run.promise);
    await user.click(screen.getByRole('button', { name: 'Run discovery' }));

    await user.selectOptions(screen.getByLabelText('Connection'), 'source_b');
    await user.type(screen.getByLabelText('DB password'), 'new-secret');
    run.resolve(discoveryRunResponse('source_a'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Run discovery' })).toBeEnabled();
    });
    expect(screen.queryByText(/profile for source_a/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('DB password')).toHaveValue('new-secret');
  });

  test('clears stale connection options and page state while reloading connections for new settings', async () => {
    const user = userEvent.setup();
    const reload = deferred<unknown>();
    mockApiFetch.mockResolvedValueOnce({
      source_a: dbConnection('source_a'),
    });
    const { rerender } = render(<DiscoveryPage settings={settings} />);

    await screen.findByRole('option', { name: 'source_a' });
    await user.selectOptions(screen.getByLabelText('Connection'), 'source_a');
    mockApiFetch.mockResolvedValueOnce(discoveryResponse('source_a'));
    await user.click(screen.getByRole('button', { name: 'Load latest' }));
    expect(await screen.findByText(/profile for source_a/)).toBeInTheDocument();

    mockApiFetch.mockReturnValueOnce(reload.promise);
    rerender(
      <DiscoveryPage
        settings={{ ...settings, apiBase: 'https://new-zeus.example.com' }}
      />,
    );

    expect(screen.queryByRole('option', { name: 'source_a' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Connection')).toHaveValue('');
    expect(screen.queryByText(/profile for source_a/)).not.toBeInTheDocument();
    expect(screen.queryByText('Loaded latest discovery snapshot.')).not.toBeInTheDocument();

    reload.reject(new Error('connection reload failed'));

    expect(await screen.findByText('connection reload failed')).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'source_a' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Connection')).toHaveValue('');
  });
});
