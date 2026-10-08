import type { SafetyFlag } from './api'

// Deterministic rule checks from the backend (docs/contracts/safety-flags.md). Text is rendered verbatim.
const order: SafetyFlag['code'][] = ['MAINS', 'LIPO', 'HIGH_CURRENT', 'LEVEL_SHIFT']
const severity: Record<SafetyFlag['severity'], { icon: string; label: string }> = { danger: { icon: '⛔', label: 'Danger' }, warning: { icon: '⚠', label: 'Warning' }, caution: { icon: '', label: 'Caution' } }
const sorted = (flags: SafetyFlag[]) => [...flags].sort((a, b) => order.indexOf(a.code) - order.indexOf(b.code))

function lineLabel(lineId: string, names: Record<string, string>) {
  return names[lineId] ? `${lineId} · ${names[lineId]}` : lineId
}

// Keep checks beside the report. Mains guidance stays expanded because it needs immediate attention.
export default function SafetyBanners({ flags, lineNames = {}, onShowLine }: { flags?: SafetyFlag[] | null; lineNames?: Record<string, string>; onShowLine?: (lineId: string) => void }) {
  if (!flags?.length) return null
  return <section className="safety-banners" aria-label="Safety checks">
    <h3>Build checks <span>{flags.length}</span></h3>
    <p className="safety-label">Automatic checks · review before ordering</p>
    {sorted(flags).map(flag => <details key={flag.code} className={`safety-banner safety-${flag.severity}`} open={flag.code === 'MAINS' ? true : undefined}>
      <summary><span className="safety-severity"><span className="safety-severity-icon" aria-hidden="true">{severity[flag.severity].icon}</span>{severity[flag.severity].label}</span><strong>{flag.title}</strong></summary>
      <div className="safety-banner-content" role={flag.severity === 'danger' ? 'alert' : undefined}>
        <p>{flag.message}</p>
        {flag.guidance.length > 0 && <ul className="safety-guidance" aria-label={`${flag.title}: checklist`}>{flag.guidance.map((entry, index) => <li key={index}>{entry}</li>)}</ul>}
        {flag.line_ids.length > 0 && <p className="safety-lines">Parts involved: {flag.line_ids.map((id, index) => <span key={id}>{index > 0 && ', '}<a href={`#line-${id}`} onClick={onShowLine ? event => { event.preventDefault(); onShowLine(id) } : undefined}>{lineLabel(id, lineNames)}</a></span>)}</p>}
        {flag.triggers?.length ? <details className="safety-why"><summary>What triggered this</summary><ul>{flag.triggers.map((trigger, index) => <li key={index}>{trigger.line_id ? `${trigger.line_id} · ` : ''}{trigger.field}: “{trigger.matched}”</li>)}</ul></details> : null}
      </div>
    </details>)}
  </section>
}

// Small per-row badges naming each flag that lists this line.
export function SafetyLineBadges({ flags, lineId }: { flags?: SafetyFlag[] | null; lineId: string }) {
  const matching = sorted(flags ?? []).filter(flag => flag.line_ids.includes(lineId))
  if (!matching.length) return null
  return <>{matching.map(flag => <span key={flag.code} className={`safety-badge safety-${flag.severity}`} title={flag.title}>{severity[flag.severity].icon && <span aria-hidden="true">{severity[flag.severity].icon}</span>} {flag.code}</span>)}</>
}
