import React, { useState, useEffect } from 'react';
import { CheckCircle2, Loader2, Database } from 'lucide-react';
import SQLViewer from './SQLViewer';
import DataTable from './DataTable';
import AnalysisPanel from './AnalysisPanel';

const LOADING_STEPS = [
  "Vectorising prompt & retrieving schema context via RAG...",
  "Running syntax checks and schema validation...",
  "Executing on Database...",
  "Formatting and rendering results..."
];

function LoadingSteps() {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    // Progress through steps every 3-4 seconds to simulate the backend process
    const interval = setInterval(() => {
      setStepIndex((prev) => (prev < LOADING_STEPS.length - 1 ? prev + 1 : prev));
    }, 3500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '8px 4px' }}>
      {LOADING_STEPS.map((step, idx) => {
        const isPast = idx < stepIndex;
        const isCurrent = idx === stepIndex;
        const isFuture = idx > stepIndex;

        if (isFuture) return null;

        return (
          <div key={idx} style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '12px',
            color: isPast ? '#34d399' : 'var(--text-main)',
            opacity: isPast ? 0.7 : 1,
            fontSize: '0.9rem',
            animation: 'fadeIn 0.3s ease-out'
          }}>
            {isPast ? (
              <CheckCircle2 size={16} color="#34d399" />
            ) : (
              <Loader2 size={16} className="spin" color="var(--accent)" />
            )}
            <span>{step}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function MessageBubble({ message, onAnalysisComplete }) {
  const isUser = message.role === 'user';
  
  if (message.type === 'loading') {
    return (
      <div className="message assistant">
        <div className="message-bubble glass-panel" style={{ minWidth: '400px' }}>
          <LoadingSteps />
        </div>
      </div>
    );
  }

  if (message.type === 'error') {
    return (
      <div className="message assistant">
        <div className="message-bubble glass-panel" style={{ borderLeft: '4px solid #ef4444' }}>
          <span style={{ color: '#ef4444' }}>{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`message ${isUser ? 'user' : 'assistant'}`}>
      <div className={isUser ? "message-bubble" : "message-bubble glass-panel"} style={!isUser ? { padding: '24px' } : {}}>
        
        {/* User message text */}
        {isUser && <div>{message.content}</div>}
        
        {/* Assistant success response */}
        {!isUser && message.type === 'success' && (
          <div style={{ display: 'flex', gap: '24px', alignItems: 'flex-start' }}>
            <div style={{ flex: 1.6, minWidth: 0 }}>
              {message.data && message.data.length > 0 ? (
                <div style={{ color: '#34d399', marginBottom: '16px', fontWeight: '500' }}>
                  ✓ {message.data.length} record{message.data.length !== 1 ? 's' : ''} retrieved
                </div>
              ) : (
                <div style={{ color: '#fbbf24', marginBottom: '16px', fontWeight: '500' }}>
                  ℹ️ Query returned 0 rows.
                </div>
              )}

              {message.explanation && (
                <div style={{ marginBottom: '16px', lineHeight: '1.5', color: 'var(--text-main)' }}>
                  {message.explanation}
                </div>
              )}
              
              {message.sql && (
                <SQLViewer sql={message.sql} originalSql={message.original_sql} />
              )}
              
              {message.data && (
                <DataTable data={message.data} />
              )}
              
              {message.cost && (
                <div className="cost-metrics">
                  <div className="metric-card">
                    <div className="metric-label">Input Tokens</div>
                    <div className="metric-value">{message.cost.input_tokens.toLocaleString()}</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">Output Tokens</div>
                    <div className="metric-value">{message.cost.output_tokens.toLocaleString()}</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">Cost (INR)</div>
                    <div className="metric-value">₹ {message.cost.cost_inr.toFixed(4)}</div>
                  </div>
                </div>
              )}
            </div>

            {message.analysisEnabled && message.data && message.data.length > 0 && (
              <div style={{ flex: 1, minWidth: '350px' }}>
                <AnalysisPanel 
                  query={message.query} 
                  data={message.data}
                  initialAnalysis={message.analysis}
                  onComplete={onAnalysisComplete}
                  isHistorical={message.isHistorical}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
