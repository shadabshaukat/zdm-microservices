type TableProps = {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  emptyText?: string;
};

export function Table({ columns, rows, emptyText = 'No records found.' }: TableProps) {
  if (rows.length === 0) {
    return <p className="empty-state">{emptyText}</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={String(row.Name || row.name || index)}>
              {columns.map((column) => <td key={column}>{String(row[column] ?? '')}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
