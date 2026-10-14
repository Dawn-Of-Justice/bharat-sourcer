// A small, safe markdown subset for assistant chat replies: bold, italics, inline code,
// bulleted and numbered lists, headings (shown bold) and line breaks. It returns plain
// data that React renders as text nodes, so model output never reaches the DOM as HTML.

export type Inline =
  | { kind: 'text'; text: string }
  | { kind: 'strong'; children: Inline[] }
  | { kind: 'em'; children: Inline[] }
  | { kind: 'code'; text: string }

export type Block =
  | { kind: 'paragraph'; lines: Inline[][] }
  | { kind: 'heading'; children: Inline[] }
  | { kind: 'list'; ordered: boolean; start: number; items: Inline[][][] }

const INLINE =
  /`([^`\n]+)`|\*\*(?=\S)([^\n]*?\S)\*\*|__(?=\S)([^\n]*?\S)__|(?<![\w*])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?![\w*])|(?<![\w_])_(?=[^\s_])([^_\n]*?[^\s_])_(?![\w_])/g

export function parseInline(text: string): Inline[] {
  const out: Inline[] = []
  let last = 0
  for (const match of text.matchAll(INLINE)) {
    const index = match.index ?? 0
    if (index > last) out.push({ kind: 'text', text: text.slice(last, index) })
    const [, code, bold, boldUnderscore, italic, italicUnderscore] = match
    if (code !== undefined) out.push({ kind: 'code', text: code })
    else if (bold !== undefined || boldUnderscore !== undefined)
      out.push({ kind: 'strong', children: parseInline(bold ?? boldUnderscore) })
    else out.push({ kind: 'em', children: parseInline(italic ?? italicUnderscore) })
    last = index + match[0].length
  }
  if (last < text.length) out.push({ kind: 'text', text: text.slice(last) })
  return out
}

const BULLET = /^\s*[-*+•]\s+(.*)$/
const NUMBERED = /^\s*(\d{1,4})[.)]\s+(.*)$/
const HEADING = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/

export function parseChatMarkdown(text: string): Block[] {
  const blocks: Block[] = []
  let paragraph: string[] = []
  let list: { ordered: boolean; start: number; items: string[][] } | null = null

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ kind: 'paragraph', lines: paragraph.map(parseInline) })
    paragraph = []
  }
  const flushList = () => {
    if (list)
      blocks.push({
        kind: 'list',
        ordered: list.ordered,
        start: list.start,
        items: list.items.map(item => item.map(parseInline)),
      })
    list = null
  }

  for (const line of text.replace(/\r\n?/g, '\n').split('\n')) {
    const bullet = BULLET.exec(line)
    const numbered = bullet ? null : NUMBERED.exec(line)
    const heading = HEADING.exec(line)
    if (!line.trim()) {
      flushParagraph()
      flushList()
    } else if (bullet || numbered) {
      flushParagraph()
      const ordered = Boolean(numbered)
      if (list && list.ordered !== ordered) flushList()
      if (!list) list = { ordered, start: numbered ? Number(numbered[1]) : 1, items: [] }
      list.items.push([(bullet ? bullet[1] : (numbered?.[2] ?? '')).trim()])
    } else if (heading) {
      flushParagraph()
      flushList()
      blocks.push({ kind: 'heading', children: parseInline(heading[1]) })
    } else if (list && /^\s/.test(line)) {
      // An indented line continues the current list item.
      list.items[list.items.length - 1].push(line.trim())
    } else {
      flushList()
      paragraph.push(line)
    }
  }
  flushParagraph()
  flushList()
  return blocks
}
