import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'

// Countries we source for. Only India is supported today; add an entry (with its flag) as sellers are added.
export const countries = [{ code: 'IN', name: 'India' }] as const
export type CountryCode = typeof countries[number]['code']

// Inline SVG flags: emoji flags render as letters on Windows.
const flags: Record<CountryCode, ReactNode> = {
  IN: <svg viewBox="0 0 30 20" aria-hidden="true">
    <rect width="30" height="20" fill="#fff" />
    <rect width="30" height="6.67" fill="#ff9933" />
    <rect y="13.33" width="30" height="6.67" fill="#138808" />
    <circle cx="15" cy="10" r="2.6" fill="none" stroke="#000080" strokeWidth=".6" />
    <circle cx="15" cy="10" r=".5" fill="#000080" />
    {Array.from({ length: 24 }, (_, i) => <line key={i} x1="15" y1="10" x2="15" y2="7.4" stroke="#000080" strokeWidth=".2" transform={`rotate(${i * 15} 15 10)`} />)}
  </svg>,
}

export function Flag({ code }: { code: CountryCode }) {
  return <span className="flag">{flags[code]}</span>
}

export function CountryPicker({ value, onChange, labelId }: { value: CountryCode; onChange: (code: CountryCode) => void; labelId: string }) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const current = countries.find(country => country.code === value) ?? countries[0]

  useEffect(() => {
    if (!open) return
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', close)
    list.current?.focus()
    return () => document.removeEventListener('pointerdown', close)
  }, [open])

  function show() {
    setActive(Math.max(0, countries.findIndex(country => country.code === value)))
    setOpen(true)
  }
  function choose(index: number) {
    onChange(countries[index].code)
    setOpen(false)
    button.current?.focus()
  }
  function onListKey(event: KeyboardEvent) {
    if (event.key === 'ArrowDown') { event.preventDefault(); setActive(i => Math.min(countries.length - 1, i + 1)) }
    else if (event.key === 'ArrowUp') { event.preventDefault(); setActive(i => Math.max(0, i - 1)) }
    else if (event.key === 'Home') { event.preventDefault(); setActive(0) }
    else if (event.key === 'End') { event.preventDefault(); setActive(countries.length - 1) }
    else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(active) }
    else if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setOpen(false); button.current?.focus() }
    else if (event.key === 'Tab') setOpen(false)
  }

  return <div className="country-picker" ref={root}>
    <button ref={button} type="button" className="country-button" aria-haspopup="listbox" aria-expanded={open} aria-labelledby={`${labelId} country-current`} onClick={() => open ? setOpen(false) : show()} onKeyDown={event => { if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); show() } }}>
      <Flag code={current.code} /><span id="country-current">{current.name}</span><span className="country-chevron" aria-hidden="true">▾</span>
    </button>
    {open && <ul ref={list} className="country-menu" role="listbox" tabIndex={-1} aria-labelledby={labelId} aria-activedescendant={`country-${countries[active].code}`} onKeyDown={onListKey}>
      {countries.map((country, index) => <li key={country.code} id={`country-${country.code}`} role="option" aria-selected={country.code === value} className={index === active ? 'is-active' : undefined} onPointerEnter={() => setActive(index)} onClick={() => choose(index)}>
        <Flag code={country.code} /><span>{country.name}</span>{country.code === value && <span className="country-check" aria-hidden="true">✓</span>}
      </li>)}
      <li className="country-soon" role="presentation">More countries coming soon</li>
    </ul>}
  </div>
}
