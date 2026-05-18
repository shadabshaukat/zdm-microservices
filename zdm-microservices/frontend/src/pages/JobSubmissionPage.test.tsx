import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { apiFetch } from '../api/client';
import { JobSubmissionPage } from './JobSubmissionPage';

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {
    ...actual,
    apiFetch: vi.fn(),
  };
});

const mockApiFetch = vi.mocked(apiFetch);
const settings = { apiBase: '', username: 'zeus', password: 'secret' };

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

function savedJob(name: string, project: string, runType: 'EVAL' | 'MIGRATE' = 'EVAL') {
  return {
    name,
    project,
    run_type: runType,
    rsp: `${project}.rsp`,
    job_parameters: { sourcedb: project.toUpperCase() },
    advisor_mode: 'NONE',
    flow_control: null,
    flow_phase: null,
    genfixup: null,
    ignore: null,
    schedule: null,
    listphases: false,
    custom_args: null,
  };
}

describe('JobSubmissionPage saved job state', () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    mockApiFetch.mockImplementation(async (_settings, path) => {
      if (path === '/saved-jobs') return { demo_eval: savedJob('demo_eval', 'demo') };
      throw new Error(`Unexpected path ${path}`);
    });
  });

  afterEach(() => {
    cleanup();
  });

  test('resets the selected saved job when a reload removes the previous selection', async () => {
    mockApiFetch.mockImplementation(async (requestSettings, path) => {
      if (path === '/saved-jobs') {
        return requestSettings.apiBase === 'https://new-zeus.example.com'
          ? { next_eval: savedJob('next_eval', 'next') }
          : { demo_eval: savedJob('demo_eval', 'demo') };
      }
      throw new Error(`Unexpected path ${path}`);
    });
    const { rerender } = render(<JobSubmissionPage settings={settings} />);

    expect(await screen.findByLabelText('Saved job definitions')).toHaveValue('demo_eval');

    rerender(
      <JobSubmissionPage
        settings={{ ...settings, apiBase: 'https://new-zeus.example.com' }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText('Saved job definitions')).toHaveValue('next_eval');
    });
    expect(screen.queryByRole('option', { name: 'demo_eval' })).not.toBeInTheDocument();
  });

  test('ignores stale run responses after selecting another saved job', async () => {
    const user = userEvent.setup();
    const run = deferred<unknown>();
    mockApiFetch.mockImplementation(async (_settings, path, options) => {
      if (path === '/saved-jobs') {
        return {
          demo_eval: savedJob('demo_eval', 'demo'),
          next_eval: savedJob('next_eval', 'next'),
        };
      }
      if (path === '/jobs' && options?.method === 'POST') return run.promise;
      throw new Error(`Unexpected path ${path}`);
    });

    render(<JobSubmissionPage settings={settings} />);

    await screen.findByText(/"project": "demo"/);
    await user.click(screen.getByRole('button', { name: 'Preview command' }));
    await user.selectOptions(screen.getByLabelText('Saved job definitions'), 'next_eval');
    run.resolve({
      status: 'planned',
      script_path: '/tmp/demo.sh',
      command: ['zdmcli migrate database -rsp demo.rsp'],
      dry_run: true,
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Preview command' })).toBeEnabled();
    });
    expect(screen.getByText(/"project": "next"/)).toBeInTheDocument();
    expect(screen.queryByText('Command preview planned.')).not.toBeInTheDocument();
    expect(screen.queryByText(/demo\.rsp/)).not.toBeInTheDocument();
  });

  test('clears old submission output when reload selects a different saved job', async () => {
    const user = userEvent.setup();
    mockApiFetch.mockImplementation(async (requestSettings, path, options) => {
      if (path === '/saved-jobs') {
        return requestSettings.apiBase === 'https://new-zeus.example.com'
          ? { next_eval: savedJob('next_eval', 'next') }
          : { demo_eval: savedJob('demo_eval', 'demo') };
      }
      if (path === '/jobs' && options?.method === 'POST') {
        return {
          status: 'planned',
          script_path: '/tmp/demo.sh',
          command: ['zdmcli migrate database -rsp demo.rsp'],
          dry_run: true,
        };
      }
      throw new Error(`Unexpected path ${path}`);
    });
    const { rerender } = render(<JobSubmissionPage settings={settings} />);

    await screen.findByText(/"project": "demo"/);
    await user.click(screen.getByRole('button', { name: 'Preview command' }));
    expect(await screen.findByText('Command preview planned.')).toBeInTheDocument();
    expect(screen.getAllByText(/demo\.rsp/).length).toBeGreaterThan(0);

    rerender(
      <JobSubmissionPage
        settings={{ ...settings, apiBase: 'https://new-zeus.example.com' }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText('Saved job definitions')).toHaveValue('next_eval');
    });
    expect(screen.getByText(/"project": "next"/)).toBeInTheDocument();
    expect(screen.queryByText('Command preview planned.')).not.toBeInTheDocument();
    expect(screen.queryByText(/demo\.rsp/)).not.toBeInTheDocument();
  });
});
