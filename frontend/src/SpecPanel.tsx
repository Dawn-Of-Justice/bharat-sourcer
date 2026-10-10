import { useState } from 'react'
import type { BuyableSpec, SpecParam } from './api'

// The line's buying spec (docs/contracts/part-matching.md). AI-inferred values are labelled; edits are saved as the user's spec.
const categoryLabel: Record<BuyableSpec['category'], string> = {
  resistor: 'Resistor',
  capacitor_electrolytic: 'Electrolytic capacitor',
  capacitor_ceramic: 'Ceramic capacitor',
  led: 'LED',
  ldr: 'Light-dependent resistor (LDR)',
  wire: 'Wire',
  diode: 'Diode',
  transistor: 'Transistor',
  ic: 'IC',
  module: 'Module',
  board: 'Board',
  sensor: 'Sensor',
  connector: 'Connector',
  switch: 'Switch',
  battery: 'Battery',
  other: 'Other part',
}
const mountLabel: Record<BuyableSpec['mount'], string> = {
  tht: 'Through-hole (THT)',
  smd: 'Surface-mount (SMD)',
  any: 'Any mount',
}
const originLabel: Record<BuyableSpec['origin'], string> = {
  ai_inferred: 'AI-inferred buying spec — check it',
  seed: 'Built from the part name only',
  user: 'Your buying spec',
}
const operatorLabel: Record<SpecParam['operator'], string> = {
  equals: '',
  at_least: 'at least ',
  at_most: 'at most ',
  between: '',
}
const valueCategories = ['resistor', 'ldr', 'capacitor_electrolytic', 'capacitor_ceramic']

const paramText = (param: SpecParam) =>
  `${operatorLabel[param.operator]}${param.value}${param.operator === 'between' && param.value_max ? ` – ${param.value_max}` : ''}`

function OriginTag({ origin, reason }: { origin?: string; reason?: string | null }) {
  if (origin === 'inferred')
    return (
      <>
        <span className="inferred-tag">inferred</span>
        {reason ? <small> {reason}</small> : null}
      </>
    )
  if (origin === 'stated') return <span className="spec-tag">stated in source</span>
  if (origin === 'user') return <span className="spec-tag">yours</span>
  return null
}

