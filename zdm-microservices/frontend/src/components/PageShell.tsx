import type { ReactNode } from 'react';

export type NavItem = {
  label: string;
  path: string;
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

type PageShellProps = {
  title: string;
  subtitle: string;
  navGroups: NavGroup[];
  activePath: string;
  onNavigate: (path: string) => void;
  children: ReactNode;
};

export function PageShell({
  title,
  subtitle,
  navGroups,
  activePath,
  onNavigate,
  children,
}: PageShellProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">Z</div>
          <div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
        </div>
        <nav className="nav-list" aria-label="Primary">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-group-label">{group.label}</div>
              {group.items.map((item) => (
                <button
                  className={item.path === activePath ? 'nav-item active' : 'nav-item'}
                  key={item.path}
                  onClick={() => onNavigate(item.path)}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <main className="main-view">{children}</main>
    </div>
  );
}
