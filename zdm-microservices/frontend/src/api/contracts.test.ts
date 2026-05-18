import { describe, expect, test } from 'vitest';

import { validateHealthResponse } from './client';
import {
  validateDbConnectionsResponse,
  validateDbConnectionWriteResponse,
  validateCredentialWalletsResponse,
  validateDiscoveryLatestResponse,
  validateDiscoveryResponse,
  validateFrontendMetadata,
  validateJobIdsResponse,
  validateJoblogReadResponse,
  validateJoblogsResponse,
  validateJobQueryResponse,
  validateJobsDashboardResponse,
  validateProjectWriteResponse,
  validateProjectsResponse,
  validateRunJobResponse,
  validateSavedJobSaveResponse,
  validateSavedJobsResponse,
  validateResponseFilePreviewResponse,
  validateResponseFileWriteResponse,
  validateTlsWalletUploadResponse,
  validateWalletCommandResponse,
} from './contracts';

describe('validateProjectsResponse', () => {
  test('accepts project records keyed by matching name', () => {
    const payload = {
      demo: {
        name: 'demo',
        rsp: null,
        source_connection: 'src',
        target_connection: 'tgt',
        migration_method: 'OFFLINE_LOGICAL',
      },
    };

    expect(validateProjectsResponse(payload)).toEqual(payload);
  });

  test('rejects arrays', () => {
    expect(() => validateProjectsResponse([])).toThrow(
      'GET /projects API contract error:',
    );
  });

  test('rejects records whose name does not match the object key', () => {
    expect(() =>
      validateProjectsResponse({
        demo: {
          name: 'other',
          rsp: null,
          source_connection: 'src',
          target_connection: 'tgt',
        },
      }),
    ).toThrow('name must match');
  });

  test('rejects extra fields and malformed job references', () => {
    expect(() =>
      validateProjectsResponse({
        demo: {
          name: 'demo',
          source_connection: 'src',
          target_connection: 'tgt',
        },
      }),
    ).toThrow('missing rsp');

    expect(() =>
      validateProjectsResponse({
        demo: {
          name: 'demo',
          rsp: null,
          source_connection: 'src',
          target_connection: 'tgt',
          owner: 'unexpected',
        },
      }),
    ).toThrow('unexpected owner');

    expect(() =>
      validateProjectsResponse({
        demo: {
          name: 'demo',
          rsp: null,
          source_connection: 'src',
          target_connection: 'tgt',
          jobs: { migrate: [8] },
        },
      }),
    ).toThrow('jobs.migrate must be a list of strings');
  });
});

describe('validateProjectWriteResponse', () => {
  test('accepts the exact project write response', () => {
    const payload = {
      status: 'success',
      message: 'Project saved.',
      project: {
        name: 'demo',
        rsp: null,
        source_connection: 'src',
        target_connection: 'tgt',
        migration_method: 'OFFLINE_LOGICAL',
      },
    };

    expect(validateProjectWriteResponse(payload)).toEqual(payload);
  });

  test('rejects malformed project write responses', () => {
    expect(() =>
      validateProjectWriteResponse({
        status: 'success',
        message: 'Project saved.',
        project: {
          name: 'other',
          rsp: null,
          source_connection: 'src',
          target_connection: 'tgt',
        },
        extra: true,
      }),
    ).toThrow('POST /projects API contract error:');

    expect(() =>
      validateProjectWriteResponse({
        status: 'success',
        message: 'Project saved.',
        project: {
          name: '',
          rsp: null,
          source_connection: 'src',
          target_connection: 'tgt',
        },
      }),
    ).toThrow('project.name must be a non-empty string');

    expect(() =>
      validateProjectWriteResponse({
        status: 'success',
        message: 'Project saved.',
        project: {
          name: 'other',
          rsp: null,
          source_connection: 'src',
          target_connection: 'tgt',
        },
      }, 'demo'),
    ).toThrow('project.name must match expected name');
  });
});

