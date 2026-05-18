import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { apiFetch } from '../api/client';
import { ResponseFilesPage } from './ResponseFilesPage';

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
      default_medium: 'OSS',
      response_file: {
        fields: {
          SOURCE_HOST: { label: 'Source host', control: 'text' },
          USER_FIELD: { label: 'User field', control: 'text' },
        },
      },
    },
  },
  navigation: { groups: [] },
  resolved_context: null,
};

const projects = {
  demo: {
    name: 'demo',
    rsp: null,
    source_connection: 'source_db',
    target_connection: 'target_db',
    migration_method: 'OFFLINE_LOGICAL',
  },
};

const resolvedMetadata = {
  ...baseMetadata,
  resolved_context: {
    project: 'demo',
    migration_method: 'OFFLINE_LOGICAL',
    medium: 'OSS',
    run_type: '',
    decision_input_values: {},
    visible_response_fields: [
      'MIGRATION_METHOD',
      'DATA_TRANSFER_MEDIUM',
      'SOURCE_HOST',
      'USER_FIELD',
    ],
    required_response_fields: [],
    derived_response_values: { SOURCE_HOST: 'source.example.com' },
    response_sections: {},
    medium_sections: {},
    media_options: [
      {
        value: 'OSS',
        label: 'OSS',
        enabled: true,
        disabled_reason: '',
        guidance: 'Use object storage.',
      },
      {
        value: 'NFS',
        label: 'NFS',
        enabled: false,
        disabled_reason: 'NFS is not available for this project.',
        guidance: '',
      },
    ],
    additional_default_rows: [
      { key: 'RUNCPATREMOTELY', value: 'TRUE' },
    ],
    job_sections: {},
  },
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

describe('ResponseFilesPage resolved metadata rendering', () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    mockApiFetch.mockImplementation(async (_settings, path) => {
      if (path === '/metadata/frontend') return baseMetadata;
      if (path === '/projects') return projects;
      if (path.startsWith('/metadata/frontend?')) return resolvedMetadata;
      throw new Error(`Unexpected path ${path}`);
    });
  });

  afterEach(() => {
    cleanup();
  });

  test('shows derived response values without rendering them as editable fields', async () => {
    render(<ResponseFilesPage settings={settings} />);

    expect(await screen.findByText(/source.example.com/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Source host')).not.toBeInTheDocument();
    expect(screen.getByLabelText('User field')).toBeInTheDocument();
  });

  test('disables unavailable media options and surfaces their reason', async () => {
    render(<ResponseFilesPage settings={settings} />);

    const unavailableOption = await screen.findByRole('option', { name: 'NFS' });

    expect(unavailableOption).toBeDisabled();
    expect(screen.getByText('NFS is not available for this project.')).toBeInTheDocument();
  });

  test('prefills profile additional default rows', async () => {
    render(<ResponseFilesPage settings={settings} />);

    expect(await screen.findByLabelText(/^Additional parameters/)).toHaveValue('RUNCPATREMOTELY=TRUE');
  });

  test('rejects resolved metadata for a different project context', async () => {
    mockApiFetch.mockImplementation(async (_settings, path) => {
      if (path === '/metadata/frontend') return baseMetadata;
      if (path === '/projects') return projects;
      if (path.startsWith('/metadata/frontend?')) {
        return {
          ...resolvedMetadata,
          resolved_context: {
            ...resolvedMetadata.resolved_context,
            project: 'other',
          },
        };
      }
      throw new Error(`Unexpected path ${path}`);
    });

    render(<ResponseFilesPage settings={settings} />);

    expect(await screen.findByText(/resolved_context.project must match requested project/)).toBeInTheDocument();
    expect(screen.queryByLabelText('User field')).not.toBeInTheDocument();
  });

  test('ignores stale preview responses after editable values change', async () => {
    const user = userEvent.setup();
    const preview = deferred<unknown>();
    mockApiFetch.mockImplementation(async (_settings, path) => {
      if (path === '/metadata/frontend') return baseMetadata;
      if (path === '/projects') return projects;
      if (path.startsWith('/metadata/frontend?')) return resolvedMetadata;
      if (path === '/responsefiles/preview') return preview.promise;
      throw new Error(`Unexpected path ${path}`);
    });

    render(<ResponseFilesPage settings={settings} />);

    await screen.findByLabelText('User field');
    await user.click(screen.getByRole('button', { name: 'Preview' }));
    await user.type(screen.getByLabelText('User field'), 'changed');

    preview.resolve({
      status: 'planned',
      project: 'demo',
      filename: 'demo.rsp',
      lines: ['MIGRATION_METHOD=OFFLINE_LOGICAL', 'USER_FIELD=old'],
      migration_method: 'OFFLINE_LOGICAL',
    });

    expect(await screen.findByRole('button', { name: 'Preview' })).toBeEnabled();
    expect(screen.queryByText('Preview planned for demo.rsp.')).not.toBeInTheDocument();
    expect(screen.queryByText(/USER_FIELD=old/)).not.toBeInTheDocument();
  });
});
