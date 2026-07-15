import { useState, useEffect, useRef } from 'react';
import vegaEmbed from 'vega-embed';
import { Loader2, AlertCircle, Maximize2, Minimize2, ChevronLeft, ChevronRight } from 'lucide-react';

// ──────────────────────────────────────────────
// Utility: Split a faceted/folded Vega-Lite spec into N independent specs
// ──────────────────────────────────────────────
function splitFacetedSpec(spec) {
  const foldTransform = spec.transform?.find(t => t.fold);
  const facetField = spec.encoding?.column || spec.encoding?.row || spec.facet?.field;

  if (!foldTransform || !facetField) return [spec];

  const foldedFields = foldTransform.fold;
  const foldAs = foldTransform.as || ["key", "value"];
  const valueAlias = foldAs[1];

  const xEnc = spec.encoding?.x;
  const yEnc = spec.encoding?.y;

  let valueAxis;
  if (xEnc?.field === valueAlias) valueAxis = 'x';
  else if (yEnc?.field === valueAlias) valueAxis = 'y';
  else return [spec];

  return foldedFields.map(fieldName => {
    const subSpec = JSON.parse(JSON.stringify(spec));
    subSpec.transform = (subSpec.transform || []).filter(t => !t.fold);
    delete subSpec.encoding?.column;
    delete subSpec.encoding?.row;
    delete subSpec.facet;
    if (subSpec.encoding?.color?.field === foldAs[0]) delete subSpec.encoding.color;
    subSpec.encoding[valueAxis] = {
      ...subSpec.encoding[valueAxis],
      field: fieldName,
      title: fieldName.replace(/([A-Z])/g, ' $1').trim()
    };
    subSpec.description = fieldName.replace(/([A-Z])/g, ' $1').trim();
    return subSpec;
  });
}

// ──────────────────────────────────────────────
// Utility: Detect extreme value disparity in a bar chart and apply
// a symmetric log scale if the variance is massive (>100x).
// ──────────────────────────────────────────────
function adjustScaleForMagnitude(specs) {
  const result = [];

  for (const spec of specs) {
    const markType = typeof spec.mark === 'string' ? spec.mark : spec.mark?.type;
    if (markType !== 'bar' || !spec.data?.values || spec.data.values.length <= 1) {
      result.push(spec);
      continue;
    }

    // Identify the quantitative field
    const xEnc = spec.encoding?.x;
    const yEnc = spec.encoding?.y;
    let quantField, quantAxis;

    if (xEnc?.type === 'quantitative' && yEnc?.type === 'nominal') {
      quantField = xEnc.field; quantAxis = 'x';
    } else if (yEnc?.type === 'quantitative' && xEnc?.type === 'nominal') {
      quantField = yEnc.field; quantAxis = 'y';
    } else {
      result.push(spec);
      continue;
    }

    // Check the magnitude ratio
    const values = spec.data.values
      .map(d => Math.abs(Number(d[quantField]) || 0))
      .filter(v => v > 0);

    if (values.length < 2) { result.push(spec); continue; }

    const maxVal = Math.max(...values);
    const minVal = Math.min(...values);
    const ratio = maxVal / minVal;

    const subSpec = JSON.parse(JSON.stringify(spec));

    // If values span more than 100x, apply a log scale
    if (ratio > 100) {
      // Use symlog to safely handle zeros if any are present in the original dataset
      subSpec.encoding[quantAxis].scale = { ...subSpec.encoding[quantAxis].scale, type: 'symlog' };
    }

    result.push(subSpec);
  }

  return result;
}

