import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { apiFetch } from '../api/client';
import { MigrationDashboardPage } from './MigrationDashboardPage';

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {
    ...actual,
    apiFetch: vi.fn(),
  };
});

const mockApiFetch = vi.mocked(apiFetch);
const settings = { apiBase: '', username: 'zeus', password: 'secret' };

function dashboardPayload(status = 'RUNNING') {
  return {
    status: 'success',
    source: 'cache',
    last_refreshed: '2026-05-17T00:00:00Z',
    warnings: [],
    jobs: [
      {
        job: {
          project: 'demo',
          job_id: '8',
          job_type: 'MIGRATE',
          status,
          current_phase: 'ZDM_DATAPUMP_IMPORT_TGT',
        },
        inventory: {
          project: { name: 'demo', migration_method: 'OFFLINE_LOGICAL' },
        },
      },
      {
        job: {
          project: 'evalonly',
          job_id: '7',
          job_type: 'EVAL',
          status: 'SUCCEEDED',
          current_phase: 'ZDM_VALIDATE_TGT',
        },
        inventory: {
          project: { name: 'evalonly', migration_method: 'OFFLINE_LOGICAL' },
        },
      },
    ],
  };
}

describe('MigrationDashboardPage', () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    mockApiFetch.mockImplementation(async (_settings, path) => {
      if (path === '/jobs') return dashboardPayload();
      if (path === '/jobs?refresh=true') return dashboardPayload('FAILED');
      throw new Error(`Unexpected path ${path}`);
    });
  });

  afterEach(() => {
    cleanup();
  });

  test('renders KPI counts and job table from enriched GET /jobs records', async () => {
    render(<MigrationDashboardPage settings={settings} />);

    expect(await screen.findByText('2')).toBeInTheDocument();
    expect(screen.getByText('Succeeded')).toBeInTheDocument();
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('demo')).toBeInTheDocument();
    expect(screen.getByText('ZDM_DATAPUMP_IMPORT_TGT')).toBeInTheDocument();
    expect(screen.getByText('Source: cache')).toBeInTheDocument();
  });

  test('refreshes jobs through the backend refresh query', async () => {
    const user = userEvent.setup();
    render(<MigrationDashboardPage settings={settings} />);

    await screen.findByText('RUNNING');
    await user.click(screen.getByRole('button', { name: 'Refresh Jobs' }));

    expect(await screen.findByText('FAILED')).toBeInTheDocument();
    expect(mockApiFetch).toHaveBeenCalledWith(settings, '/jobs?refresh=true');
  });

  test('fails visibly for raw snapshot rows instead of rendering a partial dashboard', async () => {
    mockApiFetch.mockImplementation(async (_settings, path) => {
      if (path === '/jobs') {
        return {
          status: 'success',
          source: 'snapshot',
          last_refreshed: null,
          warnings: [],
          jobs: [{ job_id: '8', job_type: 'MIGRATE', status: 'RUNNING' }],
        };
      }
      throw new Error(`Unexpected path ${path}`);
    });

    render(<MigrationDashboardPage settings={settings} />);

    expect(await screen.findByText(/GET \/jobs API contract error/)).toBeInTheDocument();
    expect(screen.queryByText('MIGRATE')).not.toBeInTheDocument();
  });
});
