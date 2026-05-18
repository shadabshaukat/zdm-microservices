import type { ReactNode } from 'react';

type AlertProps = {
  tone?: 'info' | 'success' | 'warning' | 'error';
  children: ReactNode;
};

export function Alert({ tone = 'info', children }: AlertProps) {
  return <div className={`alert alert-${tone}`}>{children}</div>;
}