describe('validateDbConnectionsResponse', () => {
  test('accepts strict db connection records keyed by matching name', () => {
    const payload = {
      source_db: {
        name: 'source_db',
        host: 'source.example.com',
        port: 1521,
        service_name: 'ORCLPDB1',
        db_type: 'ORACLE',
        connection_role: 'source',
        protocol: 'TCP',
        allow_tls_without_wallet: false,
      },
      target_db: {
        name: 'target_db',
        host: 'target.example.com',
        port: 2484,
        service_name: 'ORCLPDB2',
        db_type: 'ORACLE',
        connection_role: 'target',
        protocol: 'TCPS',
        allow_tls_without_wallet: true,
        tls_wallet_uploaded_dir: '/wallets/target',
      },
    };

    expect(validateDbConnectionsResponse(payload)).toEqual(payload);
  });

  test('rejects extra db connection fields', () => {
    expect(() =>
      validateDbConnectionsResponse({
        source_db: {
          name: 'source_db',
          host: 'source.example.com',
          port: 1521,
          service_name: 'ORCLPDB1',
          db_type: 'ORACLE',
          connection_role: 'source',
          protocol: 'TCP',
          allow_tls_without_wallet: false,
          username: 'leak',
        },
      }),
    ).toThrow('unexpected username');
  });
});

describe('validateDbConnectionWriteResponse', () => {
  test('accepts the exact db connection write response', () => {
    const payload = {
      status: 'success',
      message: 'Connection saved.',
      connection: {
        name: 'source_db',
        host: 'source.example.com',
        port: 1521,
        service_name: 'ORCLPDB1',
        db_type: 'ORACLE_DATABASE',
        connection_role: 'source',
        protocol: 'TCP',
        allow_tls_without_wallet: false,
      },
    };

    expect(validateDbConnectionWriteResponse(payload)).toEqual(payload);
  });

  test('rejects malformed db connection write responses', () => {
    expect(() =>
      validateDbConnectionWriteResponse({
        status: 'success',
        message: 'Connection saved.',
        connection: {
          name: 'source_db',
          host: 'source.example.com',
          port: '1521',
          service_name: 'ORCLPDB1',
          db_type: 'ORACLE_DATABASE',
          connection_role: 'source',
          protocol: 'TCP',
          allow_tls_without_wallet: false,
        },
      }),
    ).toThrow('connection.port must be an integer');

    expect(() =>
      validateDbConnectionWriteResponse({
        status: 'success',
        message: 'Connection saved.',
        connection: {
          name: 'source_db',
          host: 'source.example.com',
          port: 1521,
          service_name: 'ORCLPDB1',
          db_type: 'ORACLE_DATABASE',
          connection_role: 'source',
          protocol: 'TCP',
          allow_tls_without_wallet: false,
          username: 'leak',
        },
      }),
    ).toThrow('unexpected username');

    expect(() =>
      validateDbConnectionWriteResponse({
        status: 'success',
        message: 'Connection saved.',
        connection: {
          name: 'other_db',
          host: 'source.example.com',
          port: 1521,
          service_name: 'ORCLPDB1',
          db_type: 'ORACLE_DATABASE',
          connection_role: 'source',
          protocol: 'TCP',
          allow_tls_without_wallet: false,
        },
      }, 'source_db'),
    ).toThrow('connection.name must match expected name');
  });
});

describe('validateCredentialWalletsResponse', () => {
  test('accepts credential wallet rows', () => {
    const payload = {
      wallets: [
        {
          name: 'app_wallet',
          path: '/opt/zeus/wallets/app_wallet',
          credential_username: 'ADMIN',
        },
        {
          name: 'empty_wallet',
          path: '/opt/zeus/wallets/empty_wallet',
          credential_username: null,
        },
      ],
    };

    expect(validateCredentialWalletsResponse(payload)).toEqual(payload);
  });

  test('rejects malformed credential wallet rows', () => {
    expect(() =>
      validateCredentialWalletsResponse({
        wallets: [
          {
            name: 'app_wallet',
            path: '/opt/zeus/wallets/app_wallet',
            credential_username: 'ADMIN',
            credentials: ['ADMIN'],
          },
        ],
      }),
    ).toThrow('unexpected credentials');

    expect(() =>
      validateCredentialWalletsResponse({
        wallets: [
          {
            name: 'app_wallet',
            path: '/opt/zeus/wallets/app_wallet',
          },
        ],
      }),
    ).toThrow('missing credential_username');
  });
});

