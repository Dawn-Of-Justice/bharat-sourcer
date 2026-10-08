import type { ReactNode } from 'react'

// Line icons for the landing page (24px grid, stroke follows the text colour).
function Icon({ children }: { children: ReactNode }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
}

// A page with a magnifier: the quote or code line each part was found in.
export const EvidenceIcon = () => <Icon><path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h3" /><path d="M13 3l5 5v2" /><path d="M13 3v5h5" /><circle cx="16" cy="16" r="3" /><path d="m18.2 18.2 2.8 2.8" /></Icon>

// A plug: will this part work with the rest of the build.
export const CompatibilityIcon = () => <Icon><path d="M9 2v5" /><path d="M15 2v5" /><path d="M6 7h12v3a6 6 0 0 1-12 0V7z" /><path d="M12 16v6" /></Icon>

// A shop front: seller pages.
export const StoreIcon = () => <Icon><path d="M4 4h16l1 5H3l1-5z" /><path d="M3 9a3 3 0 0 0 6 0a3 3 0 0 0 6 0a3 3 0 0 0 6 0" /><path d="M5 12v8h14v-8" /><path d="M10 20v-5h4v5" /></Icon>

// A link: bring in a video, article or repository.
export const LinkIcon = () => <Icon><path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.5 1.5" /><path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.5-1.5" /></Icon>

// A checked clipboard: review and confirm the parts list.
export const ChecklistIcon = () => <Icon><rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="m9 14 2 2 4-4" /></Icon>

// A shopping bag: buy from sellers.
export const BagIcon = () => <Icon><path d="M6 7h12l1 14H5L6 7z" /><path d="M9 10V6a3 3 0 0 1 6 0v4" /></Icon>

// A conversation bubble for questions about the build.
export const ChatIcon = () => <Icon><path d="M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 3v-3a2 2 0 0 1-1-2V6a2 2 0 0 1 2-2z" /><path d="M8 9h8" /><path d="M8 12h5" /></Icon>