export default function SpecPanel({
  value,
  onChange,
  disabled = false,
}: {
  value: BuyableSpec | null | undefined
  onChange: (value: BuyableSpec) => void
  disabled?: boolean
}) {
  const [editing, setEditing] = useState(false)
  // The project's assumed range stays visible as a hint after the user replaces it with a value.
  const [ranges] = useState(
    () => value?.params.filter(param => param.operator === 'between' && param.origin !== 'user') ?? [],
  )
  if (!value) return null
  const spec = value
  const edit = (change: Partial<BuyableSpec>) => onChange({ ...spec, ...change, origin: 'user' })
  // An edited row becomes the user's: the server re-derives its unit and SI value.
  const patch = (index: number, change: Partial<SpecParam>) =>
    edit({
      params: spec.params.map((param, i) =>
        i === index
          ? {
              ...param,
              ...change,
              origin: 'user',
              reason: null,
              ...('value' in change || 'value_max' in change ? { unit: null, si_value: null, si_value_max: null } : {}),
            }
          : param,
      ),
    })
  function addValue() {
    setEditing(true)
    const name = spec.category.startsWith('capacitor')
      ? 'capacitance'
      : valueCategories.includes(spec.category)
        ? 'resistance'
        : 'value'
    // The new exact value replaces an assumed range for the same property.
    const kept = spec.params.filter(param => !(param.operator === 'between' && param.name.toLowerCase() === name))
    if (kept.length < 12)
      edit({ params: [...kept, { name, value: '', operator: 'equals', required: true, origin: 'user' }] })
  }
  return (
    <div className="spec-panel">
      <div className="spec-heading">
        <div>
          <strong>Buying spec</strong>{' '}
          <span className={spec.origin === 'user' ? 'spec-tag' : 'inferred-tag'}>{originLabel[spec.origin]}</span>
          <p>
            What we search sellers for.{' '}
            {spec.origin === 'user'
              ? 'Saved as yours when you confirm.'
              : 'Correct anything that is wrong before confirming.'}
          </p>
        </div>
        {!editing && (
          <button
            type="button"
            className="nav-cta spec-edit-button"
            disabled={disabled}
            onClick={() => setEditing(true)}
          >
            Edit buying spec
          </button>
        )}
      </div>
      {spec.needs_value && !specPayload(spec).needs_value ? (
        <p className="needs-value-filled">
          <span aria-hidden="true">✓</span> Value added. It is saved as yours when you confirm.
        </p>
      ) : (
        spec.needs_value && (
          <div className="needs-value" role="note">
            <strong>
              <span aria-hidden="true">⚠</span> Needs value
            </strong>
            <p>
              {spec.needs_value_reason || 'The source does not state this part’s value.'} We won’t search sellers blind
              for this part; add the value you need.
            </p>
            {ranges.map((param, index) => (
              <p key={index}>
                Assumed from the project:{' '}
                <b>
                  {param.name} {paramText(param)}
                </b>
                {param.reason ? ` — ${param.reason}` : ''}
              </p>
            ))}
            {!editing && (
              <button type="button" className="add-requirement" disabled={disabled} onClick={addValue}>
                <span className="add-requirement-icon" aria-hidden="true">
                  +
                </span>
                <span>Add the value</span>
              </button>
            )}
          </div>
        )
      )}
      <dl className="spec-facts">
        <div>
          <dt>Category</dt>
          <dd>{categoryLabel[spec.category] ?? spec.category}</dd>
        </div>
        <div>
          <dt>Mount</dt>
          <dd>
            {mountLabel[spec.mount]}{' '}
            {spec.mount_origin === 'inferred' ? (
              <OriginTag origin="inferred" reason={spec.mount_reason} />
            ) : spec.mount_origin === 'stated' ? (
              <OriginTag origin="stated" />
            ) : spec.mount_origin === 'user' ? (
              <OriginTag origin="user" />
            ) : spec.mount === 'any' ? null : (
              <small>default</small>
            )}
            {spec.mount_origin !== 'inferred' && spec.mount_reason ? <small> {spec.mount_reason}</small> : null}
          </dd>
        </div>
        {spec.params
          .filter(param => param.value.trim())
          .map((param, index) => (
            <div key={index}>
              <dt>{param.name}</dt>
              <dd>
                {paramText(param)}
                {param.required === false && <small> (optional)</small>}{' '}
                <OriginTag origin={param.origin} reason={param.reason} />
              </dd>
            </div>
          ))}
      </dl>
      {spec.reasons?.length ? (
        <ul className="spec-reasons">
          {spec.reasons.map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      ) : null}
      {editing && (
        <div className="spec-editor">
          <label className="spec-mount">
            Mount
            <select
              disabled={disabled}
              value={spec.mount}
              onChange={event =>
                edit({ mount: event.target.value as BuyableSpec['mount'], mount_origin: 'user', mount_reason: null })
              }
            >
              <option value="any">Any mount</option>
              <option value="tht">Through-hole (THT)</option>
              <option value="smd">Surface-mount (SMD)</option>
            </select>
          </label>
          {spec.params.map((param, index) => (
            <div className="requirement-row spec-param-row" key={index}>
              <label>
                Property
                <input
                  disabled={disabled}
                  maxLength={60}
                  value={param.name}
                  onChange={event => patch(index, { name: event.target.value })}
                  placeholder="e.g. resistance"
                />
              </label>
              <label>
                Rule
                <select
                  disabled={disabled}
                  value={param.operator}
                  onChange={event => patch(index, { operator: event.target.value as SpecParam['operator'] })}
                >
                  <option value="equals">Equals</option>
                  <option value="at_least">At least</option>
                  <option value="at_most">At most</option>
                  <option value="between">Between</option>
                </select>
              </label>
              <label>
                Value
                <input
                  disabled={disabled}
                  maxLength={80}
                  value={param.value}
                  onChange={event => patch(index, { value: event.target.value })}
                  placeholder="e.g. 33kΩ"
                />
              </label>
              {param.operator === 'between' ? (
                <label>
                  Up to
                  <input
                    disabled={disabled}
                    maxLength={80}
                    value={param.value_max ?? ''}
                    onChange={event => patch(index, { value_max: event.target.value })}
                    placeholder="e.g. 47kΩ"
                  />
                </label>
              ) : (
                <label className="check-label spec-required">
                  <input
                    type="checkbox"
                    disabled={disabled}
                    checked={param.required !== false}
                    onChange={event => patch(index, { required: event.target.checked })}
                  />{' '}
                  Required
                </label>
              )}
              <button
                className="remove-requirement"
                type="button"
                disabled={disabled}
                aria-label={`Remove spec value ${param.name || index + 1}`}
                onClick={() => edit({ params: spec.params.filter((_, i) => i !== index) })}
              >
                Remove
              </button>
            </div>
          ))}
          <div className="spec-editor-actions">
            <button
              className="add-requirement"
              type="button"
              disabled={disabled || spec.params.length >= 12}
              onClick={() =>
                edit({
                  params: [...spec.params, { name: '', value: '', operator: 'equals', required: true, origin: 'user' }],
                })
              }
            >
              <span className="add-requirement-icon" aria-hidden="true">
                +
              </span>
              <span>Add a spec value</span>
            </button>
            <button type="button" className="remove-button" onClick={() => setEditing(false)}>
              Done editing
            </button>
          </div>
          <small>
            Write values the way sellers list them, e.g. 33kΩ, 22µF, 5mm. The server normalises units when you confirm.
          </small>
        </div>
      )}
    </div>
  )
}

export function validSpec(spec: BuyableSpec | null | undefined) {
  return (
    !spec ||
    spec.params.every(
      param => param.name.trim() && param.value.trim() && (param.operator !== 'between' || param.value_max?.trim()),
    )
  )
}

// The confirm `update` replaces the spec and saves it as the user's. A user value clears "Needs value"; must is derived by the server.
export function specPayload(spec: BuyableSpec): BuyableSpec {
  const { must: _must, ...rest } = spec
  const params = spec.params.map(param => ({
    ...param,
    name: param.name.trim(),
    value: param.value.trim(),
    value_max: param.operator === 'between' ? param.value_max?.trim() || null : null,
  }))
  const hasValue = params.some(param => param.origin === 'user' && param.operator === 'equals' && param.value)
  return {
    ...rest,
    origin: 'user',
    params,
    ...(spec.needs_value && hasValue ? { needs_value: false, needs_value_reason: null } : {}),
  }
}
