import { describe, expect, test } from 'vitest';

import { buildResponseFileRequest, buildRunJobRequest, buildSavedJobRequest } from './payloads';

describe('buildResponseFileRequest', () => {
  test('merges core response-file values, remaps, and additional values', () => {
    expect(buildResponseFileRequest({
      project: 'demo',
      migrationMethod: 'OFFLINE_LOGICAL',
      medium: 'OSS',
      values: {
        SOURCEDATABASE_CONNECTIONDETAILS_HOST: 'source.example.com',
        include_schemas: ['APP'],
      },
      remaps: [['REMAP_SCHEMA', 'APP', 'APP_NEW']],
      additional: { RUNCPATREMOTELY: 'TRUE' },
    })).toEqual({
      project: 'demo',
      migration_method: 'OFFLINE_LOGICAL',
      values: {
        MIGRATION_METHOD: 'OFFLINE_LOGICAL',
        DATA_TRANSFER_MEDIUM: 'OSS',
        SOURCEDATABASE_CONNECTIONDETAILS_HOST: 'source.example.com',
        include_schemas: ['APP'],
        DATAPUMPSETTINGS_METADATAREMAPS: [['REMAP_SCHEMA', 'APP', 'APP_NEW']],
        additional: { RUNCPATREMOTELY: 'TRUE' },
      },
    });
  });

  test('omits remaps and additional values when empty', () => {
    expect(buildResponseFileRequest({
      project: 'demo',
      migrationMethod: 'ONLINE_LOGICAL',
      medium: 'NFS',
      values: {},
      remaps: [],
      additional: {},
    })).toEqual({
      project: 'demo',
      migration_method: 'ONLINE_LOGICAL',
      values: {
        MIGRATION_METHOD: 'ONLINE_LOGICAL',
        DATA_TRANSFER_MEDIUM: 'NFS',
      },
    });
  });

  test('keeps core method and medium values authoritative', () => {
    expect(buildResponseFileRequest({
      project: 'demo',
      migrationMethod: 'OFFLINE_LOGICAL',
      medium: 'OSS',
      values: {
        MIGRATION_METHOD: 'ONLINE_LOGICAL',
        DATA_TRANSFER_MEDIUM: 'NFS',
      },
      remaps: [],
      additional: {},
    })).toEqual({
      project: 'demo',
      migration_method: 'OFFLINE_LOGICAL',
      values: {
        MIGRATION_METHOD: 'OFFLINE_LOGICAL',
        DATA_TRANSFER_MEDIUM: 'OSS',
      },
    });
  });
});

describe('buildSavedJobRequest', () => {
  test('builds the backend saved job request shape', () => {
    expect(buildSavedJobRequest({
      name: 'demo_eval',
      project: 'demo',
      rsp: 'demo.rsp',
      runType: 'EVAL',
      jobParameters: { sourcedb: 'SRCDB' },
      controls: { advisor_mode: 'NONE', listphases: false },
    })).toEqual({
      name: 'demo_eval',
      project: 'demo',
      rsp: 'demo.rsp',
      run_type: 'EVAL',
      job_parameters: { sourcedb: 'SRCDB' },
      advisor_mode: 'NONE',
      listphases: false,
    });
  });

  test('keeps core saved-job fields authoritative over control values', () => {
    expect(buildSavedJobRequest({
      name: 'demo_eval',
      project: 'demo',
      rsp: 'demo.rsp',
      runType: 'EVAL',
      jobParameters: { sourcedb: 'SRCDB' },
      controls: {
        name: 'wrong_migrate',
        project: 'wrong',
        rsp: 'wrong.rsp',
        run_type: 'MIGRATE',
        job_parameters: { sourcedb: 'WRONG' },
        advisor_mode: 'NONE',
      },
    })).toEqual({
      name: 'demo_eval',
      project: 'demo',
      rsp: 'demo.rsp',
      run_type: 'EVAL',
      job_parameters: { sourcedb: 'SRCDB' },
      advisor_mode: 'NONE',
    });
  });
});

describe('buildRunJobRequest', () => {
  const savedJob = {
    name: 'demo_eval',
    project: 'demo',
    rsp: 'demo.rsp',
    run_type: 'EVAL' as const,
    job_parameters: { sourcedb: 'SRCDB', empty: '' },
    advisor_mode: 'NONE',
    flow_control: 'NONE',
    flow_phase: null,
    genfixup: null,
    ignore: null,
    schedule: null,
    listphases: false,
    custom_args: null,
  };

  test('builds dry-run job submission payload from a saved job', () => {
    expect(buildRunJobRequest(savedJob, true)).toEqual({
      project: 'demo',
      run_type: 'EVAL',
      rsp: 'demo.rsp',
      job_parameters: { sourcedb: 'SRCDB', empty: '' },
      advisor_mode: 'NONE',
      flow_control: 'NONE',
      flow_phase: null,
      genfixup: null,
      ignore: null,
      schedule: null,
      listphases: false,
      custom_args: null,
      dry_run: true,
    });
  });

  test('builds submit job payload from a saved job', () => {
    expect(buildRunJobRequest(savedJob, false)).toEqual({
      project: 'demo',
      run_type: 'EVAL',
      rsp: 'demo.rsp',
      job_parameters: { sourcedb: 'SRCDB', empty: '' },
      advisor_mode: 'NONE',
      flow_control: 'NONE',
      flow_phase: null,
      genfixup: null,
      ignore: null,
      schedule: null,
      listphases: false,
      custom_args: null,
      dry_run: false,
    });
  });
});
