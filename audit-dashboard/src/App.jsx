import { useState, useEffect, useCallback, useRef } from 'react'

// ── Nav Icons (inline SVG, no external icon lib needed) ──────────────────────
const Icons = {
  Dashboard: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/>
      <rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/>
    </svg>
  ),
  Rules: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 4h12M2 8h8M2 12h10"/>
    </svg>
  ),
  Findings: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="7" cy="7" r="5"/><path d="M11 11l3 3"/>
    </svg>
  ),
  Reports: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="1" width="12" height="14" rx="1"/>
      <path d="M5 5h6M5 8h6M5 11h4"/>
    </svg>
  ),
  Policies: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 2v12h10V4l-2-2H3z"/>
      <path d="M8 6h3M5 10h6"/>
    </svg>
  ),
  Settings: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="2"/>
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41"/>
    </svg>
  ),
  Loader: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="animate-spin">
      <path d="M8 1.5A6.5 6.5 0 1 1 1.5 8"/>
    </svg>
  ),
}

// ── Severity helpers ──────────────────────────────────────────────────────────
const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3 }

function severityStampClass(sev) {
  const s = sev?.toLowerCase()
  if (s === 'critical') return 'stamp stamp-critical'
  if (s === 'high') return 'stamp stamp-high'
  return 'stamp stamp-medium'
}

function severityLabel(sev) {
  return sev?.toUpperCase() ?? 'UNKNOWN'
}

function sortBySeverity(results) {
  return [...results].sort((a, b) => {
    const ao = SEV_ORDER[a.severity?.toLowerCase()] ?? 99
    const bo = SEV_ORDER[b.severity?.toLowerCase()] ?? 99
    return ao - bo
  })
}

// ── Generate a run ID from today's date ──────────────────────────────────────
function makeRunId() {
  const d = new Date()
  const ymd = d.toISOString().slice(0, 10).replace(/-/g, '-')
  const seq = String(Math.floor(Math.random() * 9000) + 1000)
  return `#${ymd}-${seq}`
}

// ── Removed SVG roughen filter (simplified badge design) ──────────────────────

// ── HTML Sanitizer Helper (prevents XSS) ────────────────────────────────────
const AUTH_TOKEN = import.meta.env?.VITE_API_AUTH_TOKEN || 'vault-audit-secret-token'

function apiFetch(url, options = {}) {
  const headers = {
    'Authorization': `Bearer ${AUTH_TOKEN}`,
    ...(options.headers || {})
  }
  return fetch(url, { ...options, headers })
}

function safeMarkdown(md) {
  if (!md) return ''
  if (window.DOMPurify && window.marked) {
    return window.DOMPurify.sanitize(window.marked.parse(md))
  }
  // Bulletproof fallback if DOMPurify fails to load: escape all HTML tags to prevent XSS
  const div = document.createElement('div')
  div.textContent = md
  return '<p style="white-space: pre-wrap;">' + div.innerHTML + '</p>'
}

// ── NavRail ───────────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', Icon: Icons.Dashboard },
  { id: 'policies',  label: 'Policies',  Icon: Icons.Policies  },
  { id: 'rules',     label: 'Rules',     Icon: Icons.Rules     },
  { id: 'findings',  label: 'Findings',  Icon: Icons.Findings  },
  { id: 'reports',   label: 'Reports',   Icon: Icons.Reports   },
  { id: 'settings',  label: 'Settings',  Icon: Icons.Settings  },
]

