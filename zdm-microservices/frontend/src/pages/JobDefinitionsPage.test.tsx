import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { apiFetch } from '../api/client';
import { JobDefinitionsPage } from './JobDefinitionsPage';

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {
    ...actual,
    apiFetch: vi.fn(),
  };
});

const mockApiFetch = vi.mocked(apiFetch);
const settings = { apiBase: '', username: 'zeus', password: 'secret' };

const baseMetadata = {
  status: 'success',
  environments: {},
  migration_profiles: {
    OFFLINE_LOGICAL: {
      method: 'OFFLINE_LOGICAL',
      job_submission: {
        fields: ['sourcedb'],
        run_controls: {
          advisor_mode: {
            label: 'Advisor mode',
            control: 'select',
            options: ['NONE', 'CPAT'],
            default: 'NONE',
          },
          listphases: {
            label: 'List phases',
            control: 'checkbox',
            default: false,
          },
        },
      },
    },
  },
  navigation: { groups: [] },
  resolved_context: null,
};

function project(name: string) {
  return {
    name,
    rsp: `${name}.rsp`,
    source_connection: 'source_db',
    target_connection: 'target_db',
    migration_method: 'OFFLINE_LOGICAL',
  };
}

function savedJob(name: string, projectName: string, runType: 'EVAL' | 'MIGRATE' = 'EVAL') {
  return {
    name,
    project: projectName,
    run_type: runType,
    rsp: `${projectName}.rsp`,
    job_parameters: { sourcedb: 'SRCDB' },
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

function savedJobSaveResponse(name: string, projectName: string) {
  return {
    status: 'success',
    message: 'Saved job definition.',
    job: savedJob(name, projectName),
  };
}

describe('JobDefinitionsPage API contract behavior', () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    mockApiFetch.mockImplementation(async (_settings, path) => {
      if (path === '/metadata/frontend') return baseMetadata;
      if (path === '/projects') return { demo: project('demo') };
      if (path === '/saved-jobs') return {};
      throw new Error(`Unexpected path ${path}`);
    });
  });

  afterEach(() => {
    cleanup();
  });

  test('fails visibly when job metadata contains an unsupported run control type', async () => {
    mockApiFetch.mockImplementation(async (_settings, path) => {
      if (path === '/metadata/frontend') {
        return {
          ...baseMetadata,
          migration_profiles: {
            OFFLINE_LOGICAL: {
              method: 'OFFLINE_LOGICAL',
              job_submission: {
                fields: ['sourcedb'],
                run_controls: {
                  advisor_mode: {
                    label: 'Bad advisor mode',
                    control: 'radio',
                    options: ['NONE', 'CPAT'],
                  },
                },
              },
            },
          },
        };
      }
      if (path === '/projects') return { demo: project('demo') };
      if (path === '/saved-jobs') return {};
      throw new Error(`Unexpected path ${path}`);
    });

    render(<JobDefinitionsPage settings={settings} />);

    expect(await screen.findByText(/GET \/metadata\/frontend API contract error/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Bad advisor mode')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save job definition' })).toBeDisabled();
  });

  test('fails visibly when multiselect metadata contains an invalid default', async () => {
    mockApiFetch.mockImplementation(async (_settings, path) => {
      if (path === '/metadata/frontend') {
        return {
          ...baseMetadata,
          migration_profiles: {
            OFFLINE_LOGICAL: {
              method: 'OFFLINE_LOGICAL',
              job_submission: {
                fields: ['sourcedb'],
                run_controls: {
                  ignore: {
                    label: 'Ignore checks',
                    control: 'multiselect',
                    options: ['ALL'],
                    default: ['ALL', 3],
                  },
                },
              },
            },
          },
        };
      }
      if (path === '/projects') return { demo: project('demo') };
      if (path === '/saved-jobs') return {};
      throw new Error(`Unexpected path ${path}`);
    });

    render(<JobDefinitionsPage settings={settings} />);

    expect(await screen.findByText(/GET \/metadata\/frontend API contract error/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Ignore checks')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save job definition' })).toBeDisabled();
  });

  test('resets the selected project when reloaded projects no longer contain the previous selection', async () => {
    mockApiFetch.mockImplementation(async (requestSettings, path) => {
      if (path === '/metadata/frontend') return baseMetadata;
      if (path === '/projects') {
        return requestSettings.apiBase === 'https://new-zeus.example.com'
          ? { next: project('next') }
          : { demo: project('demo') };
      }
      if (path === '/saved-jobs') return {};
      throw new Error(`Unexpected path ${path}`);
    });
    const { rerender } = render(<JobDefinitionsPage settings={settings} />);

    expect(await screen.findByLabelText('sourcedb')).toBeInTheDocument();
    expect(screen.getByLabelText('Project')).toHaveValue('demo');

    rerender(
      <JobDefinitionsPage
        settings={{ ...settings, apiBase: 'https://new-zeus.example.com' }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText('Project')).toHaveValue('next');
    });
    expect(screen.queryByRole('option', { name: 'demo' })).not.toBeInTheDocument();
  });

  test('saves a canonical job definition payload and validates the save response', async () => {
    const user = userEvent.setup();
    const postCalls: Array<{ body?: string }> = [];
    mockApiFetch.mockImplementation(async (_settings, path, options) => {
      if (path === '/metadata/frontend') return baseMetadata;
      if (path === '/projects') return { demo: project('demo') };
      if (path === '/saved-jobs' && options?.method === 'POST') {
        postCalls.push({ body: String(options.body) });
        return savedJobSaveResponse('demo_eval', 'demo');
      }
      if (path === '/saved-jobs') return {};
      throw new Error(`Unexpected path ${path}`);
    });

    render(<JobDefinitionsPage settings={settings} />);

    await user.type(await screen.findByLabelText('sourcedb'), 'SRCDB');
    await user.click(screen.getByRole('button', { name: 'Save job definition' }));

    await screen.findByText('Saved job definition.');
    expect(postCalls).toHaveLength(1);
    expect(JSON.parse(postCalls[0].body || '')).toEqual({
      name: 'demo_eval',
      project: 'demo',
      rsp: 'demo.rsp',
      run_type: 'EVAL',
      job_parameters: { sourcedb: 'SRCDB' },
      advisor_mode: 'NONE',
      flow_control: 'NONE',
      flow_phase: '',
      genfixup: '',
      ignore: null,
      schedule: '',
      listphases: false,
      custom_args: null,
    });
  });

  test('clears job parameters when the selected project changes', async () => {
    const user = userEvent.setup();
    const postCalls: Array<{ body?: string }> = [];
    mockApiFetch.mockImplementation(async (_settings, path, options) => {
      if (path === '/metadata/frontend') return baseMetadata;
      if (path === '/projects') {
        return {
          demo: project('demo'),
          next: project('next'),
        };
      }
      if (path === '/saved-jobs' && options?.method === 'POST') {
        postCalls.push({ body: String(options.body) });
        return savedJobSaveResponse('next_eval', 'next');
      }
      if (path === '/saved-jobs') return {};
      throw new Error(`Unexpected path ${path}`);
    });

    render(<JobDefinitionsPage settings={settings} />);

    await user.type(await screen.findByLabelText('sourcedb'), 'SRCDB');
    await user.selectOptions(screen.getByLabelText('Project'), 'next');
    await waitFor(() => {
      expect(screen.getByLabelText('sourcedb')).toHaveValue('');
    });
    await user.click(screen.getByRole('button', { name: 'Save job definition' }));

    await screen.findByText('Saved job definition.');
    expect(postCalls).toHaveLength(1);
    expect(JSON.parse(postCalls[0].body || '')).toMatchObject({
      name: 'next_eval',
      project: 'next',
      rsp: 'next.rsp',
      run_type: 'EVAL',
      job_parameters: {},
    });
  });
});