function applyChartConfig(spec) {
  const s = JSON.parse(JSON.stringify(spec));
  const markType = typeof s.mark === 'string' ? s.mark : s.mark?.type;
  const isHorizontalBar = markType === 'bar' && s.encoding?.x?.type === 'quantitative' && s.encoding?.y?.type === 'nominal';
  const isVerticalBar = markType === 'bar' && s.encoding?.y?.type === 'quantitative' && s.encoding?.x?.type === 'nominal';

  // ── Config object ──
  s.config = s.config || {};

  // Legend: always bottom, never clipped on the right
  s.config.legend = { orient: 'bottom', labelLimit: 300 };

  // ── Axis config ──
  // X-axis: tilt labels at -30° for vertical bars to prevent overlap
  s.config.axisX = s.config.axisX || {};
  if (isVerticalBar) {
    s.config.axisX.labelAngle = -30;
    s.config.axisX.labelAlign = 'right';
    s.config.axisX.labelLimit = 150;
  } else {
    s.config.axisX.labelLimit = 200;
  }

  // Y-axis: horizontal labels, generous limit for horizontal bar charts
  s.config.axisY = s.config.axisY || {};
  s.config.axisY.labelLimit = isHorizontalBar ? 250 : 200;
  // Title placement: horizontal, anchored at top to avoid overlapping labels
  s.config.axisY.titleAngle = 0;
  s.config.axisY.titleAlign = 'left';
  s.config.axisY.titleAnchor = 'end';
  s.config.axisY.titleY = -10;

  // ── Sizing: Use fixed pixel dimensions, NOT "container" ──
  // This gives Vega full control over layout. The scrollable wrapper handles overflow.
  const dataLen = s.data?.values?.length || 0;

  if (s.vconcat || s.hconcat || s.concat || s.facet) {
    // Top-level width/height is illegal on composite specs in Vega-Lite
    // Let the composite layout define its own dimensions.
  } else if (isHorizontalBar) {
    // Horizontal bar: width fixed, height grows with categories
    s.width = 500;
    s.height = Math.max(200, dataLen * 35);
  } else if (isVerticalBar) {
    // Vertical bar: height fixed, width grows with categories
    s.width = Math.max(400, dataLen * 50);
    s.height = 350;
  } else {
    // Line, scatter, area, etc: fixed dimensions
    s.width = 550;
    s.height = 350;
  }

  // Padding so nothing touches the edges
  s.padding = { left: 10, right: 10, top: 15, bottom: 10 };
  s.autosize = { type: "pad", contains: "padding" };

  return s;
}


// ──────────────────────────────────────────────
// Sub-component: Renders a single Vega chart
// ──────────────────────────────────────────────
const SingleChart = ({ spec }) => {
  const chartRef = useRef(null);
  const viewRef = useRef(null);

  useEffect(() => {
    if (!chartRef.current || !spec) return;
    let cancelled = false;

    const render = async () => {
      if (viewRef.current) { viewRef.current.finalize(); viewRef.current = null; }
      try {
        const result = await vegaEmbed(chartRef.current, spec, {
          actions: false,
          renderer: 'svg',
          theme: 'dark'
        });
        if (!cancelled) viewRef.current = result.view;
      } catch (err) {
        console.error("Vega render error:", err);
      }
    };
    render();

    return () => {
      cancelled = true;
      if (viewRef.current) { viewRef.current.finalize(); viewRef.current = null; }
    };
  }, [spec]);

  return (
    // Scrollable wrapper: both axes. The chart inside has fixed pixel size.
    <div style={{
      width: '100%',
      overflow: 'auto', // scroll both X and Y
      maxHeight: '450px' // cap inline height, scroll inside
    }}>
      <div
        ref={chartRef}
        style={{
          width: 'fit-content',  // let Vega decide the width
          minWidth: '100%',      // but never smaller than container
          padding: '12px'
        }}
      />
    </div>
  );
};