function NavRail({ active, setActive }) {
  return (
    <nav
      className="nav-rail"
      style={{
        width: 220,
        minWidth: 220,
        background: '#1E2C3A',
        height: '100vh',
        position: 'fixed',
        left: 0,
        top: 0,
        display: 'flex',
        flexDirection: 'column',
        zIndex: 10,
        borderRight: '1px solid #2a3e52',
      }}
    >
      {/* Wordmark */}
      <div style={{ padding: '22px 20px 24px' }}>
        <div style={{
          fontFamily: 'Newsreader, Georgia, serif',
          fontSize: '1.1rem',
          color: '#B08F4F',
          letterSpacing: '0.02em',
          lineHeight: 1.2,
        }}>
          Vault<span style={{ color: '#DCD3B8', fontWeight: 400 }}>Audit</span>
        </div>
        <div style={{
          fontFamily: 'Inter, sans-serif',
          fontSize: '0.65rem',
          color: '#4a6070',
          marginTop: 2,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}>
          Compliance Case File
        </div>
      </div>

      {/* Nav items */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 2, paddingRight: 12 }}>
        {NAV_ITEMS.map(({ id, label, Icon }) => (
          <button
            key={id}
            id={`nav-${id}`}
            className={`nav-item${active === id ? ' active' : ''}`}
            onClick={() => setActive(id)}
            aria-current={active === id ? 'page' : undefined}
          >
            <Icon />
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* Version footer */}
      <div style={{
        padding: '16px 20px',
        fontSize: '0.65rem',
        color: '#2f4455',
        fontFamily: 'JetBrains Mono, monospace',
        borderTop: '1px solid #2a3e52',
      }}>
        v0.1.0 · audit-engine
      </div>
    </nav>
  )
}

// ── Bottom nav (mobile) ───────────────────────────────────────────────────────
function BottomNav({ active, setActive }) {
  return (
    <nav
      className="bottom-nav"
      style={{
        display: 'flex',
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        background: '#1E2C3A',
        borderTop: '1px solid #2a3e52',
        zIndex: 20,
        justifyContent: 'space-around',
        padding: '8px 0',
      }}
    >
      {NAV_ITEMS.map(({ id, label, Icon }) => (
        <button
          key={id}
          id={`bottom-nav-${id}`}
          onClick={() => setActive(id)}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 4,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: active === id ? '#B08F4F' : '#4a6070',
            fontSize: '0.6rem',
            fontFamily: 'Inter, sans-serif',
            padding: '4px 12px',
          }}
          aria-current={active === id ? 'page' : undefined}
        >
          <Icon />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  )
}

// ── Tally strip ───────────────────────────────────────────────────────────────
function TallyStrip({ results }) {
  const counts = { critical: 0, high: 0, medium: 0, low: 0 }
  results.forEach(r => {
    const s = r.severity?.toLowerCase()
    if (s in counts) counts[s] += r.finding_count ?? 0
  })

  const items = [
    { key: 'critical', label: 'Critical', color: '#A23B2C' },
    { key: 'high',     label: 'High',     color: '#D97706' },
    { key: 'medium',   label: 'Medium',   color: '#B08F4F' },
    { key: 'low',      label: 'Low',      color: '#6b7f8c' },
  ]

  return (
    <div className="tally-grid">
      {items.map(({ key, label, color }) => (
        <div key={key} style={{ minWidth: 60 }}>
          <div
            style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '2.5rem',
              fontWeight: 800,
              color,
              lineHeight: 1,
            }}
          >
            {String(counts[key]).padStart(2, '0')}
          </div>
          <div
            style={{
              fontFamily: 'Inter, sans-serif',
              fontSize: '0.95rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color,
              marginTop: 8,
            }}
          >
            {label}
          </div>
          <span className="tally-rule" style={{ opacity: 0.4 }} />
        </div>
      ))}
    </div>
  )
}

// ── Finding card tabs (Query / Narrative / Raw rows) ──────────────────────────
function FindingTabs({ finding, rule }) {
  const [activeTab, setActiveTab] = useState(null) // null = collapsed

  const tabs = [
    { id: 'query',     label: 'View query' },
    { id: 'narrative', label: 'Narrative'  },
    { id: 'rawrows',   label: 'Raw rows'   },
  ]

  // Build a representive SQL from the rule title (real SQL unknown client-side)
  const sqlSnippet = rule.query_run ?? rule.query_hint
    ?? `-- Rule: ${rule.title}\n-- Run the audit to execute the live query against the database.\n-- Check /audits/${rule.rule_id} for the full execution result.`

  const narrative = finding?.narrative ?? rule.narrative ?? null

  // Build raw rows columns
  const rows = rule.findings ?? []
  const cols = rows.length > 0 ? Object.keys(rows[0]) : []

  return (
    <div style={{ borderTop: '1px solid #c9bf9e', marginTop: 14 }}>
      {/* Tab triggers */}
      <div style={{ display: 'flex', gap: 0 }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            id={`tab-${rule.rule_id}-${tab.id}`}
            onClick={() => setActiveTab(activeTab === tab.id ? null : tab.id)}
            aria-expanded={activeTab === tab.id}
            style={{
              padding: '7px 14px',
              fontSize: '0.75rem',
              fontFamily: 'Inter, sans-serif',
              fontWeight: 500,
              background: 'none',
              border: 'none',
              borderBottom: activeTab === tab.id ? '2px solid #B08F4F' : '2px solid transparent',
              color: activeTab === tab.id ? '#211C16' : '#6b5d42',
              cursor: 'pointer',
              transition: 'color 0.1s, border-color 0.1s',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'query' && (
        <div style={{ padding: '12px 0 4px' }}>
          <pre className="code-block">{sqlSnippet}</pre>
        </div>
      )}

      {activeTab === 'narrative' && (
        <div style={{
          padding: '14px 0 4px',
          fontFamily: 'Inter, sans-serif',
          fontSize: '0.85rem',
          lineHeight: 1.6,
          color: '#3d322a',
        }}>
          {narrative
            ? <div className="markdown-body" dangerouslySetInnerHTML={{ __html: safeMarkdown(narrative) }} />
            : (
              <p style={{ color: '#7a6a55', fontStyle: 'italic' }}>
                Narrative not yet available. The AI summarizer may still be processing — re-run the audit to request an updated report.
              </p>
            )
          }
        </div>
      )}

      {activeTab === 'rawrows' && (
        <div style={{ padding: '12px 0 4px', overflowX: 'auto' }}>
          {rows.length === 0 ? (
            <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem', color: '#7a6a55' }}>
              No rows returned for this rule.
            </p>
          ) : (
            <table className="raw-table">
              <thead>
                <tr>{cols.map(c => <th key={c}>{c}</th>)}</tr>
              </thead>
              <tbody>
                {rows.map((row, ri) => (
                  <tr key={ri}>
                    {cols.map(c => (
                      <td key={c}>
                        {row[c] === null ? <span style={{ opacity: 0.4 }}>null</span>
                          : String(row[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

// ── Single finding card ───────────────────────────────────────────────────────
function FindingCard({ rule, index }) {
  const sev = rule.severity?.toLowerCase() ?? 'low'

  // Build a one-line summary using real data if available
  const topRow = rule.findings?.[0]
  let summary = null
  if (topRow) {
    const user = topRow.user_name ?? topRow.employee_id ?? topRow.full_name ?? topRow.username ?? null
    const detail = topRow.total_bytes != null
      ? `${(topRow.total_bytes / 1e9).toFixed(1)} GB transferred`
      : topRow.event_count != null
        ? `${topRow.event_count} events in window`
        : topRow.role_1 && topRow.role_2
          ? `${topRow.role_1} + ${topRow.role_2} conflict`
          : topRow.days_since_login != null
            ? `${topRow.days_since_login}d since last login`
            : null

    if (user && detail) summary = { user, detail }
    else if (user) summary = { user, detail: `${rule.finding_count} finding${rule.finding_count !== 1 ? 's' : ''}` }
  }

  return (
    <article
      className="stamp-land"
      style={{
        background: '#DCD3B8',
        color: '#211C16',
        borderRadius: 6,
        boxShadow: '0 2px 8px rgba(0,0,0,0.22), 0 1px 2px rgba(0,0,0,0.12)',
        padding: '18px 20px',
        position: 'relative',
        animationDelay: `${index * 60}ms`,
      }}
    >
      {/* Severity stamp — top-right corner */}
      <div className={`${severityStampClass(sev)} stamp-absolute`}>
        {severityLabel(sev)}
      </div>

      {/* Rule title */}
      <h2 style={{
        fontFamily: 'Inter, sans-serif',
        fontWeight: 600,
        fontSize: '0.95rem',
        color: '#211C16',
        paddingRight: 80, // avoid stamp overlap
        lineHeight: 1.3,
      }}>
        {rule.title}
      </h2>

      {/* One-line data summary */}
      {summary ? (
        <p style={{ marginTop: 6, fontSize: '0.83rem', display: 'flex', flexWrap: 'wrap', gap: '0 6px' }}>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#3d2e1a' }}>
            {summary.user}
          </span>
          <span style={{ color: '#6b5d42' }}>—</span>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', color: '#3d2e1a' }}>
            {summary.detail}
          </span>
          {rule.finding_count > 1 && (
            <span style={{ color: '#7a6a55', fontFamily: 'Inter, sans-serif', fontSize: '0.78rem' }}>
              + {rule.finding_count - 1} more
            </span>
          )}
        </p>
      ) : (
        <p style={{ marginTop: 6, fontSize: '0.83rem', color: '#7a6a55', fontFamily: 'Inter, sans-serif' }}>
          <span style={{ fontFamily: 'JetBrains Mono, monospace' }}>{rule.finding_count}</span>
          {` finding${rule.finding_count !== 1 ? 's' : ''} identified`}
        </p>
      )}

      {/* Remediation note */}
      {rule.remediation && (
        <p style={{
          marginTop: 8,
          fontSize: '0.78rem',
          color: '#5a4c3c',
          fontFamily: 'Inter, sans-serif',
          lineHeight: 1.5,
          borderLeft: '2px solid #b8ad8c',
          paddingLeft: 10,
        }}>
          {rule.remediation.length > 160 ? rule.remediation.slice(0, 157) + '…' : rule.remediation}
        </p>
      )}

      {/* Tabs */}
      <FindingTabs finding={null} rule={rule} />
    </article>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────
function EmptyState({ onRun, loading }) {
  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 12,
      padding: 48,
      textAlign: 'center',
    }}>
      <p style={{
        fontFamily: 'Newsreader, Georgia, serif',
        fontSize: '1.5rem',
        color: '#4a6070',
        lineHeight: 1.3,
      }}>
        No findings yet.
      </p>
      <p style={{
        fontFamily: 'Inter, sans-serif',
        fontSize: '0.88rem',
        color: '#2f4455',
        maxWidth: 320,
      }}>
        Run the audit to open this case. Findings will appear here sorted by severity.
      </p>
      <RunButton onRun={onRun} loading={loading} id="empty-run-btn" />
    </div>
  )
}

// ── Error state ───────────────────────────────────────────────────────────────
function ErrorState({ message, onRun, loading }) {
  return (
    <div style={{
      margin: '32px',
      padding: '20px 24px',
      background: '#1E2C3A',
      border: '1px solid #A23B2C',
      borderRadius: 6,
      maxWidth: 560,
    }}>
      <p style={{ fontFamily: 'Inter, sans-serif', fontWeight: 600, color: '#DCD3B8', marginBottom: 6 }}>
        Audit failed to run
      </p>
      <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.78rem', color: '#8fa3b8', lineHeight: 1.6 }}>
        {message}
      </p>
      <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.82rem', color: '#4a6070', marginTop: 12 }}>
        Check that the FastAPI server is running at localhost:8000, then try again.
      </p>
      <div style={{ marginTop: 16 }}>
        <RunButton onRun={onRun} loading={loading} id="error-run-btn" />
      </div>
    </div>
  )
}

// ── Run Audit button ──────────────────────────────────────────────────────────
function RunButton({ onRun, loading, id = 'run-audit-btn', label = 'Run Audit' }) {
  const btnRef = useRef(null)

  function handleClick() {
    if (loading) return
    const el = btnRef.current
    if (el) {
      el.classList.remove('btn-press')
      void el.offsetWidth // reflow
      el.classList.add('btn-press')
    }
    onRun()
  }

  return (
    <button
      ref={btnRef}
      id={id}
      onClick={handleClick}
      disabled={loading}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        padding: '9px 20px',
        background: loading ? '#7a6030' : '#B08F4F',
        color: '#211C16',
        fontFamily: 'Inter, sans-serif',
        fontSize: '0.85rem',
        fontWeight: 600,
        border: 'none',
        borderRadius: 4,
        cursor: loading ? 'not-allowed' : 'pointer',
        letterSpacing: '0.02em',
        transition: 'background 0.15s',
      }}
      onAnimationEnd={() => btnRef.current?.classList.remove('btn-press')}
    >
      {loading ? <Icons.Loader /> : null}
      {loading ? 'Running…' : label}
    </button>
  )
}

// ── Dashboard view ────────────────────────────────────────────────────────────
function Dashboard({ runId, env, results, loading, error, onRun, executedAt, health }) {
  const sorted = sortBySeverity(results)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Top header bar */}
      <header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '16px 32px',
        borderBottom: '1px solid #1E2C3A',
        flexWrap: 'wrap',
        gap: 12,
      }}>
        {/* Left: eyebrow + run ID */}
        <div>
          <div style={{
            fontFamily: 'Inter, sans-serif',
            fontSize: '0.65rem',
            textTransform: 'uppercase',
            letterSpacing: '0.12em',
            color: '#4a6070',
            marginBottom: 2,
          }}>
            Case File
          </div>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: '0.95rem',
            color: '#DCD3B8',
          }}>
            {runId}
          </div>
          {executedAt && (
            <div style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.65rem',
              color: '#2f4455',
              marginTop: 2,
            }}>
              {executedAt}
            </div>
          )}
        </div>

        {/* Center-right: environment chip + Health + Run Audit */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 8, marginRight: 8 }}>
            <div title="API Status" style={{ display: 'flex', alignItems: 'center', gap: 4, fontFamily: 'Inter, sans-serif', fontSize: '0.65rem', color: '#8fa3b8' }}>
               <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: health.api === 'ok' ? '#4CAF50' : health.api === 'error' ? '#A23B2C' : '#B08F4F' }} />
               API
            </div>
            <div title="DB Status" style={{ display: 'flex', alignItems: 'center', gap: 4, fontFamily: 'Inter, sans-serif', fontSize: '0.65rem', color: '#8fa3b8' }}>
               <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: health.db === 'ok' ? '#4CAF50' : health.db === 'error' ? '#A23B2C' : '#B08F4F' }} />
               DB
            </div>
          </div>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: '0.72rem',
            color: '#B08F4F',
            border: '1px solid #B08F4F',
            borderRadius: 3,
            padding: '3px 10px',
            letterSpacing: '0.05em',
          }}>
            {env}
          </div>
          <RunButton onRun={onRun} loading={loading} id="header-run-btn" />
        </div>
      </header>

      {/* Tally strip */}
      <TallyStrip results={results} />

      {/* Main content */}
      <main
        className="main-area"
        style={{ flex: 1, padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}
      >
        {error && <ErrorState message={error} onRun={onRun} loading={loading} />}

        {!error && results.length === 0 && !loading && (
          <EmptyState onRun={onRun} loading={loading} />
        )}

        {!error && loading && results.length === 0 && (
          <div style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#2f4455', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82rem',
          }}>
            Executing audit rules…
          </div>
        )}

        {sorted.map((rule, i) => (
          <FindingCard key={rule.rule_id} rule={rule} index={i} />
        ))}
      </main>
    </div>
  )
}