describe('validateWalletCommandResponse', () => {
  test('accepts the exact wallet command response', () => {
    const payload = { status: 'success', output: 'wallet command completed' };

    expect(validateWalletCommandResponse(payload, 'POST /wallets/ora-pki')).toEqual(payload);
  });

  test('rejects malformed wallet command responses', () => {
    expect(() =>
      validateWalletCommandResponse(
        { status: 'success', message: 'wallet command completed' },
        'POST /wallets/ora-pki',
      ),
    ).toThrow('POST /wallets/ora-pki API contract error:');

    expect(() =>
      validateWalletCommandResponse(
        { status: 'success', output: 'wallet command completed', path: '/tmp/wallet' },
        'POST /wallets/mkstore-credential',
      ),
    ).toThrow('unexpected path');
  });
});

describe('validateTlsWalletUploadResponse', () => {
  test('accepts the exact TLS wallet upload response', () => {
    const payload = {
      status: 'success',
      message: 'TLS wallet uploaded.',
      path: '/opt/zeus/uploads/wallet.zip',
      wallet_dir: '/opt/zeus/uploads/wallet',
    };

    expect(validateTlsWalletUploadResponse(payload)).toEqual(payload);
  });

  test('rejects malformed TLS wallet upload responses', () => {
    expect(() =>
      validateTlsWalletUploadResponse({
        status: 'success',
        message: 'TLS wallet uploaded.',
        path: '/opt/zeus/uploads/wallet.zip',
      }),
    ).toThrow('missing wallet_dir');

    expect(() =>
      validateTlsWalletUploadResponse({
        status: 'success',
        message: 'TLS wallet uploaded.',
        path: '/opt/zeus/uploads/wallet.zip',
        wallet_dir: '/opt/zeus/uploads/wallet',
        output: 'unexpected',
      }),
    ).toThrow('unexpected output');
  });
});

describe('validateDiscoveryResponse', () => {
  test('accepts exact success payload and returns snapshot', () => {
    const snapshot = { extras: { logical_common: { db_profiles: [] } } };
    const payload = {
      status: 'success',
      message: 'Discovery complete.',
      snapshot,
    };

    expect(validateDiscoveryResponse(payload)).toBe(snapshot);
  });

  test('rejects malformed discovery response', () => {
    expect(() =>
      validateDiscoveryResponse({
        status: 'success',
        message: 'Discovery complete.',
        snapshot: {},
        file: 'unexpected.json',
      }),
    ).toThrow('POST /dbconnections/discover API contract error:');

    expect(() =>
      validateDiscoveryResponse({
        status: 'success',
        message: 'Discovery complete.',
        snapshot: [],
      }),
    ).toThrow('snapshot must be an object');
  });
});

describe('validateDiscoveryLatestResponse', () => {
  test('returns null for exact not_found payload', () => {
    expect(validateDiscoveryLatestResponse({ status: 'not_found' })).toBeNull();
  });

  test('accepts exact success latest payload and returns snapshot', () => {
    const snapshot = { extras: { logical_common: { db_profiles: [{ name: 'OLTP' }] } } };
    const payload = {
      status: 'success',
      file: 'source.discovery.json',
      snapshot,
    };

    expect(validateDiscoveryLatestResponse(payload)).toBe(snapshot);
  });

  test('rejects latest payload with extra keys or missing file/snapshot', () => {
    expect(() =>
      validateDiscoveryLatestResponse({
        status: 'not_found',
        file: 'unexpected.json',
      }),
    ).toThrow('GET /dbconnections/{name}/discovery/latest API contract error:');

    expect(() =>
      validateDiscoveryLatestResponse({
        status: 'success',
        snapshot: {},
      }),
    ).toThrow('missing file');

    expect(() =>
      validateDiscoveryLatestResponse({
        status: 'success',
        file: 'source.discovery.json',
      }),
    ).toThrow('missing snapshot');
  });
});

