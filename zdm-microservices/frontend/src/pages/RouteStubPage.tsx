type RouteStubPageProps = {
  path: string;
  metadataLoaded: boolean;
};

export function RouteStubPage({ path, metadataLoaded }: RouteStubPageProps) {
  return (
    <section className="zeus-panel">
      <h2 className="page-title">{titleFromPath(path)}</h2>
      <p className="page-caption">
        {metadataLoaded
          ? 'Metadata loaded. This route is waiting for its page task.'
          : 'Configure ZEUS Settings to load backend metadata.'}
      </p>
    </section>
  );
}

function titleFromPath(path: string) {
  return path
    .replace(/^\//, '')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase()) || 'ZEUS';
}