// ── Rule Editor Modal ────────────────────────────────────────────────────────

const Field = ({ label, required, children }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
    <label style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', fontWeight: 600, color: '#4a3d2c' }}>
      {label}
      {required && <span style={{ color: '#A23B2C', marginLeft: '4px' }}>*</span>}
    </label>
    {children}
  </div>
)

function RuleEditorModal({ rule, onClose, onSave, loading }) {
  const [formData, setFormData] = useState(() => {
    const cleanRule = { ...rule }
    delete cleanRule._filename
    delete cleanRule._file_path
    delete cleanRule._is_draft
    delete cleanRule.rule_id
    delete cleanRule.finding_count
    delete cleanRule.findings
    delete cleanRule.error
    delete cleanRule.query_run
    
    // Extract standard fields
    const { id, title, severity, remediation, query, narrative, isNew, ...rest } = cleanRule
    
    return {
      id: id || '',
      title: title || '',
      severity: severity || 'medium',
      remediation: remediation || '',
      query: query || '',
      narrative: narrative || '',
      advanced: Object.keys(rest).length > 0 ? JSON.stringify(rest, null, 2) : ''
    }
  })
  
  const [error, setError] = useState(null)

  const handleChange = (key, value) => {
    setFormData(prev => ({ ...prev, [key]: value }))
    setError(null)
  }

  const handleSave = () => {
    try {
      let parsedAdvanced = {}
      if (formData.advanced.trim()) {
        parsedAdvanced = JSON.parse(formData.advanced)
      }
      
      const finalRule = {
        id: formData.id,
        title: formData.title,
        severity: formData.severity,
        query: formData.query,
        ...parsedAdvanced
      }
      
      if (formData.remediation) finalRule.remediation = formData.remediation
      if (formData.narrative) finalRule.narrative = formData.narrative
      
      onSave(finalRule)
    } catch (err) {
      setError("Invalid JSON in Advanced Parameters: " + err.message)
    }
  }

  const inputStyle = { width: '100%', padding: '10px', borderRadius: 4, border: '1px solid #c7be9f', fontFamily: 'Inter, sans-serif', backgroundColor: '#fff', color: '#211C16' }
  const textareaStyle = { ...inputStyle, resize: 'vertical', minHeight: '80px', fontSize: '0.85rem' }
  const codeStyle = { ...textareaStyle, fontFamily: 'JetBrains Mono, monospace' }

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
      <div style={{ background: '#DCD3B8', padding: '28px', borderRadius: 8, width: '800px', maxWidth: '100%', maxHeight: '100%', display: 'flex', flexDirection: 'column', gap: '20px', boxShadow: '0 10px 25px rgba(0,0,0,0.5)', boxSizing: 'border-box', overflow: 'hidden' }}>
        <h2 style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.6rem', color: '#211C16', margin: 0, flexShrink: 0 }}>Edit Rule Metadata</h2>
        
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '20px', padding: '4px 12px 4px 4px', minHeight: 0 }}>
          
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '20px' }}>
            <div style={{ flex: '1 1 250px' }}>
              <Field label="Rule ID" required>
                <input style={inputStyle} value={formData.id} onChange={e => handleChange('id', e.target.value)} disabled={loading || !rule.isNew} />
              </Field>
            </div>
            <div style={{ flex: '1 1 250px' }}>
              <Field label="Severity" required>
                <select style={inputStyle} value={formData.severity} onChange={e => handleChange('severity', e.target.value)} disabled={loading}>
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </Field>
            </div>
          </div>

          <Field label="Title" required>
            <input style={inputStyle} value={formData.title} onChange={e => handleChange('title', e.target.value)} disabled={loading} />
          </Field>

          <Field label="Remediation">
            <textarea style={textareaStyle} value={formData.remediation} onChange={e => handleChange('remediation', e.target.value)} disabled={loading} />
          </Field>
          
          <Field label="Narrative (AI Prompt/Context)">
            <textarea style={textareaStyle} value={formData.narrative} onChange={e => handleChange('narrative', e.target.value)} disabled={loading} placeholder="Optional context for the AI summary..." />
          </Field>

          <Field label="SQL Query" required>
            <textarea style={{...codeStyle, minHeight: '200px'}} value={formData.query} onChange={e => handleChange('query', e.target.value)} disabled={loading} />
          </Field>

          <Field label="Advanced Parameters (JSON)">
            <textarea style={codeStyle} value={formData.advanced} onChange={e => handleChange('advanced', e.target.value)} disabled={loading} placeholder={'{\n  "threshold_days": 30\n}'} />
          </Field>
          
        </div>

        {error && <div style={{ color: '#A23B2C', fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', flexShrink: 0 }}>{error}</div>}
        
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '8px', flexShrink: 0 }}>
          <button onClick={onClose} disabled={loading} style={{ padding: '10px 20px', border: '1px solid #c7be9f', background: 'transparent', color: '#211C16', borderRadius: 4, cursor: loading ? 'not-allowed' : 'pointer', fontFamily: 'Inter, sans-serif', fontWeight: 600 }}>Cancel</button>
          <button onClick={handleSave} disabled={loading} style={{ padding: '10px 20px', background: '#211C16', color: '#DCD3B8', border: 'none', borderRadius: 4, cursor: loading ? 'not-allowed' : 'pointer', fontFamily: 'Inter, sans-serif', fontWeight: 600 }}>{loading ? 'Saving...' : 'Save Rule'}</button>
        </div>
      </div>
    </div>
  )
}

