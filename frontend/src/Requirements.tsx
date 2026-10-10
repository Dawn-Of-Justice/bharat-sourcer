import { useId, useState } from 'react'
import type { PartRequirement } from './api'

export default function Requirements({
  value,
  onChange,
  disabled = false,
  inline = false,
}: {
  value: PartRequirement[]
  onChange: (value: PartRequirement[]) => void
  disabled?: boolean
  inline?: boolean
}) {
  const [open, setOpen] = useState(false)
  const detailsId = useId()
  // An edited row becomes the user's own: drop origin/reason so the backend defaults it to 'user'.
  function patch(index: number, change: Partial<PartRequirement>) {
    onChange(
      value.map((item, i) => {
        if (i !== index) return item
        const { origin: _origin, reason: _reason, ...rest } = item
        return { ...rest, ...change }
      }),
    )
  }
  return (
    <div className={`requirements-editor ${open || inline ? 'is-open' : ''}`}>
      {inline ? (
        <h4 className="build-details-heading">Build details</h4>
      ) : (
        <button
          type="button"
          className="build-details-button"
          aria-expanded={open}
          aria-controls={detailsId}
          disabled={disabled}
          onClick={() => setOpen(current => !current)}
        >
          <span className="details-button-icon" aria-hidden="true">
            ≡
          </span>
          <span>
            Build details{' '}
            <small>
              {value.length
                ? `${value.length} ${value.length === 1 ? 'detail' : 'details'} to check`
                : 'Optional · size, voltage & more'}
            </small>
          </span>
          <span className="disclosure-chevron" aria-hidden="true" />
        </button>
      )}
      <div id={detailsId} hidden={!open && !inline} className="build-details-content">
        <p className="build-details-help">
          Tell us what this part needs to do so we can check seller matches. You can keep the suggested details, change
          them, or leave this empty if you’re unsure.
        </p>
        <div className="detail-example">
          <strong>For example</strong>
          <span>
            A part that runs on 5 volts: <b>Voltage</b> → <b>Exactly</b> → <b>5</b> → <b>V</b>
          </span>
        </div>
        {value.map((item, index) => (
          <div className="requirement-row" key={index}>
            <label>
              What matters?
              <input
                disabled={disabled}
                maxLength={100}
                value={item.name}
                onChange={event => patch(index, { name: event.target.value })}
                placeholder="Voltage, width, connector…"
              />
            </label>
            <label>
              Must be
              <select
                disabled={disabled}
                value={item.operator}
                onChange={event => patch(index, { operator: event.target.value as PartRequirement['operator'] })}
              >
                <option value="equals">Exactly</option>
                <option value="at_least">At least</option>
                <option value="at_most">No more than</option>
              </select>
            </label>
            <label>
              Value or type
              <input
                disabled={disabled}
                maxLength={200}
                value={item.value}
                onChange={event => patch(index, { value: event.target.value })}
                placeholder="5, 20, USB-C…"
              />
            </label>
            <label>
              Unit (if needed)
              <input
                disabled={disabled}
                maxLength={40}
                value={item.unit ?? ''}
                onChange={event => patch(index, { unit: event.target.value })}
                placeholder="V, mm…"
              />
            </label>
            <button
              className="remove-requirement"
              type="button"
              disabled={disabled}
              aria-label={`Remove requirement ${index + 1}`}
              onClick={() => onChange(value.filter((_, i) => i !== index))}
            >
              Remove
            </button>
            {item.origin === 'inferred' && (
              <small className="requirement-origin">
                <span className="inferred-tag">Suggested</span>{' '}
                {item.reason || 'Based on the project. Check this value before continuing.'}
              </small>
            )}
          </div>
        ))}
        <button
          className="add-requirement"
          type="button"
          disabled={disabled || value.length >= 20}
          onClick={() => onChange([...value, { name: '', value: '', unit: '', operator: 'equals' }])}
        >
          <span aria-hidden="true">+</span> {value.length ? 'Add another detail' : 'Add a detail'}
        </button>
        {value.length >= 20 && <small className="requirements-limit">Maximum 20 requirements per part.</small>}
      </div>
    </div>
  )
}

// The API replaces the whole list, so untouched inferred rows keep their origin and reason; everything else is sent as the user's.
export function requirementPayload(value: PartRequirement[]): PartRequirement[] {
  return value.map(({ name, value, unit, operator, origin, reason }) => ({
    name: name.trim(),
    value: value.trim(),
    unit: unit?.trim() || null,
    operator,
    ...(origin === 'inferred' ? { origin, reason: reason ?? null } : {}),
  }))
}

export function validRequirements(value: PartRequirement[]) {
  return value.every(item => item.name.trim().length > 0 && item.value.trim().length > 0)
}
