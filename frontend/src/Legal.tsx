import { useEffect, type MouseEvent, type ReactNode } from 'react'

const REPO = 'https://github.com/Dawn-Of-Justice/bharat-sourcer'
const LEGAL_UPDATED = '17 October 2026'

// Plain left-clicks stay in the single-page app; modified clicks open the page normally.
function appLink(go: (path: string) => void, path: string) {
  return {
    href: path,
    onClick: (event: MouseEvent<HTMLAnchorElement>) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      event.preventDefault()
      go(path)
    },
  }
}

function LegalPage({
  title,
  documentTitle,
  onNavigate,
  children,
}: {
  title: string
  documentTitle: string
  onNavigate: (path: string) => void
  children: ReactNode
}) {
  useEffect(() => {
    const previous = document.title
    document.title = documentTitle
    return () => {
      document.title = previous
    }
  }, [documentTitle])
  return (
    <main id="main" className="legal-page container">
      <article>
        <a className="legal-back" {...appLink(onNavigate, '/')}>
          ← Back to Bharat Sourcer
        </a>
        <h1>{title}</h1>
        <p className="legal-updated">Last updated: {LEGAL_UPDATED}</p>
        {children}
      </article>
    </main>
  )
}

function Contact() {
  return (
    <>
      <h2 id="contact">Contact</h2>
      <p>
        Questions and requests go to the project’s{' '}
        <a href={REPO + '/issues'} target="_blank" rel="noreferrer">
          GitHub issues
        </a>
        . Report a security or privacy problem privately through{' '}
        <a href={REPO + '/security/advisories/new'} target="_blank" rel="noreferrer">
          GitHub security advisories
        </a>
        . Please don’t post personal details in a public issue.
      </p>
    </>
  )
}

export function PrivacyPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <LegalPage title="Privacy" documentTitle="Privacy — Bharat Sourcer" onNavigate={onNavigate}>
      <p>
        Bharat Sourcer turns an electronics project link into a parts list and finds sellers. This page explains what we
        keep, why, and how to delete it.
      </p>
      <h2>What we collect</h2>
      <ul>
        <li>The project links you paste, and the parts lists, seller offers and build guides we make from them.</li>
        <li>The chat messages you send in a project, and the replies.</li>
        <li>
          If you sign in with Google: Firebase Authentication holds your Google email and a user id. Our project
          database stores the user id and your delivery country, not your email.
        </li>
        <li>If you use the app as a guest: a random session id in a cookie. It is not linked to your name.</li>
        <li>
          Usage counters per account, guest session and network, used for daily limits. Your network address is stored
          only as a keyed hash.
        </li>
        <li>Server logs, which can include your IP address and browser details.</li>
      </ul>
      <p>If you create a share link, anyone who has it can view that project’s report until you turn it off.</p>
      <h2>Why</h2>
      <p>
        To run the service, keep your projects for you, and prevent abuse. We don’t sell your data or use it for
        advertising.
      </p>
      <h2>Who processes it</h2>
      <ul>
        <li>Google Cloud and Firebase host the app, store projects, sign you in and keep logs.</li>
        <li>Gemini (Google) processes your project content and chat messages to make parts lists and answers.</li>
        <li>
          We fetch the project pages you link and public seller websites to find parts and prices. None of your data is
          sent to sellers.
        </li>
      </ul>
      <h2>How long we keep it</h2>
      <ul>
        <li>Guest projects are deleted 30 days after their last update.</li>
        <li>Account projects are deleted after 365 days without an update. Opening a project doesn’t count.</li>
        <li>Usage counters expire after about two days.</li>
        <li>Server logs are kept for 30 days, the Google Cloud Logging default.</li>
        <li>
          Some cached results, such as seller searches and read-aloud audio, are stored by content rather than by person
          and expire on their own.
        </li>
      </ul>
      <h2>Your controls</h2>
      <ul>
        <li>
          <strong>Delete my data</strong> in the Account panel removes all your projects, share links and settings. For
          a Google account it also removes your sign-in record.
        </li>
        <li>You can delete a single project from My projects.</li>
        <li>Signing out ends your session on this device.</li>
      </ul>
      <h2>Cookies</h2>
      <p>
        We use only essential cookies and browser storage: the guest session cookie, and the sign-in state Firebase
        keeps in your browser. There are no advertising or analytics trackers.
      </p>
      <Contact />
    </LegalPage>
  )
}

export function TermsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <LegalPage title="Terms" documentTitle="Terms — Bharat Sourcer" onNavigate={onNavigate}>
      <p>By using Bharat Sourcer you agree to these terms. They are short on purpose.</p>
      <h2>A free tool</h2>
      <p>Bharat Sourcer is a free tool, provided as-is. It may change, pause or stop at any time.</p>
      <h2>Check before you buy</h2>
      <p>
        Parts lists, prices and compatibility notes are generated with AI and can be wrong or out of date. Verify every
        part, price and listing with the seller before you buy.
      </p>
      <h2>Sellers</h2>
      <p>
        Prices and listings belong to the sellers. We don’t sell anything and aren’t part of any purchase you make. Your
        order is between you and the seller.
      </p>
      <h2>Acceptable use</h2>
      <p>
        Don’t abuse the service: no automated scraping, no attempts to get around usage limits, and nothing that
        disrupts it for others. We may limit or block access that does.
      </p>
      <h2>No warranty</h2>
      <p>The service comes without any warranty, express or implied, including fitness for a particular purpose.</p>
      <h2>Limitation of liability</h2>
      <p>
        To the extent the law allows, we aren’t liable for any loss or damage from using the service, including parts
        that don’t work, wrong prices or failed builds.
      </p>
      <h2>Changes</h2>
      <p>
        We may update these terms. The date above shows the latest version, and using the service after a change means
        you accept it.
      </p>
      <Contact />
    </LegalPage>
  )
}

export function SiteFooter({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <footer className="site-footer">
      <div className="container">
        <a {...appLink(onNavigate, '/privacy')}>Privacy</a>
        <span aria-hidden="true"> · </span>
        <a {...appLink(onNavigate, '/terms')}>Terms</a>
      </div>
    </footer>
  )
}