// ── Rules view ─────────────────────────────────────────────────────────────────
function RulesView({ results, onDeleteRule, onRuleUpdated }) {
  const [deletingId, setDeletingId] = useState(null)
  const [editingRule, setEditingRule] = useState(null)
  const [savingId, setSavingId] = useState(null)

  const handleDelete = async (ruleId, ruleTitle) => {
    if (!window.confirm(`Delete rule "${ruleTitle}"?\n\nThis will permanently remove the rule file. It will no longer run in future audits.`)) return
    setDeletingId(ruleId)
    try {
      const res = await apiFetch(`/audits/rules/${ruleId}`, { method: 'DELETE' })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        alert(`Failed to delete rule: ${err.detail ?? 'Unknown error'}`)
      } else {
        onDeleteRule(ruleId)
      }
    } catch (e) {
      alert(`Network error: ${e.message}`)
    } finally {
      setDeletingId(null)
    }
  }

  const handleSave = async (updatedData) => {
    const isNew = editingRule.isNew
    setSavingId(isNew ? 'new' : editingRule.rule_id)
    try {
      const endpoint = isNew ? '/audits/rules' : `/audits/rules/${editingRule.rule_id}`
      const method = isNew ? 'POST' : 'PUT'
      const res = await apiFetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedData)
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        alert(`Failed to save rule: ${err.detail ?? 'Unknown error'}`)
      } else {
        setEditingRule(null)
        if (onRuleUpdated) onRuleUpdated() // refresh results
      }
    } catch (e) {
      alert(`Network error: ${e.message}`)
    } finally {
      setSavingId(null)
    }
  }

  if (results.length === 0) {
    return (
      <div style={{ padding: '48px', textAlign: 'center' }}>
        <p style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.5rem', color: '#4a6070' }}>No rules loaded</p>
        <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.88rem', color: '#2f4455', marginTop: 12 }}>Run an audit to discover configured rules.</p>
        <button 
          onClick={() => setEditingRule({ isNew: true, id: '', title: '', severity: 'medium', query: '', remediation: '', narrative: '' })}
          style={{ marginTop: 24, padding: '8px 16px', background: '#2e6b2f', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontFamily: 'Inter, sans-serif', fontSize: '0.9rem', fontWeight: 600 }}
        >
          + Create Rule
        </button>
      </div>
    )
  }
  return (
    <div style={{ padding: '32px', display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 1200 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.8rem', color: '#DCD3B8', margin: 0 }}>Configured Rules</h1>
          <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.9rem', color: '#a0aab2', margin: '4px 0 0 0' }}>Manage the active audit rules currently enforced.</p>
        </div>
        <button 
          onClick={() => setEditingRule({ isNew: true, id: '', title: '', severity: 'medium', query: '', remediation: '', narrative: '' })}
          style={{ padding: '8px 16px', background: '#2e6b2f', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontFamily: 'Inter, sans-serif', fontSize: '0.9rem', fontWeight: 600 }}
        >
          + Create Rule
        </button>
      </div>
      
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
        {results.map(r => (
          <div key={r.rule_id} style={{
            background: '#DCD3B8',
            borderRadius: 8,
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', minWidth: 0 }}>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem', color: '#6b5d42', textTransform: 'uppercase', wordBreak: 'break-all' }}>{r.rule_id}</span>
                <h3 style={{ fontFamily: 'Inter, sans-serif', fontSize: '1.1rem', fontWeight: 600, color: '#211C16', margin: 0, wordBreak: 'break-word' }}>{r.title}</h3>
              </div>
              <span className={severityStampClass(r.severity)} style={{ flexShrink: 0 }}>{severityLabel(r.severity)}</span>
            </div>
            
            <div style={{ flex: 1, marginTop: '8px' }}>
              <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', color: '#5a4c3c', margin: 0, lineHeight: 1.5 }}>
                {r.remediation ? (
                   <><strong>Remediation:</strong> {r.remediation}</>
                ) : (
                   <span style={{ fontStyle: 'italic', color: '#8c7a6b' }}>No remediation provided.</span>
                )}
              </p>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '12px', paddingTop: '12px', borderTop: '1px solid rgba(0,0,0,0.1)' }}>
              <button
                onClick={() => setEditingRule(r)}
                disabled={deletingId === r.rule_id}
                title="Edit metadata"
                style={{
                  padding: '6px 16px', background: '#B08F4F', color: '#211C16', border: 'none', borderRadius: 4, cursor: deletingId === r.rule_id ? 'not-allowed' : 'pointer', fontFamily: 'Inter, sans-serif', fontSize: '0.8rem', fontWeight: 600
                }}
              >
                Edit
              </button>
              <button
                id={`delete-rule-${r.rule_id}`}
                onClick={() => handleDelete(r.rule_id, r.title)}
                disabled={deletingId === r.rule_id}
                title="Delete this rule"
                style={{
                  padding: '6px 16px', background: deletingId === r.rule_id ? '#7a3020' : '#A23B2C', color: '#fff', border: 'none', borderRadius: 4, cursor: deletingId === r.rule_id ? 'not-allowed' : 'pointer', fontFamily: 'Inter, sans-serif', fontSize: '0.8rem', fontWeight: 600
                }}
              >
                {deletingId === r.rule_id ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        ))}
      </div>

      {editingRule && (
        <RuleEditorModal 
          rule={editingRule} 
          onClose={() => setEditingRule(null)} 
          onSave={handleSave} 
          loading={savingId === editingRule.rule_id} 
        />
      )}
    </div>
  )
}

