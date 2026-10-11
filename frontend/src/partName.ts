import type { BomItem, BuyableSpec, ReportLine } from './api'

const reference = '(?:VR|IC|ZD|PZ|R|C|D|Q|T|U|L|J|SW)\\d+(?:\\s*[,/]\\s*(?:VR|IC|ZD|PZ|R|C|D|Q|T|U|L|J|SW)\\d+)*'
const referenceOnly = new RegExp(`^${reference}$`, 'i')

// A selected listing describes the actual purchase, including its value and rating.
// Keep the full seller title: blindly stripping suffixes can remove package/model data.
export function reportPartName(line: ReportLine): string {
  const raw = line.item.raw_name.trim()
  const refs = referenceOnly.test(raw) ? raw : raw.match(new RegExp(`\\((${reference})\\)$`, 'i'))?.[1]
  const selected = line.offers?.find(offer => offer.url === line.selected_offer_url)
  if (refs && !line.item.user_has_it && selected?.title.trim()) {
    return `${selected.title.trim()} (${refs})`
  }
  return partName(line.item, line.buyable_spec ?? line.item.buyable_spec)
}

// Keep circuit references visible, while explaining what the user is buying.
export function partName(item: BomItem, spec: BuyableSpec | null | undefined = item.buyable_spec): string {
  if (!referenceOnly.test(item.raw_name.trim()) || !spec) return item.raw_name
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
