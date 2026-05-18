import type { InputHTMLAttributes, ReactNode } from 'react';

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  helper?: ReactNode;
};

export function Field({ label, helper, ...props }: FieldProps) {
  return (
    <label className="field">
      <span>{label}</span>
      <input {...props} />
      {helper ? <small>{helper}</small> : null}
    </label>
  );
}