// ──────────────────────────────────────────────
// Main Component
// ──────────────────────────────────────────────
const VisualAnalysisPanel = ({ query, data, isHistorical, initialSpec, onComplete, messageId }) => {
  const [status, setStatus] = useState('loading');
  const [errorMsg, setErrorMsg] = useState('');
  const [summaryText, setSummaryText] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [chartPages, setChartPages] = useState([]);
  const [currentPage, setCurrentPage] = useState(0);

  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    const fetchAndPrepare = async () => {
      setStatus('loading');

      try {
        if (!data || !Array.isArray(data) || data.length === 0) {
          throw new Error("No data returned from the database to visualize.");
        }

        let spec;
        let summary = '';

        if (initialSpec) {
          if (initialSpec.error) {
            throw new Error(initialSpec.error);
          }
          spec = initialSpec.spec !== undefined ? initialSpec.spec : initialSpec;
          if (spec) spec = JSON.parse(JSON.stringify(spec));
          summary = initialSpec.summary || '';
        } else {
          let response = await fetch('/api/analyze_v2', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ query, data, message_id: messageId }),
            signal: controller.signal
          });

          if (response.status === 401) {
            const refreshRes = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' });
            if (refreshRes.ok) {
              response = await fetch('/api/analyze_v2', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ query, data, message_id: messageId }),
                signal: controller.signal
              });
            } else {
              window.dispatchEvent(new Event('sessionExpired'));
              throw new Error("SESSION_EXPIRED");
            }
          }

          if (!response.ok) throw new Error("Failed to connect to visual analysis server.");

          const result = await response.json();
          if (result.status === 'error') throw new Error(result.content || "AI generation failed.");

          spec = result.vega_spec;
          summary = result.summary || '';

          // Handle AI declining to generate a chart, or if data is too small for a meaningful chart
          const isSingleValue = data.length === 1 && Object.keys(data[0] || {}).length <= 2;
          if (!spec || isSingleValue) {
            if (isMounted) {
              setSummaryText(summary);
              setStatus('success'); // Show summary only, no chart
              setChartPages([]);
            }
            if (onComplete) onComplete({ spec: null, summary });
            return;
          }

          // Merge data BEFORE caching
          spec.data = { values: result.data || data };
          if (onComplete) onComplete({ spec, summary });
        }

        setSummaryText(summary);

        // If spec is null (from cache) or invalid, show summary only
        const isSingleValueCached = data.length === 1 && Object.keys(data[0] || {}).length <= 2;
        const isComposite = spec && (spec.layer || spec.vconcat || spec.hconcat || spec.concat || spec.facet);
        if (!spec || (!spec.mark && !isComposite) || isSingleValueCached) {
          if (isMounted) { setStatus('success'); setChartPages([]); }
          return;
        }
        if (!spec.data || !spec.data.values || spec.data.values.length === 0) {
          throw new Error("Invalid chart spec: data values array is empty.");
        }

        // Split faceted specs, then adjust scale for magnitude
        const facetSplit = splitFacetedSpec(spec);
        const pages = adjustScaleForMagnitude(facetSplit);

        // Apply visualization config to each page
        const readyPages = pages.map(applyChartConfig);

        if (isMounted) {
          setChartPages(readyPages);
          setCurrentPage(0);
          setStatus('success');
        }

      } catch (err) {
        if (err.name === 'AbortError') return;
        console.error("Vega-Lite compile/render error:", err);
        if (err.message === "SESSION_EXPIRED") return; // Let the modal handle this
        
        if (isMounted) {
          setStatus('error');
          setErrorMsg(err.message || "Failed to render chart.");
        }
        // Crucial fix: cache the error state so it doesn't retry on every refresh
        if (onComplete && (!initialSpec || !initialSpec.error)) {
          onComplete({ spec: null, summary: '', error: err.message || "Failed to render chart." });
        }
      }
    };

    fetchAndPrepare();
    return () => { isMounted = false; controller.abort(); };
  }, [query, data]);

  const currentSpec = chartPages[currentPage];
  const insightCount = summaryText
    ? summaryText.split('\n').filter(l => l.trim().startsWith('*')).length
    : 0;
  const totalPages = chartPages.length;
  const isMultiPage = totalPages > 1;
  const hasCharts = totalPages > 0;

  // If there's an error or we have no charts and no summary, don't render the panel at all
  if (status === 'error' || (status === 'success' && !hasCharts && !summaryText)) return null;

  return (
    <div style={isFullscreen ? {
      position: 'fixed', inset: '3%', zIndex: 1000,
      background: '#1a1a1a', borderRadius: '12px',
      border: '1px solid rgba(255,255,255,0.15)',
      display: 'flex', flexDirection: 'column',
      boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.8)'
    } : {
      width: '100%',
      background: 'rgba(0,0,0,0.2)',
      borderRadius: '8px',
      border: '1px solid rgba(255,255,255,0.1)',
      display: 'flex', flexDirection: 'column',
      marginTop: '16px'
    }}>
      {/* ── Sticky Header ── */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '10px 16px',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
        fontSize: '0.85rem', color: '#a3a3a3',
        background: 'rgba(255,255,255,0.02)',
        flexShrink: 0
      }}>
        <span style={{ fontWeight: 600 }}>Visual Analysis</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Pagination: ← 1/3 → */}
          {isMultiPage && status === 'success' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
              <button
                onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                disabled={currentPage === 0}
                style={{
                  background: 'transparent', border: 'none',
                  color: currentPage === 0 ? '#444' : '#a3a3a3',
                  cursor: currentPage === 0 ? 'default' : 'pointer',
                  display: 'flex', padding: '4px', borderRadius: '4px'
                }}
              ><ChevronLeft size={16} /></button>
              <span style={{ fontSize: '0.8rem', minWidth: '36px', textAlign: 'center' }}>
                {currentPage + 1} / {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={currentPage === totalPages - 1}
                style={{
                  background: 'transparent', border: 'none',
                  color: currentPage === totalPages - 1 ? '#444' : '#a3a3a3',
                  cursor: currentPage === totalPages - 1 ? 'default' : 'pointer',
                  display: 'flex', padding: '4px', borderRadius: '4px'
                }}
              ><ChevronRight size={16} /></button>
            </div>
          )}
          {/* Fullscreen toggle */}
          {status === 'success' && hasCharts && (
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              style={{
                background: 'transparent', border: 'none', color: '#a3a3a3',
                cursor: 'pointer', display: 'flex', alignItems: 'center',
                padding: '4px', borderRadius: '4px'
              }}
              title={isFullscreen ? "Collapse" : "Expand"}
              onMouseOver={(e) => e.currentTarget.style.color = '#fff'}
              onMouseOut={(e) => e.currentTarget.style.color = '#a3a3a3'}
            >
              {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
            </button>
          )}
        </div>
      </div>

      {/* ── Page Title (multi-page only) ── */}
      {isMultiPage && status === 'success' && currentSpec && (
        <div style={{
          padding: '6px 16px', fontSize: '0.85rem', fontWeight: 600,
          color: 'var(--accent, #f59e0b)',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
          background: 'rgba(255,255,255,0.02)', flexShrink: 0
        }}>
          {currentSpec.description || `Chart ${currentPage + 1}`}
        </div>
      )}

      {/* ── Summary Accordion ── */}
      {status === 'success' && summaryText && (
        <details style={{
          borderBottom: '1px solid rgba(255,255,255,0.05)',
          background: 'rgba(0,0,0,0.1)', color: 'var(--text-main)', flexShrink: 0
        }}>
          <summary style={{
            padding: '10px 16px', fontSize: '0.9rem', fontWeight: 500,
            cursor: 'pointer', userSelect: 'none', outline: 'none',
            display: 'flex', alignItems: 'center', gap: '8px'
          }}>
            <span style={{ color: 'var(--accent)' }}>Insights ({insightCount} points)</span>
          </summary>
          <div style={{ padding: '0 16px 12px 16px', fontSize: '0.9rem', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>
            {summaryText.split('\n').map((line, i) => {
              const boldRegex = /\*\*(.*?)\*\*/g;
              if (!line.trim()) return <br key={i} />;
              const parts = line.split(boldRegex);
              return (
                <div key={i} style={{ marginBottom: '6px' }}>
                  {parts.map((part, idx) => idx % 2 === 1 ? <strong key={idx} style={{ color: '#fff' }}>{part}</strong> : part)}
                </div>
              );
            })}
          </div>
        </details>
      )}

      {/* ── Chart Area ── */}
      <div style={{ flex: 1, width: '100%' }}>
        {status === 'loading' && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#a3a3a3', minHeight: '250px' }}>
            <Loader2 size={24} className="spin" style={{ marginBottom: '8px' }} />
            <span style={{ fontSize: '0.9rem' }}>Generating chart...</span>
          </div>
        )}

        {/* One page, one visual */}
        {status === 'success' && currentSpec && (
          <SingleChart key={currentPage} spec={currentSpec} />
        )}
      </div>
    </div>
  );
};

export default VisualAnalysisPanel;