describe('validateJobsDashboardResponse', () => {
  test('accepts enriched GET /jobs records with job and inventory objects', () => {
    const payload = {
      status: 'success',
      source: 'cache',
      last_refreshed: '2026-05-17T00:00:00Z',
      jobs: [
        {
          job: { job_id: '8', job_type: 'MIGRATE', status: 'RUNNING' },
          inventory: { project: { name: 'demo' } },
        },
      ],
      warnings: [],
    };

    expect(validateJobsDashboardResponse(payload)).toEqual(payload);
  });

  test('rejects raw snapshot rows for GET /jobs', () => {
    const payload = {
      status: 'success',
      source: 'snapshot',
      last_refreshed: null,
      jobs: [{ job_id: '8', job_type: 'MIGRATE' }],
      warnings: [],
    };

    expect(() => validateJobsDashboardResponse(payload)).toThrow(
      'GET /jobs API contract error:',
    );
  });

  test('rejects enriched rows that mix in raw snapshot fields', () => {
    expect(() =>
      validateJobsDashboardResponse({
        status: 'success',
        source: 'cache',
        last_refreshed: null,
        jobs: [{ job: {}, inventory: {}, job_id: '8' }],
        warnings: [],
      }),
    ).toThrow('expected exact top-level keys');
  });
});

describe('validateJobIdsResponse', () => {
  test('accepts the exact job ids response', () => {
    const payload = { job_ids: ['8'] };

    expect(validateJobIdsResponse(payload)).toEqual(payload);
  });

  test('rejects malformed job ids responses', () => {
    expect(() => validateJobIdsResponse(['8'])).toThrow(
      'GET /jobs/ids API contract error:',
    );

    expect(() => validateJobIdsResponse({})).toThrow('expected exact top-level keys');

    expect(() => validateJobIdsResponse({ job_ids: [8] })).toThrow(
      'job_ids must be an array of strings',
    );

    expect(() => validateJobIdsResponse({ job_ids: ['8'], source: 'snapshot' })).toThrow(
      'expected exact top-level keys',
    );
  });
});

describe('validateJobQueryResponse', () => {
  test('accepts the exact job query response', () => {
    const payload = { status: 'success', output: 'job output' };

    expect(validateJobQueryResponse(payload)).toEqual(payload);
  });

  test('rejects malformed job query responses', () => {
    expect(() => validateJobQueryResponse({ status: 'success' })).toThrow(
      'expected exact top-level keys',
    );

    expect(() =>
      validateJobQueryResponse({ status: 'success', output: 'job output', job_id: '8' }),
    ).toThrow('expected exact top-level keys');

    expect(() => validateJobQueryResponse({ status: 'success', output: 8 })).toThrow(
      'output must be a string',
    );
  });
});

