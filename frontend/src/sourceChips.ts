import type { SourceReport } from './api'

// Source names for the review page (ReviewDetails.tsx and the review step's chip row in App.tsx).
export const kindLabel: Record<SourceReport['kind'], string> = {
  video: 'YouTube video',
  instructables: 'Instructables project',
  hackster: 'Hackster project',
  github: 'GitHub repository',
  adafruit: 'Adafruit Learn guide',
  blog: 'Tutorial blog',
  youtube_description: 'Video description',
}
const bareHost = (url: URL) => url.hostname.toLowerCase().replace(/^www\./, '')
// Chip names for the review page's source row: the source kind ("YouTube video", "Video description"), or the host
// for blogs. Names that still repeat get the URL's last path segment so every chip reads differently.
export function sourceChipLabels(reports: SourceReport[]): string[] {
  const parse = (link: string) => {
    try {
      return new URL(link)
    } catch {
      return null
    }
  }
  const base = reports.map(report => {
    const url = parse(report.url)
    return report.kind === 'blog' && url ? bareHost(url) : kindLabel[report.kind]
  })
  return base.map((label, index) => {
    if (base.indexOf(label) === base.lastIndexOf(label)) return label
    const segment = parse(reports[index].url)?.pathname.split('/').filter(Boolean).pop()
    return segment ? `${label} · ${segment}` : label
  })
}
export function sourceChipCount(report: SourceReport): string {
  if (report.status !== 'read') return 'Skipped'
  const parts = `${report.item_count} ${report.item_count === 1 ? 'part' : 'parts'}`
  return report.code_item_count ? `${parts} (${report.code_item_count} from code)` : parts
}
