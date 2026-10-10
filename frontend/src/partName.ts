import type { BomItem, BuyableSpec } from './api'

// Keep circuit references visible, while explaining what the user is buying.
export function partName(item: BomItem, spec: BuyableSpec | null | undefined = item.buyable_spec): string {
  const ref = /^(?:VR|IC|ZD|PZ|R|C|D|Q|T|U|L|J|SW)\d+(?:\s*[,/]\s*(?:VR|IC|ZD|PZ|R|C|D|Q|T|U|L|J|SW)\d+)*$/i
  if (!ref.test(item.raw_name.trim()) || !spec) return item.raw_name
  let category = spec.category.replaceAll('_', ' ')
  if (/^VR\d+$/i.test(item.raw_name)) category = 'potentiometer'
  const identity = spec.params
    .filter(
      p =>
        ['stated', 'user'].includes(p.origin ?? '') &&
        p.operator === 'equals' &&
        ['resistance', 'capacitance', 'ic_part_number', 'buzzer_type', 'diode_type'].includes(p.name),
    )
    .map(p => p.value)
  const name = [...identity, category === 'other' ? '' : category].filter(Boolean).join(' ')
  return name ? `${name} (${item.raw_name})` : item.raw_name
}
