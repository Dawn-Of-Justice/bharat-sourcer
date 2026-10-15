// Landing-page link parsing. Every input field (YouTube, project links, GitHub, extra sources)
// accepts any supported link: the backend classifies each URL by what it is, not by the field
// it was typed in, so a GitHub link pasted under YouTube is read as a repository.

export type LinkKind = 'youtube' | 'article' | 'github' | 'hackster'

const bareHost = (url: URL) => url.hostname.toLowerCase().replace(/^www\./, '')

export function linkKind(url: URL): LinkKind | null {
  const host = bareHost(url)
  if (['youtube.com', 'm.youtube.com', 'youtu.be'].includes(host)) return 'youtube'
  if (host === 'github.com') return 'github'
  if (host === 'hackster.io') return 'hackster'
  // Public personal blogs are accepted too; the backend validates and safely fetches them.
  return host.includes('.') && !url.username && !url.password ? 'article' : null
}

// A pasted link as an absolute http(s) URL, or null. A missing scheme ("github.com/a/b",
// "youtu.be/x") is taken as https.
export function parseLink(raw: string): URL | null {
  const text = raw.trim()
  if (!text) return null
  const candidate = /^[a-z][a-z0-9+.-]*:\/\//i.test(text) ? text : `https://${text.replace(/^\/+/, '')}`
  try {
    const url = new URL(candidate)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url : null
  } catch {
    return null
  }
}

export const hacksterMessage =
  'Hackster blocks automated reading, so its projects cannot be read yet. Try the project’s GitHub repository or video instead.'

export type CheckedLinks = { url: string; sources: string[] } | { error: string }

// Validate the main link and the extra sources regardless of which field each was typed in.
export function checkLinks(main: string, extras: string[]): CheckedLinks {
  const parsed = parseLink(main)
  const mainKind = parsed && linkKind(parsed)
  if (!parsed || !mainKind) {
    return { error: 'Enter a YouTube video, GitHub repository or public project/blog page link.' }
  }
  if (mainKind === 'hackster') return { error: hacksterMessage }
  const sources: string[] = []
  for (const [index, extra] of extras.entries()) {
    if (!extra.trim()) continue
    const url = parseLink(extra)
    const kind = url && linkKind(url)
    if (!url || !kind) {
      return { error: `Extra source ${index + 1}: use a YouTube video, GitHub repository or public project/blog page.` }
    }
    if (kind === 'hackster') return { error: `Extra source ${index + 1}: ${hacksterMessage}` }
    sources.push(url.toString())
  }
  const all = [parsed.toString(), ...sources]
  if (all.filter(url => linkKind(new URL(url)) === 'youtube').length > 1) {
    return { error: 'Only one YouTube video can be read per project. Remove the extra video link.' }
  }
  return { url: all[0], sources: all.slice(1) }
}
