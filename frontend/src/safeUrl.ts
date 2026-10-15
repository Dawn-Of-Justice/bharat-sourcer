// Links built from backend, seller or AI data must never become javascript:, data: or other
// script-capable URLs. Returns the URL only when it parses as absolute http(s); otherwise undefined,
// so React renders the anchor without an href.
export function safeHref(url?: string | null): string | undefined {
  if (!url) return undefined
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : undefined
  } catch {
    return undefined
  }
}
