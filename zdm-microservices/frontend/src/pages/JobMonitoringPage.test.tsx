import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { apiFetch } from '../api/client';
import { JobMonitoringPage } from './JobMonitoringPage';

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {
    ...actual,
    apiFetch: vi.fn(),
  };
});

const mockApiFetch = vi.mocked(apiFetch);
const settings = { apiBase: '', username: 'zeus', password: 'secret' };

describe('JobMonitoringPage', () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    mockApiFetch.mockImplementation(async (_settings, path) => {
      if (path === '/jobs/ids') return { job_ids: ['8', '9'] };
      if (path === '/jobs/8') return { status: 'success', output: 'Job 8 is RUNNING' };
      throw new Error(`Unexpected path ${path}`);
    });
  });

  afterEach(() => {
    cleanup();
  });

  test('loads recent job ids, queries a selected job, and renders the backend output', async () => {
    const user = userEvent.setup();
    render(<JobMonitoringPage settings={settings} />);

    await user.selectOptions(await screen.findByLabelText('Recent jobs'), '8');
    await user.click(screen.getByRole('button', { name: 'Query' }));

    expect(await screen.findByText(/Job 8 is RUNNING/)).toBeInTheDocument();
    expect(mockApiFetch).toHaveBeenCalledWith(settings, '/jobs/8');
  });

  test('loads job logs for the queried job and reads a selected log file', async () => {
    const user = userEvent.setup();
    mockApiFetch.mockImplementation(async (_settings, path, options) => {
      if (path === '/jobs/ids') return { job_ids: ['8'] };
      if (path === '/jobs/8') return { status: 'success', output: 'Job 8 is RUNNING' };
      if (path === '/joblogs?job_id=8') {
        return {
          status: 'success',
          job_id: '8',
          logs: [
            {
              name: 'zdm_8.log',
              size_bytes: 42,
              modified_time: '2026-05-17T00:00:00+00:00',
            },
          ],
        };
      }
      if (path === '/joblogs/read' && options?.method === 'POST') {
        return {
          status: 'success',
          job_id: '8',
          name: 'zdm_8.log',
          content: 'log content for job 8',
        };
      }
      throw new Error(`Unexpected path ${path}`);
    });

    render(<JobMonitoringPage settings={settings} />);

    await user.selectOptions(await screen.findByLabelText('Recent jobs'), '8');
    await user.click(screen.getByRole('button', { name: 'Query' }));
    await user.click(await screen.findByRole('button', { name: 'View zdm_8.log' }));

    expect(await screen.findByText(/log content for job 8/)).toBeInTheDocument();
    expect(mockApiFetch).toHaveBeenCalledWith(settings, '/joblogs?job_id=8');
    expect(mockApiFetch).toHaveBeenCalledWith(settings, '/joblogs/read', {
      method: 'POST',
      body: JSON.stringify({ job_id: '8', name: 'zdm_8.log' }),
    });
  });

  test('shows a visible contract error for malformed job query payloads', async () => {
    const user = userEvent.setup();
    mockApiFetch.mockImplementation(async (_settings, path) => {
      if (path === '/jobs/ids') return { job_ids: ['8'] };
      if (path === '/jobs/8') return { status: 'success', job: { job_id: '8' } };
      throw new Error(`Unexpected path ${path}`);
    });

    render(<JobMonitoringPage settings={settings} />);

    await user.selectOptions(await screen.findByLabelText('Recent jobs'), '8');
    await user.click(screen.getByRole('button', { name: 'Query' }));

    expect(await screen.findByText(/GET \/jobs\/\{jobid\} API contract error/)).toBeInTheDocument();
    expect(screen.queryByText(/Job 8 is RUNNING/)).not.toBeInTheDocument();
  });
});
