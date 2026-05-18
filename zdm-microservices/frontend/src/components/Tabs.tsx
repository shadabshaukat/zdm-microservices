import { useState, type ReactNode } from 'react';

export type TabItem = {
  label: string;
  content: ReactNode;
};

type TabsProps = {
  tabs: TabItem[];
};

export function Tabs({ tabs }: TabsProps) {
  const [active, setActive] = useState(0);

  return (
    <div className="tabs">
      <div className="tab-list" role="tablist">
        {tabs.map((tab, index) => (
          <button
            aria-selected={active === index}
            className={active === index ? 'tab active' : 'tab'}
            key={tab.label}
            onClick={() => setActive(index)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="tab-panel" role="tabpanel">
        {tabs[active]?.content}
      </div>
    </div>
  );
}
