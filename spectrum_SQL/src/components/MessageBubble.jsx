import React, { useState, useEffect } from 'react';
import { CheckCircle2, Loader2, Database, ThumbsUp, ThumbsDown } from 'lucide-react';
import SQLViewer from './SQLViewer';
import DataTable from './DataTable';
import AnalysisPanel from './AnalysisPanel';
import VisualAnalysisPanel from './VisualAnalysisPanel';

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

export default function MessageBubble({ message, onAnalysisComplete, onVisualAnalysisComplete, onUpdateMessage, showCost, showSql, allowedDatabases = [] }) {
  const isUser = message.role === 'user';
  
  const [commentText, setCommentText] = useState(message.user_comment || '');
  const [showCommentInput, setShowCommentInput] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleFeedback = async (isUseful) => {
    if (isSubmitting) return;
    if (onUpdateMessage) onUpdateMessage({ is_useful: isUseful });
    
    try {
      setIsSubmitting(true);
      await fetch(`/api/messages/${message.id}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_useful: isUseful })
      });
    } catch (e) {
      console.error("Failed to submit feedback", e);
    } finally {
      setIsSubmitting(false);
    }
  };

  const submitComment = async () => {
    if (isSubmitting || !commentText.trim()) return;
    if (onUpdateMessage) onUpdateMessage({ user_comment: commentText });

    try {
      setIsSubmitting(true);
      await fetch(`/api/messages/${message.id}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_comment: commentText })
      });
    } catch (e) {
      console.error("Failed to submit comment", e);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (message.type === 'loading') {
    return (
      <div className="message assistant">
        <div className="message-bubble glass-panel" style={{ minWidth: '400px' }}>
          <LoadingSteps />
        </div>
      </div>
    );
  }

  if (message.type === 'loading_history') {
    return (
      <div className="message assistant">
        <div className="message-bubble glass-panel" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Loader2 size={16} className="spin" color="var(--accent)" />
          <span style={{ color: 'var(--text-main)', fontSize: '0.9rem' }}>Loading chat history...</span>
        </div>
      </div>
    );
  }



  return (
    <div className={`message ${isUser ? 'user' : 'assistant'}`}>
      <div className={isUser ? "message-bubble" : "message-bubble glass-panel"} style={!isUser ? { padding: '24px' } : {}}>

        {/* User message text */}
        {isUser && <div>{message.content}</div>}

        {/* Assistant error response */}
        {!isUser && message.type === 'error' && (
          <div style={{ color: 'var(--text-main)', fontSize: '0.95rem', lineHeight: '1.6', marginBottom: '16px' }}>
            {message.content}
          </div>
        )}

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

              {message.sql && showSql && (
                <SQLViewer sql={message.sql} originalSql={message.original_sql} />
              )}

              {message.data && (
                <DataTable data={message.data} />
              )}

              {(message.visualAnalysisEnabled || message.visual_spec) && message.data && message.data.length > 0 && (
                <VisualAnalysisPanel
                  query={message.query}
                  data={message.data}
                  isHistorical={message.isHistorical}
                  initialSpec={message.visual_spec}
                  messageId={message.id}
                  onComplete={onVisualAnalysisComplete}
                />
              )}

              {message.cost && showCost && (
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

              {
                //component 
              }
            </div>

            {(message.analysisEnabled || message.analysis) && message.data && message.data.length > 0 && (
              <div style={{ flex: 1, minWidth: '350px' }}>
                <AnalysisPanel
                  query={message.query}
                  data={message.data}
                  initialAnalysis={message.analysis}
                  messageId={message.id}
                  onComplete={onAnalysisComplete}
                  isHistorical={message.isHistorical}
                />
              </div>
            )}
          </div>
        )}

        {/* Feedback Widget */}
        {!isUser && (message.type === 'success' || message.type === 'error') && (
          <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px solid rgba(255,255,255,0.1)', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <span style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)' }}>Is the Response useful?</span>
                <button 
                  onClick={() => handleFeedback(true)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: message.is_useful === true ? '#34d399' : 'rgba(255,255,255,0.4)' }}
                  title="Thumbs Up"
                >
                  <ThumbsUp size={16} />
                </button>
                <button 
                  onClick={() => handleFeedback(false)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: message.is_useful === false ? '#ef4444' : 'rgba(255,255,255,0.4)' }}
                  title="Thumbs Down"
                >
                  <ThumbsDown size={16} />
                </button>
                <button
                  onClick={() => setShowCommentInput(!showCommentInput)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: showCommentInput ? 'var(--accent)' : 'rgba(255,255,255,0.4)', fontSize: '0.85rem' }}
                >
                  Comment
                </button>
              </div>
              {message.db_id && (
                <div style={{ fontSize: '0.85rem', color: '#8c8787ff', fontStyle: 'italic', display: 'flex', alignItems: 'center' }}>
                  <span style={{opacity: 0.7}}>from {allowedDatabases.find(d => d.id === message.db_id)?.name || 'Unknown Database'}</span>
                </div>
              )}
            </div>
            
            {showCommentInput && (
              <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
                <div style={{ flex: 1 }}>
                  <textarea
                    value={commentText}
                    onChange={(e) => {
                      if (e.target.value.length <= 500) {
                        setCommentText(e.target.value);
                      }
                    }}
                    placeholder="Provide additional feedback..."
                    style={{
                      width: '100%',
                      background: 'rgba(0,0,0,0.2)',
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: '6px',
                      padding: '8px',
                      color: 'white',
                      fontSize: '0.85rem',
                      minHeight: '60px',
                      resize: 'vertical',
                      fontFamily: 'inherit'
                    }}
                  />
                  <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', textAlign: 'right', marginTop: '4px' }}>
                    {commentText.length}/500
                  </div>
                </div>
                <button 
                  onClick={submitComment}
                  disabled={isSubmitting || !commentText.trim() || commentText === message.user_comment}
                  style={{
                    background: 'var(--accent)',
                    border: 'none',
                    borderRadius: '4px',
                    padding: '8px 16px',
                    color: 'white',
                    cursor: (isSubmitting || !commentText.trim() || commentText === message.user_comment) ? 'not-allowed' : 'pointer',
                    opacity: (isSubmitting || !commentText.trim() || commentText === message.user_comment) ? 0.5 : 1,
                    marginBottom: '20px'
                  }}
                >
                  Submit
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
