import React from 'react';
import { ChevronDown, ChevronUp, Database } from 'lucide-react';

export default function SQLViewer({ sql, originalSql }) {
  const [isOpen, setIsOpen] = React.useState(false);
  const wasCorrected = originalSql && originalSql !== sql;

  return (
    <div className="sql-viewer">
      <div 
        className="sql-viewer-header"
        onClick={() => setIsOpen(!isOpen)}
      >
        <Database size={16} />
        <span>View Generated SQL</span>
        {isOpen ? <ChevronUp size={16} style={{ marginLeft: 'auto' }} /> : <ChevronDown size={16} style={{ marginLeft: 'auto' }} />}
      </div>
      
      {isOpen && (
        <div className="sql-content">
          {wasCorrected && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{ color: '#fbbf24', marginBottom: '8px' }}>⚠️ Original SQL was auto-corrected:</div>
              <div style={{ opacity: 0.7 }}>{originalSql}</div>
            </div>
          )}
          
          <div>
            {wasCorrected && <div style={{ color: '#34d399', marginBottom: '8px' }}>✅ Final executed SQL:</div>}
            <div>{sql}</div>
          </div>
        </div>
      )}
    </div>
  );
}
