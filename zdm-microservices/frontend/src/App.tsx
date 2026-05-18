import { useEffect, useMemo, useState } from 'react';
import { apiFetch, loadApiSettings, type ApiSettings } from './api/client';
import { validateFrontendMetadata, type FrontendMetadata } from './api/metadata';
import { Alert } from './components/Alert';
import { PageShell, type NavGroup } from './components/PageShell';
import { DbConnectionsPage } from './pages/DbConnectionsPage';
import { DiscoveryPage } from './pages/DiscoveryPage';
import { JobDefinitionsPage } from './pages/JobDefinitionsPage';
import { JobMonitoringPage } from './pages/JobMonitoringPage';
import { JobSubmissionPage } from './pages/JobSubmissionPage';
import { MigrationDashboardPage } from './pages/MigrationDashboardPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { ResponseFilesPage } from './pages/ResponseFilesPage';
import { RouteStubPage } from './pages/RouteStubPage';
import { SettingsPage } from './pages/SettingsPage';
import { WalletsPage } from './pages/WalletsPage';

const fallbackNavGroups: NavGroup[] = [
  {
    label: 'Database Setup',
    items: [
      { label: 'DB Connections', path: '/connections' },
      { label: 'DB Wallets & Credentials', path: '/wallets' },
      { label: 'DB Discovery', path: '/discovery' },
    ],
  },
  {
    label: 'Migrations',
    items: [
      { label: 'Projects', path: '/projects' },
      { label: 'ZDM Response Files', path: '/response-files' },
      { label: 'ZDM Job Definitions', path: '/job-definitions' },
      { label: 'ZDM Job Submission', path: '/job-submission' },
      { label: 'ZDM Job Monitoring', path: '/jobs' },
      { label: 'Migration Dashboard', path: '/dashboard' },
    ],
  },
  {
    label: 'Administration',
    items: [
      { label: 'ZEUS Settings', path: '/settings' },
    ],
  },
];

function currentPath() {
  return window.location.pathname === '/' ? '/settings' : window.location.pathname;
}

export function App() {
  const [path, setPath] = useState(currentPath);
  const [settings, setSettings] = useState<ApiSettings>(() => loadApiSettings());
  const [metadata, setMetadata] = useState<FrontendMetadata | null>(null);
  const [metadataError, setMetadataError] = useState('');

  useEffect(() => {
    function onPopState() {
      setPath(currentPath());
    }
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    if (!settings.apiBase || !settings.username || !settings.password) {
      setMetadata(null);
      setMetadataError('');
      return;
    }

    let cancelled = false;

    async function loadMetadata() {
      setMetadata(null);
      setMetadataError('');
      try {
        const payload = await apiFetch(settings, '/metadata/frontend');
        const nextMetadata = validateFrontendMetadata(payload);
        if (!cancelled) setMetadata(nextMetadata);
      } catch (err) {
        if (cancelled) return;
        setMetadata(null);
        setMetadataError(err instanceof Error ? err.message : 'metadata response was invalid.');
      }
    }

    void loadMetadata();

    return () => {
      cancelled = true;
    };
  }, [settings]);

  const navGroups = useMemo<NavGroup[]>(() => {
    if (!metadata) return fallbackNavGroups;
    const metadataNavGroups = metadata.navigation.groups.map((group) => ({
      label: group.label,
      items: group.items.map((item) => ({ label: item.label, path: item.path })),
    }));
    return metadataNavGroups.length > 0 ? metadataNavGroups : fallbackNavGroups;
  }, [metadata]);

  const activePage = useMemo(() => {
    if (path === '/connections') return <DbConnectionsPage settings={settings} />;
    if (path === '/discovery') return <DiscoveryPage settings={settings} />;
    if (path === '/dashboard') return <MigrationDashboardPage settings={settings} />;
    if (path === '/job-definitions') return <JobDefinitionsPage settings={settings} />;
    if (path === '/job-submission') return <JobSubmissionPage settings={settings} />;
    if (path === '/jobs') return <JobMonitoringPage settings={settings} />;
    if (path === '/projects') return <ProjectsPage settings={settings} />;
    if (path === '/response-files') return <ResponseFilesPage settings={settings} />;
    if (path === '/wallets') return <WalletsPage settings={settings} />;
    if (path === '/settings') return <SettingsPage onSettingsSaved={setSettings} />;
    return <RouteStubPage path={path} metadataLoaded={metadata !== null} />;
  }, [metadata, path, settings]);

  function navigate(nextPath: string) {
    window.history.pushState({}, '', nextPath);
    setPath(nextPath);
  }

  return (
    <PageShell
      title="ZEUS"
      subtitle="ZDM Enqueue URL Services"
      navGroups={navGroups}
      activePath={path}
      onNavigate={navigate}
    >
      {metadataError ? (
        <Alert tone="error">Frontend metadata contract error: {metadataError}</Alert>
      ) : null}
      {activePage}
    </PageShell>
  );
}