// ── Findings view ──────────────────────────────────────────────────────────────
function FindingsView({ results }) {
  const withFindings = results.filter(r => r.finding_count > 0)
  const sorted = sortBySeverity(withFindings)
  
  if (sorted.length === 0) {
    return (
      <div style={{ padding: '48px', textAlign: 'center' }}>
        <p style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.5rem', color: '#4a6070' }}>No active findings</p>
        <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.88rem', color: '#2f4455', marginTop: 12 }}>Run an audit. Findings will appear here if any rule conditions are met.</p>
      </div>
    )
  }

  return (
    <div style={{ padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h1 style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.5rem', color: '#DCD3B8', marginBottom: 8 }}>Active Findings</h1>
      {sorted.map((rule, i) => (
        <FindingCard key={rule.rule_id} rule={rule} index={i} />
      ))}
    </div>
  )
}

// ── Reports view ───────────────────────────────────────────────────────────────
function ReportsView({ runId }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const generateReport = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch('/audits/report?format=json')
      if (!res.ok) throw new Error('Failed to generate report')
      const data = await res.json()
      setReport(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const downloadPdf = () => {
    window.print();
  }

  return (
    <div className="reports-view">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, width: '100%', boxSizing: 'border-box' }}>
        <h1 style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.5rem', color: '#DCD3B8' }}>Executive Narrative Report</h1>
        <div style={{ display: 'flex', gap: 12 }}>
          {report && (
            <button onClick={downloadPdf} style={{
              padding: '9px 20px', background: 'transparent', color: '#DCD3B8', 
              border: '1px solid #DCD3B8', borderRadius: 4, cursor: 'pointer',
              fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', fontWeight: 600
            }} title="Use browser print to save as PDF with selectable text">
              Save as PDF
            </button>
          )}
          <RunButton onRun={generateReport} loading={loading} id="generate-report-btn" label="Generate Narrative" />
        </div>
      </div>
      
      {error && <div style={{ color: '#A23B2C', fontFamily: 'Inter, sans-serif', width: '100%', boxSizing: 'border-box' }}>Error: {error}</div>}
      
      {report && (
        <div id="report-content" className="report-card" style={{ width: '100%', boxSizing: 'border-box', minWidth: 0, overflowX: 'hidden' }}>
          {/* Header */}
          <div style={{ borderBottom: '2px solid #211C16', paddingBottom: 16, marginBottom: 24, width: '100%', boxSizing: 'border-box' }}>
            <h1 style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '2rem', margin: 0 }}>Audit Case File</h1>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.8rem', color: '#6b5d42', marginTop: 8 }}>
              Case ID: {runId} <br/>
              Generated: {report.executed_at} <br/>
              AI Model: {report.narrative_model}
            </div>
          </div>

          {/* Executive Summary */}
          <h2 style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.4rem', marginBottom: 12 }}>Executive Summary</h2>
          <div className="markdown-body" style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: 32, width: '100%', boxSizing: 'border-box', overflowWrap: 'break-word', wordBreak: 'break-word' }}>
            {report.narrative 
              ? <div dangerouslySetInnerHTML={{ __html: safeMarkdown(report.narrative) }} />
              : <p>No narrative generated.</p>
            }
          </div>

          {/* Active Findings */}
          <h2 style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.4rem', marginBottom: 12 }}>Active Findings Detail</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24, marginBottom: 32, width: '100%', boxSizing: 'border-box', minWidth: 0 }}>
            {report.results.filter(r => r.finding_count > 0).length === 0 ? (
              <p style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.9rem' }}>No anomalies detected in this run.</p>
            ) : (
              report.results.filter(r => r.finding_count > 0).map(rule => (
                <div key={rule.rule_id} style={{ pageBreakInside: 'avoid', background: 'rgba(255,255,255,0.4)', padding: 16, borderRadius: 4, borderLeft: `4px solid ${rule.severity === 'critical' ? '#A23B2C' : rule.severity === 'high' ? '#D97706' : '#B08F4F'}`, width: '100%', boxSizing: 'border-box', minWidth: 0, overflow: 'hidden' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12, gap: 12, width: '100%', boxSizing: 'border-box' }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem', color: '#6b5d42', wordBreak: 'break-all' }}>{rule.rule_id}</div>
                      <h3 style={{ fontFamily: 'Inter, sans-serif', fontSize: '1.1rem', margin: '4px 0', fontWeight: 600, wordBreak: 'break-word' }}>{rule.title}</h3>
                    </div>
                    <span className={severityStampClass(rule.severity)} style={{ position: 'static', flexShrink: 0 }}>{severityLabel(rule.severity)}</span>
                  </div>
                  {/* Findings Table */}
                  <div style={{ overflowX: 'auto', width: '100%', boxSizing: 'border-box' }}>
                    <table style={{ width: '100%', fontSize: '0.8rem', fontFamily: 'Inter, sans-serif', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid #c7be9f', textAlign: 'left' }}>
                          {Object.keys(rule.findings[0] || {}).map(k => (
                            <th key={k} style={{ padding: '6px 8px', fontWeight: 600, color: '#4a3d2c' }}>{k}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {rule.findings.map((f, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid rgba(199, 190, 159, 0.5)' }}>
                            {Object.values(f).map((val, j) => (
                              <td key={j} style={{ padding: '6px 8px' }}>{String(val)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Configured Rules Evaluated */}
          <h2 style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.4rem', marginBottom: 12 }}>Rules Evaluated</h2>
          <div style={{ overflowX: 'auto', width: '100%', boxSizing: 'border-box' }}>
            <table style={{ width: '100%', fontSize: '0.85rem', fontFamily: 'Inter, sans-serif', borderCollapse: 'collapse', background: 'rgba(255,255,255,0.4)', borderRadius: 4, overflow: 'hidden' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #c7be9f', textAlign: 'left' }}>
                  <th style={{ padding: '8px 12px' }}>Rule ID</th>
                  <th style={{ padding: '8px 12px' }}>Title</th>
                  <th style={{ padding: '8px 12px' }}>Severity</th>
                </tr>
              </thead>
              <tbody>
                {report.results.map(r => (
                  <tr key={r.rule_id} style={{ borderBottom: '1px solid rgba(199, 190, 159, 0.5)' }}>
                    <td style={{ padding: '8px 12px', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}>{r.rule_id}</td>
                    <td style={{ padding: '8px 12px', fontWeight: 500 }}>{r.title}</td>
                    <td style={{ padding: '8px 12px' }}>{severityLabel(r.severity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {!report && !loading && !error && (
        <p style={{ fontFamily: 'Inter, sans-serif', color: '#4a6070', fontSize: '0.9rem' }}>Click "Generate Narrative" above to run the checks and generate an AI-powered executive narrative.</p>
      )}
    </div>
  )
}

// ── Policies view ─────────────────────────────────────────────────────────────
function PoliciesView() {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const [uploadError, setUploadError] = useState(null)

  const [drafts, setDrafts] = useState([])
  const [draftsLoading, setDraftsLoading] = useState(true)
  const [editingRule, setEditingRule] = useState(null)
  const [savingId, setSavingId] = useState(null)

  const fetchDrafts = useCallback(async () => {
    try {
      const res = await apiFetch('/policies/rules/draft')
      if (res.ok) {
        const data = await res.json()
        setDrafts(data.draft_rules || [])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setDraftsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDrafts()
  }, [fetchDrafts])

  const handleFileChange = (e) => {
    setFile(e.target.files[0])
    setUploadResult(null)
    setUploadError(null)
  }

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setUploadError(null)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await apiFetch('/policies/upload', {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error('Upload failed')
      const data = await res.json()
      setUploadResult(data)
      fetchDrafts()
    } catch (err) {
      setUploadError(err.message)
    } finally {
      setUploading(false)
    }
  }

  const handleApprove = async (ruleId) => {
    try {
      const res = await apiFetch(`/policies/rules/draft/${ruleId}/approve`, { method: 'POST' })
      if (res.ok) {
        setDrafts(prev => prev.filter(d => d.id !== ruleId))
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleReject = async (ruleId) => {
    try {
      const res = await apiFetch(`/policies/rules/draft/${ruleId}/reject`, { method: 'DELETE' })
      if (res.ok) {
        setDrafts(prev => prev.filter(d => d.id !== ruleId))
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleSaveDraft = async (updatedData) => {
    setSavingId(editingRule.id)
    try {
      const res = await apiFetch(`/policies/rules/draft/${editingRule.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedData)
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        alert(`Failed to update draft: ${err.detail ?? 'Unknown error'}`)
      } else {
        setEditingRule(null)
        fetchDrafts()
      }
    } catch (e) {
      alert(`Network error: ${e.message}`)
    } finally {
      setSavingId(null)
    }
  }

  return (
    <div className="policies-view">
      <h1 style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.5rem', color: '#DCD3B8' }}>Policy Document Ingestion</h1>
      
      <div className="policies-card">
        <h2 style={{ fontFamily: 'Inter, sans-serif', fontSize: '1.1rem', fontWeight: 600, color: '#211C16', marginBottom: 12 }}>Upload PDF Policy</h2>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <input type="file" accept=".pdf" onChange={handleFileChange} style={{ fontFamily: 'Inter, sans-serif', color: '#211C16', maxWidth: '100%' }} />
          <RunButton onRun={handleUpload} loading={uploading} label="Ingest Policy" id="upload-policy-btn" />
        </div>
        
        {uploadError && <div style={{ color: '#A23B2C', marginTop: 12, fontFamily: 'Inter, sans-serif' }}>Error: {uploadError}</div>}
        
        {uploadResult && (
          <div style={{ marginTop: 24, background: 'rgba(255,255,255,0.5)', padding: 16, borderRadius: 4, color: '#211C16' }}>
            <h3 style={{ fontFamily: 'Inter, sans-serif', fontWeight: 600, marginBottom: 8 }}>Ingestion Result for {uploadResult.source_pdf}</h3>
            <ul style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.9rem', lineHeight: 1.6, paddingLeft: 20 }}>
              <li>Total clauses parsed: {uploadResult.summary.total_clauses}</li>
              <li>Existing rules updated: {uploadResult.summary.rules_updated}</li>
              <li>Draft rules created: {uploadResult.summary.rules_created}</li>
              <li>Clauses skipped (non-auditable): {uploadResult.summary.clauses_skipped}</li>
            </ul>
          </div>
        )}
      </div>

      <div style={{ marginTop: 16, width: '100%', boxSizing: 'border-box' }}>
        <h2 style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.4rem', color: '#DCD3B8', marginBottom: 16 }}>Pending Draft Rules</h2>
        {draftsLoading ? (
          <p style={{ color: '#4a6070' }}>Loading drafts...</p>
        ) : drafts.length === 0 ? (
          <p style={{ color: '#4a6070', fontFamily: 'Inter, sans-serif' }}>No draft rules pending review.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, width: '100%', boxSizing: 'border-box' }}>
            {drafts.map(draft => (
              <div key={draft.id} style={{ background: '#DCD3B8', padding: 16, borderRadius: 6, color: '#211C16', width: '100%', boxSizing: 'border-box', overflow: 'hidden' }}>
                <div className="draft-card-header">
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem', color: '#6b5d42', wordBreak: 'break-all' }}>{draft.id}</div>
                    <h3 style={{ fontFamily: 'Inter, sans-serif', fontSize: '1.1rem', margin: '4px 0', fontWeight: 600, wordBreak: 'break-word' }}>{draft.title}</h3>
                  </div>
                  <div className="draft-card-buttons">
                    <button onClick={() => setEditingRule(draft)} style={{ background: '#B08F4F', color: '#211C16' }}>Edit</button>
                    <button onClick={() => handleReject(draft.id)} style={{ background: '#A23B2C', color: '#fff' }}>Deny</button>
                    <button onClick={() => handleApprove(draft.id)} style={{ background: '#2e6b2f', color: '#fff' }}>Approve</button>
                  </div>
                </div>
                <pre className="draft-json-preview">
                  {JSON.stringify(draft, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>
      {editingRule && (
        <RuleEditorModal
          rule={editingRule}
          onClose={() => setEditingRule(null)}
          onSave={handleSaveDraft}
          loading={savingId === editingRule.id}
        />
      )}
    </div>
  )
}

// ── Settings view ──────────────────────────────────────────────────────────────
function SettingsView() {
  const [config, setConfig] = useState({
    ai_provider: '',
    gemini_api_key: '',
    gemini_model: '',
    ollama_base_url: '',
    ollama_model: ''
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    apiFetch('/audits/settings')
      .then(r => r.json())
      .then(data => {
        setConfig(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const handleChange = (e) => {
    setConfig({ ...config, [e.target.name]: e.target.value })
  }

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true)
    setMsg('')
    try {
      const res = await apiFetch('/audits/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      })
      if (res.ok) {
        setMsg('Settings saved successfully.')
      } else {
        setMsg('Failed to save settings.')
      }
    } catch {
      setMsg('Error saving settings.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div style={{ padding: 48, color: '#4a6070', fontFamily: 'Inter, sans-serif' }}>Loading settings...</div>

  return (
    <div style={{ padding: '32px', display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 600 }}>
      <h1 style={{ fontFamily: 'Newsreader, Georgia, serif', fontSize: '1.5rem', color: '#DCD3B8' }}>System Settings</h1>
      
      <form onSubmit={handleSave} style={{ background: '#DCD3B8', padding: '24px', borderRadius: 6, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <label style={{ display: 'block', fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', fontWeight: 600, color: '#211C16', marginBottom: 4 }}>AI Provider</label>
          <select name="ai_provider" value={config.ai_provider} onChange={handleChange} style={{ width: '100%', padding: '8px', borderRadius: 4, border: '1px solid #c7be9f', fontFamily: 'Inter, sans-serif', color: '#211C16', backgroundColor: '#FFFFFF' }}>
            <option value="gemini">Google Gemini</option>
            <option value="ollama">Local Ollama</option>
          </select>
        </div>

        {config.ai_provider === 'gemini' && (
          <>
            <div>
              <label style={{ display: 'block', fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', fontWeight: 600, color: '#211C16', marginBottom: 4 }}>Gemini API Key</label>
              <input type="password" name="gemini_api_key" value={config.gemini_api_key} onChange={handleChange} style={{ width: '100%', padding: '8px', borderRadius: 4, border: '1px solid #c7be9f', fontFamily: 'Inter, sans-serif', color: '#211C16', backgroundColor: '#FFFFFF' }} />
            </div>
            <div>
              <label style={{ display: 'block', fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', fontWeight: 600, color: '#211C16', marginBottom: 4 }}>Gemini Model</label>
              <input type="text" name="gemini_model" value={config.gemini_model} onChange={handleChange} style={{ width: '100%', padding: '8px', borderRadius: 4, border: '1px solid #c7be9f', fontFamily: 'Inter, sans-serif', color: '#211C16', backgroundColor: '#FFFFFF' }} />
            </div>
          </>
        )}

        {config.ai_provider === 'ollama' && (
          <>
            <div>
              <label style={{ display: 'block', fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', fontWeight: 600, color: '#211C16', marginBottom: 4 }}>Ollama Base URL</label>
              <input type="text" name="ollama_base_url" value={config.ollama_base_url} onChange={handleChange} style={{ width: '100%', padding: '8px', borderRadius: 4, border: '1px solid #c7be9f', fontFamily: 'Inter, sans-serif', color: '#211C16', backgroundColor: '#FFFFFF' }} />
            </div>
            <div>
              <label style={{ display: 'block', fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', fontWeight: 600, color: '#211C16', marginBottom: 4 }}>Ollama Model</label>
              <input type="text" name="ollama_model" value={config.ollama_model} onChange={handleChange} style={{ width: '100%', padding: '8px', borderRadius: 4, border: '1px solid #c7be9f', fontFamily: 'Inter, sans-serif', color: '#211C16', backgroundColor: '#FFFFFF' }} />
            </div>
          </>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12 }}>
          <button type="submit" disabled={saving} style={{ padding: '8px 16px', background: '#211C16', color: '#DCD3B8', border: 'none', borderRadius: 4, cursor: saving ? 'not-allowed' : 'pointer', fontFamily: 'Inter, sans-serif', fontWeight: 600 }}>
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
          {msg && <span style={{ fontFamily: 'Inter, sans-serif', fontSize: '0.85rem', color: msg.includes('Error') || msg.includes('Failed') ? '#A23B2C' : '#2e6b2f' }}>{msg}</span>}
        </div>
      </form>
    </div>
  )
}

// ── Root App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [activeNav, setActiveNav] = useState('dashboard')
  const [results, setResults]     = useState([])
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [executedAt, setExecutedAt] = useState(null)
  const [runId]                   = useState(makeRunId)

  const [health, setHealth]       = useState({ api: 'checking', db: 'checking' })

  // Read environment from Vite env or fallback
  const env = import.meta.env.VITE_ENV ?? 'development'

  const checkHealth = useCallback(async () => {
    try {
      const res = await apiFetch('/health')
      if (res.ok) {
        const data = await res.json()
        setHealth({ api: data.status === 'healthy' ? 'ok' : 'error', db: data.db_status === 'ok' ? 'ok' : 'error' })
      } else {
        setHealth({ api: 'error', db: 'error' })
      }
    } catch {
      setHealth({ api: 'error', db: 'error' })
    }
  }, [])

  useEffect(() => {
    checkHealth()
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [checkHealth])

  const runAudit = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch('/audits/run')
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`Server returned ${res.status}: ${text.slice(0, 200)}`)
      }
      const data = await res.json()
      setResults(data.results ?? [])
      setExecutedAt(data.executed_at ?? null)
    } catch (err) {
      // Distinguish network failure from server error
      if (err instanceof TypeError) {
        setError('Could not reach the audit server. Check that FastAPI is running on localhost:8000.')
      } else {
        setError(err.message)
      }
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [])

  // Auto-run on mount
  useEffect(() => {
    runAudit()
  }, [runAudit])

  return (
    <>
      <div style={{ display: 'flex', minHeight: '100vh' }}>
        {/* Fixed left nav rail */}
        <NavRail active={activeNav} setActive={setActiveNav} />

        {/* Main scrollable content area (offset by nav width on desktop) */}
        <div
          className="main-content"
          style={{
            flex: 1,
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {activeNav === 'dashboard' && (
            <Dashboard
              runId={runId}
              env={env}
              results={results}
              loading={loading}
              error={error}
              onRun={runAudit}
              executedAt={executedAt}
              health={health}
            />
          )}
          {activeNav === 'rules'    && <RulesView results={results} onDeleteRule={(ruleId) => setResults(prev => prev.filter(r => r.rule_id !== ruleId))} onRuleUpdated={runAudit} />}
          {activeNav === 'findings' && <FindingsView results={results} />}
          {activeNav === 'reports'  && <ReportsView runId={runId} />}
          {activeNav === 'policies' && <PoliciesView />}
          {activeNav === 'settings' && <SettingsView />}
        </div>

        {/* Mobile bottom nav */}
        <BottomNav active={activeNav} setActive={setActiveNav} />
      </div>
    </>
  )
}
