import React, { useState, useEffect, useRef } from 'react';
import { Loader2, Code2, Sparkles, TerminalSquare } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const AnalysisPanel = ({ query, data, initialAnalysis, onComplete, isHistorical }) => {
  const [status, setStatus] = useState(initialAnalysis ? 'done' : (isHistorical ? 'idle' : 'generating_code'));
  const [code, setCode] = useState(initialAnalysis?.code || '');
  const [summary, setSummary] = useState(initialAnalysis?.summary || '');
  const [tokenUsage, setTokenUsage] = useState(initialAnalysis?.tokenUsage || 0);
  const [errorMsg, setErrorMsg] = useState('');
  
  const bottomRef = useRef(null);

  useEffect(() => {
    // If we already have the initial analysis cached in the global messages state, do not re-fetch.
    if (initialAnalysis) return;
    
    // If this is a historical message loaded from localStorage (e.g. on page reload), 
    // and it doesn't have an analysis, do not auto-fetch. Wait for user to click 'Run Analysis'.
    if (isHistorical && status === 'idle') return;

    let isMounted = true;
    const abortController = new AbortController();

    const fetchAnalysis = async () => {
      try {
        if (status === 'idle') setStatus('generating_code');
        const response = await fetch('http://localhost:8000/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, data }),
          signal: abortController.signal
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const payload = await response.json();
        
        if (payload.status === 'error') {
            if (isMounted) {
              setStatus('error');
              setErrorMsg(payload.content);
            }
            return;
        }

        if (isMounted) {
            setCode(payload.code || '');
            setSummary(payload.summary || '');
            setTokenUsage(payload.tokenUsage || 0);
            setStatus('done');
            
            if (onComplete) {
              onComplete({
                code: payload.code || '',
                summary: payload.summary || '',
                tokenUsage: payload.tokenUsage || 0
              });
            }
        }

      } catch (err) {
        if (err.name !== 'AbortError' && isMounted) {
          setStatus('error');
          setErrorMsg(err.message);
        }
      }
    };

    fetchAnalysis();

    return () => {
      isMounted = false;
      abortController.abort();
    };
  }, [query, data, isHistorical, status]);

  useEffect(() => {
    if (status === 'generating_code' && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'auto' });
    }
  }, [code, status]);

  if (status === 'done' || status === 'generating_summary') {
    return (
      <div className="analysis-panel summary-view" style={{ position: 'relative' }}>
        <div className="analysis-header">
          <Sparkles size={16} style={{ color: '#d97757' }} />
          <span>Analytical Summary</span>
        </div>
        <div className="analysis-content summary-content">
          {summary ? <ReactMarkdown>{summary}</ReactMarkdown> : <span style={{opacity: 0.5}}>Generating summary...</span>}
        </div>
        {tokenUsage > 0 && (
          <div style={{
            position: 'absolute',
            bottom: '12px',
            right: '16px',
            fontSize: '11px',
            color: 'rgba(255,255,255,0.4)',
            pointerEvents: 'none',
            fontFamily: 'monospace'
          }}>
            {tokenUsage} Tokens
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="analysis-panel code-view">
      <div className="analysis-header">
        <TerminalSquare size={16} />
        <span>Execute Python code</span>
        {status === 'executing' && <Loader2 size={14} className="spin-icon" style={{marginLeft: 'auto'}} />}
      </div>
      <div className="analysis-content code-content">
        {status === 'idle' && isHistorical ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px 16px', opacity: 0.8 }}>
            <div style={{ marginBottom: '12px', fontSize: '0.9rem' }}>Analytical summary is missing or failed previously.</div>
            <button 
              onClick={() => setStatus('generating_code')}
              style={{
                background: 'var(--accent)',
                color: 'white',
                border: 'none',
                padding: '8px 16px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontWeight: 500,
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              <Sparkles size={16} /> Run Analysis Now
            </button>
          </div>
        ) : (
          <div className="code-block">
            <pre>
              <code>{code}</code>
              <div ref={bottomRef} />
            </pre>
          </div>
        )}
        {status === 'executing' && (
          <div className="execution-status">
            Executing code locally...
          </div>
        )}
        {status === 'error' && (
          <div className="error-status">
            {errorMsg}
          </div>
        )}
      </div>
    </div>
  );
};

export default AnalysisPanel;
