export default function DataTable({ data }) {
  if (!data || data.length === 0) return null;

  const headers = Object.keys(data[0]);

  return (
    <div className="native-table-wrapper">
      <table className="native-table">
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {headers.map((header) => {
                let cellValue = row[header];
                // If the value is a number, format it using the Indian numbering system
                if (typeof cellValue === 'number') {
                  cellValue = cellValue.toLocaleString('en-IN');
                }
                return <td key={header}>{cellValue}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
