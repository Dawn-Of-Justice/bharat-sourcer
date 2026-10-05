import type { PartRequirement } from './api'

export default function Requirements({ value, onChange, disabled = false }: { value: PartRequirement[]; onChange: (value: PartRequirement[]) => void; disabled?: boolean }) {
  function patch(index: number, change: Partial<PartRequirement>) {
    onChange(value.map((item, i) => i === index ? { ...item, ...change } : item))
  }
  return <div className="requirements-editor"><div className="requirements-heading"><strong>Build requirements</strong><button type="button" disabled={disabled || value.length >= 20} onClick={() => onChange([...value, { name: '', value: '', unit: '', operator: 'equals' }])}>+ Add requirement</button></div><p>Describe only constraints you know. These are your inputs, not verified facts from the source.</p>{value.map((item, index) => <div className="requirement-row" key={index}><label>Property<input disabled={disabled} maxLength={100} value={item.name} onChange={event => patch(index, { name: event.target.value })} placeholder="e.g. bore diameter" /></label><label>Rule<select disabled={disabled} value={item.operator} onChange={event => patch(index, { operator: event.target.value as PartRequirement['operator'] })}><option value="equals">Equals</option><option value="at_least">At least</option><option value="at_most">At most</option></select></label><label>Value<input disabled={disabled} maxLength={200} value={item.value} onChange={event => patch(index, { value: event.target.value })} placeholder="e.g. 8" /></label><label>Unit<input disabled={disabled} maxLength={40} value={item.unit ?? ''} onChange={event => patch(index, { unit: event.target.value })} placeholder="optional" /></label><button type="button" disabled={disabled} aria-label={`Remove requirement ${index + 1}`} onClick={() => onChange(value.filter((_, i) => i !== index))}>Remove</button></div>)}</div>
}

export function validRequirements(value: PartRequirement[]) {
  return value.every(item => item.name.trim().length > 0 && item.value.trim().length > 0)
}