describe('validateJoblogsResponse', () => {
  test('accepts the exact job log list response for the requested job', () => {
    const payload = {
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

    expect(validateJoblogsResponse(payload, '8')).toEqual(payload);
  });

  test('rejects malformed job log list responses', () => {
    expect(() => validateJoblogsResponse({ status: 'success', job_id: '9', logs: [] }, '8')).toThrow(
      'job_id must match requested job ID',
    );

    expect(() =>
      validateJoblogsResponse(
        {
          status: 'success',
          job_id: '8',
          logs: [{ name: '', size_bytes: 42, modified_time: '2026-05-17T00:00:00+00:00' }],
        },
        '8',
      ),
    ).toThrow('logs[0].name must be a non-empty string');
  });
});

describe('validateJoblogReadResponse', () => {
  test('accepts the exact job log read response for the requested log', () => {
    const payload = {
      status: 'success',
      job_id: '8',
      name: 'zdm_8.log',
      content: 'log content',
    };

    expect(validateJoblogReadResponse(payload, '8', 'zdm_8.log')).toEqual(payload);
  });

  test('rejects malformed job log read responses', () => {
    expect(() =>
      validateJoblogReadResponse(
        { status: 'success', job_id: '8', name: 'other.log', content: 'log content' },
        '8',
        'zdm_8.log',
      ),
    ).toThrow('name must match requested log name');

    expect(() =>
      validateJoblogReadResponse(
        { status: 'success', job_id: '8', name: 'zdm_8.log', content: ['log content'] },
        '8',
        'zdm_8.log',
      ),
    ).toThrow('content must be a string');
  });
});

describe('validateFrontendMetadata', () => {
  test('accepts the frontend metadata contract', () => {
    const payload = {
      status: 'success',
      environments: {},
      migration_profiles: {},
      navigation: {
        groups: [
          {
            label: 'Database Setup',
            items: [
              {
                label: 'DB Connections',
                section: 'connections',
                path: '/connections',
              },
            ],
          },
        ],
      },
      resolved_context: null,
    };

    expect(validateFrontendMetadata(payload)).toEqual(payload);
  });

  test('accepts empty metadata navigation groups', () => {
    expect(
      validateFrontendMetadata({
        status: 'success',
        environments: {},
        migration_profiles: {},
        navigation: { groups: [] },
        resolved_context: null,
      }).navigation.groups,
    ).toEqual([]);
  });

  test('rejects malformed metadata with the documented endpoint name', () => {
    expect(() => validateFrontendMetadata({})).toThrow(
      'GET /metadata/frontend API contract error:',
    );
  });

  test('rejects malformed metadata navigation groups and items', () => {
    const metadata = {
      status: 'success',
      environments: {},
      migration_profiles: {},
      navigation: {
        groups: [
          {
            label: 'Database Setup',
            items: [
              {
                label: 'DB Connections',
                section: 'connections',
                path: '/connections',
              },
            ],
          },
        ],
      },
      resolved_context: null,
    };

    expect(() =>
      validateFrontendMetadata({
        ...metadata,
        navigation: { groups: [{ label: 'Database Setup', items: [], extra: true }] },
      }),
    ).toThrow('unexpected extra');

    expect(() =>
      validateFrontendMetadata({
        ...metadata,
        navigation: {
          groups: [{ label: 'Database Setup', items: [{ label: 'DB Connections', path: '/connections' }] }],
        },
      }),
    ).toThrow('missing section');

    expect(() =>
      validateFrontendMetadata({
        ...metadata,
        navigation: {
          groups: [
            {
              label: 'Database Setup',
              items: [{ label: 'DB Connections', section: 'connections', path: '//evil.example' }],
            },
          ],
        },
      }),
    ).toThrow('path must be an app path');
  });
});

describe('validateResponseFilePreviewResponse', () => {
  test('accepts the exact planned response file preview contract', () => {
    const payload = {
      status: 'planned',
      project: 'demo',
      filename: 'demo.rsp',
      lines: ['MIGRATION_METHOD=OFFLINE_LOGICAL'],
      migration_method: 'OFFLINE_LOGICAL',
    };

    expect(validateResponseFilePreviewResponse(
      payload,
      'demo',
      'OFFLINE_LOGICAL',
    )).toEqual(payload);
  });

  test('rejects malformed preview responses', () => {
    expect(() =>
      validateResponseFilePreviewResponse({
        status: 'planned',
        project: 'demo',
        filename: 'demo.rsp',
        lines: ['MIGRATION_METHOD=OFFLINE_LOGICAL'],
        migration_method: 'OFFLINE_LOGICAL',
        extra: true,
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('POST /responsefiles/preview API contract error:');

    expect(() =>
      validateResponseFilePreviewResponse({
        status: 'success',
        project: 'demo',
        filename: 'demo.rsp',
        lines: ['MIGRATION_METHOD=OFFLINE_LOGICAL'],
        migration_method: 'OFFLINE_LOGICAL',
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('status must be planned');

    expect(() =>
      validateResponseFilePreviewResponse({
        status: 'planned',
        project: 'other',
        filename: 'demo.rsp',
        lines: ['MIGRATION_METHOD=OFFLINE_LOGICAL'],
        migration_method: 'OFFLINE_LOGICAL',
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('project must match expected project');

    expect(() =>
      validateResponseFilePreviewResponse({
        status: 'planned',
        project: 'demo',
        filename: 'demo.rsp',
        lines: ['MIGRATION_METHOD=OFFLINE_LOGICAL'],
        migration_method: 'ONLINE_LOGICAL',
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('migration_method must match expected method');

    expect(() =>
      validateResponseFilePreviewResponse({
        status: 'planned',
        project: 'demo',
        filename: '../demo.rsp',
        lines: ['MIGRATION_METHOD=OFFLINE_LOGICAL'],
        migration_method: 'OFFLINE_LOGICAL',
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('filename must be a response file name');

    expect(() =>
      validateResponseFilePreviewResponse({
        status: 'planned',
        project: 'demo',
        filename: 'demo.rsp',
        lines: ['MIGRATION_METHOD=OFFLINE_LOGICAL', 8],
        migration_method: 'OFFLINE_LOGICAL',
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('lines must be an array of strings');
  });
});

describe('validateResponseFileWriteResponse', () => {
  test('accepts the exact response file write contract with migration method', () => {
    const payload = {
      status: 'success',
      message: 'Response file demo.rsp written successfully',
      project: 'demo',
      path: '/tmp/demo.rsp',
      line_count: 1,
      sha256: 'a'.repeat(64),
      migration_method: 'OFFLINE_LOGICAL',
    };

    expect(validateResponseFileWriteResponse(
      payload,
      'demo',
      'OFFLINE_LOGICAL',
    )).toEqual(payload);
  });

  test('rejects malformed write responses', () => {
    expect(() =>
      validateResponseFileWriteResponse({
        status: 'success',
        message: 'Response file demo.rsp written successfully',
        project: 'demo',
        path: '/tmp/demo.rsp',
        line_count: 1,
        sha256: 'a'.repeat(64),
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('missing migration_method');

    expect(() =>
      validateResponseFileWriteResponse({
        status: 'success',
        message: 'Response file demo.rsp written successfully',
        project: 'demo',
        path: '/tmp/demo.rsp',
        line_count: 1,
        sha256: 'a'.repeat(64),
        migration_method: 'OFFLINE_LOGICAL',
        extra: true,
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('unexpected extra');

    expect(() =>
      validateResponseFileWriteResponse({
        status: 'success',
        message: 'Response file demo.rsp written successfully',
        project: 'other',
        path: '/tmp/demo.rsp',
        line_count: 1,
        sha256: 'a'.repeat(64),
        migration_method: 'OFFLINE_LOGICAL',
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('project must match expected project');

    expect(() =>
      validateResponseFileWriteResponse({
        status: 'success',
        message: 'Response file demo.rsp written successfully',
        project: 'demo',
        path: '/tmp/demo.rsp',
        line_count: 1,
        sha256: 'a'.repeat(64),
        migration_method: 'ONLINE_LOGICAL',
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('migration_method must match expected method');

    expect(() =>
      validateResponseFileWriteResponse({
        status: 'success',
        message: 8,
        project: 'demo',
        path: '/tmp/demo.rsp',
        line_count: 1,
        sha256: 'a'.repeat(64),
        migration_method: 'OFFLINE_LOGICAL',
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('message must be a non-empty string');

    expect(() =>
      validateResponseFileWriteResponse({
        status: 'success',
        message: 'Response file demo.rsp written successfully',
        project: 'demo',
        path: '/tmp/demo.rsp',
        line_count: 0,
        sha256: 'a'.repeat(64),
        migration_method: 'OFFLINE_LOGICAL',
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('line_count must be a positive integer');

    expect(() =>
      validateResponseFileWriteResponse({
        status: 'success',
        message: 'Response file demo.rsp written successfully',
        project: 'demo',
        path: '/tmp/demo.rsp',
        line_count: 1,
        sha256: 'not-a-sha',
        migration_method: 'OFFLINE_LOGICAL',
      }, 'demo', 'OFFLINE_LOGICAL'),
    ).toThrow('sha256 must be 64 lowercase hex characters');
  });
});

function savedJobRecord(overrides: Record<string, unknown> = {}) {
  return {
    name: 'demo_eval',
    project: 'demo',
    run_type: 'EVAL',
    rsp: 'demo.rsp',
    job_parameters: { sourcedb: 'SRCDB' },
    advisor_mode: 'NONE',
    flow_control: 'NONE',
    flow_phase: null,
    genfixup: null,
    ignore: null,
    schedule: null,
    listphases: false,
    custom_args: null,
    ...overrides,
  };
}

describe('validateSavedJobsResponse', () => {
  test('accepts exact saved job records keyed by canonical name', () => {
    const payload = { demo_eval: savedJobRecord() };

    expect(validateSavedJobsResponse(payload)).toEqual(payload);
  });

  test('rejects malformed saved job records and legacy flat parameters', () => {
    expect(() =>
      validateSavedJobsResponse({
        demo_eval: {
          ...savedJobRecord(),
          sourcedb: 'legacy flat parameter',
        },
      }),
    ).toThrow('GET /saved-jobs API contract error:');

    expect(() =>
      validateSavedJobsResponse({
        custom_name: savedJobRecord(),
      }),
    ).toThrow('name must match object key');

    expect(() =>
      validateSavedJobsResponse({
        demo_eval: savedJobRecord({ run_type: 'BAD' }),
      }),
    ).toThrow('run_type must be EVAL or MIGRATE');

    expect(() =>
      validateSavedJobsResponse({
        demo_eval: savedJobRecord({ ignore: 'PATCH_CHECK' }),
      }),
    ).toThrow('ignore must be an array of strings or null');
  });
});

describe('validateSavedJobSaveResponse', () => {
  test('accepts exact saved job save response', () => {
    const payload = {
      status: 'success',
      message: "Job 'demo_eval' saved",
      job: savedJobRecord(),
    };

    expect(validateSavedJobSaveResponse(payload, 'demo_eval')).toEqual(payload);
  });

  test('rejects malformed saved job save responses', () => {
    expect(() =>
      validateSavedJobSaveResponse({
        status: 'success',
        message: "Job 'demo_eval' saved",
        job: savedJobRecord(),
        extra: true,
      }, 'demo_eval'),
    ).toThrow('POST /saved-jobs API contract error:');

    expect(() =>
      validateSavedJobSaveResponse({
        status: 'success',
        message: "Job 'demo_eval' saved",
        job: savedJobRecord({ name: 'demo_migrate', run_type: 'MIGRATE' }),
      }, 'demo_eval'),
    ).toThrow('name must match expected name');
  });
});

describe('validateRunJobResponse', () => {
  test('accepts exact dry-run response', () => {
    const payload = {
      status: 'planned',
      script_path: '/tmp/runjob.sh',
      command: ['zdmcli migrate database'],
      dry_run: true,
    };

    expect(validateRunJobResponse(payload, { dryRun: true })).toEqual(payload);
  });

  test('accepts exact submitted response', () => {
    const payload = {
      status: 'submitted',
      script_path: '/tmp/runjob.sh',
      output: 'Operation scheduled with job ID "22".',
      command: ['zdmcli migrate database'],
      job_id: '22',
    };

    expect(validateRunJobResponse(payload, { dryRun: false })).toEqual(payload);
  });

  test('rejects alternate run job payload shapes', () => {
    expect(() =>
      validateRunJobResponse({
        status: 'success',
        output: 'old shape',
      }, { dryRun: false }),
    ).toThrow('POST /jobs API contract error:');

    expect(() =>
      validateRunJobResponse({
        status: 'planned',
        script_path: '/tmp/runjob.sh',
        command: ['zdmcli migrate database'],
        dry_run: false,
      }, { dryRun: true }),
    ).toThrow('dry_run must be true');

    expect(() =>
      validateRunJobResponse({
        status: 'submitted',
        script_path: '/tmp/runjob.sh',
        output: '',
        command: 'zdmcli migrate database',
        job_id: null,
      }, { dryRun: false }),
    ).toThrow('command must be an array of strings');
  });
});

describe('validateHealthResponse', () => {
  test('accepts an ok health response', () => {
    expect(validateHealthResponse({ status: 'ok' })).toEqual({ status: 'ok' });
  });

  test.each([
    ['arrays', []],
    ['null', null],
    ['primitive non-objects', 'ok'],
    ['missing status', {}],
    ['non-ok status', { status: 'error' }],
    ['extra fields', { status: 'ok', extra: true }],
  ])('rejects %s', (_label, payload) => {
    expect(() => validateHealthResponse(payload)).toThrow(
      'GET /health API contract error:',
    );
  });
});
