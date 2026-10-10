import { useEffect, useRef, useState } from 'react'
import './youtube-journey.css'
import JourneyCircuit from './JourneyCircuit'
import { DocumentIcon, LinkIcon } from './LandingIcons'
import JourneyProjectArt from './JourneyProjectArt'

const projects = {
  youtube: {
    title: 'Automatic night light',
    description: 'A light that responds to the room.',
    quote: 'Parts: LDR, LED, transistor, resistors.',
    url: 'youtube.com/watch?v=dQw4w9WgXcQ',
    parts: ['Light sensor + LED', 'Transistor', 'Resistors'],
    before: 'Value to confirm',
    after: 'Check values for your 5V supply',
    question: 'I already have a 5V supply. Can I use it?',
    answer: 'Let’s check your LED and transistor specs, then choose resistor values for 5V.',
    seller: 'Resistor options',
  },
  article: {
    title: 'Automatic plant watering',
    description: 'Give your plants a helping hand.',
    quote: 'Parts: sensor, controller, pump, tubing.',
    url: 'github.com/maker/plant-watering',
    parts: ['Soil sensor + controller', 'Tubing', 'Water pump'],
    before: 'Flow rate to confirm',
    after: 'Choose flow for three small pots',
    question: 'Can I use this for three small pots?',
    answer: 'Let’s check the pump flow and tubing layout so each pot gets the water it needs.',
    seller: 'Water pump options',
  },
  document: {
    title: 'A quieter desk fan',
    description: 'A little breeze for your workspace.',
    quote: 'Parts: fan, stand, speed controller.',
    url: 'desk-fan-build-guide.pdf',
    parts: ['DC fan + guard', 'Desk stand', 'Speed controller'],
    before: 'Controller rating to confirm',
    after: 'Match control to the fan rating',
    question: 'Can I make the fan quieter?',
    answer: 'Let’s check the fan’s voltage and control method before choosing a speed controller.',
    seller: 'Speed controller options',
  },
}

// Illustrative content only. No model, sourcing or project requests.
export default function YoutubeJourney({ source = 'youtube' }: { source?: 'youtube' | 'article' | 'document' }) {
  const isDocument = source === 'document'
  const project = projects[source]
  const label = source === 'youtube' ? 'YouTube' : isDocument ? 'Document' : 'Project links'
  const sourceName = source === 'youtube' ? 'VIDEO' : isDocument ? 'DOCUMENT' : 'PROJECT'
  const [replay, setReplay] = useState(0)
  const [paused, setPaused] = useState(false)
  const [ended, setEnded] = useState(false)
  const [visible, setVisible] = useState(false)
  const [foreground, setForeground] = useState(() => !document.hidden)
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const host = useRef<HTMLElement>(null)
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const updatePreference = () => setReduced(preference.matches)
    const updateVisibility = () => setForeground(!document.hidden)
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting && entry.intersectionRatio >= 0.35),
      { threshold: [0, 0.35] },
    )
    if (host.current) observer.observe(host.current)
    preference.addEventListener('change', updatePreference)
    document.addEventListener('visibilitychange', updateVisibility)
    return () => {
      observer.disconnect()
      preference.removeEventListener('change', updatePreference)
      document.removeEventListener('visibilitychange', updateVisibility)
    }
  }, [])
  return (
    <section className="hero-visual youtube-journey" ref={host} aria-label={`Animated ${label} project journey`}>
      <div className="orbit orbit-one" aria-hidden="true" />
      <div className="orbit orbit-two" aria-hidden="true" />
      <div className="preview-card journey-card">
        <div className="preview-heading">
          <span className="preview-label">THE JOURNEY</span>
        </div>
        <p className="journey-accessible">
          {isDocument
            ? 'Document uploads are not available yet. This illustrates the planned workflow.'
            : `Bring a ${label} source.`}{' '}
          {project.title}: review its parts, discuss changes, compare seller options, and sign in to save the project.
          All content shown is an example.
        </p>
        <div
          className="journey-film"
          key={replay}
          aria-hidden="true"
          data-playing={!paused && visible && foreground && !reduced}
          onAnimationEnd={event => {
            if (event.animationName === 'journey-clock') setEnded(true)
          }}
        >
          <div className="journey-video-anchor">
            <div className="video-tile">
              <div className="video-art">
                {source === 'youtube' ? (
                  <>
                    <JourneyCircuit />
                    <div className="play-button">▶</div>
                  </>
                ) : (
                  <div className={`journey-source-paper ${isDocument ? 'journey-source-document' : ''}`}>
                    <div className="journey-paper-heading">
                      <span>{isDocument ? 'BUILD GUIDE.pdf' : 'MAKER GUIDE / README.md'}</span>
                      <span>{isDocument ? 'PDF' : <LinkIcon />}</span>
                    </div>
                    <div className="journey-paper-content">
                      <div className="journey-paper-text">
                        <strong>{project.title}</strong>
                        <span>{project.description}</span>
                        <div className="journey-source-quote">
                          {project.quote}
                          <i />
                        </div>
                        <div className="journey-paper-rule" />
                        <div className="journey-paper-rule short" />
                      </div>
                      <div className="journey-paper-circuit">
                        <JourneyProjectArt kind={source} />
                      </div>
                    </div>
                  </div>
                )}
                <div className="journey-scan" />
                <span className="journey-detected">Components found</span>
              </div>
              <div className="video-caption">
                <span className={`source-pill source-pill-${source} journey-source-pill`}>
                  {source === 'youtube' ? '▶' : isDocument ? <DocumentIcon /> : <LinkIcon />} {label}
                </span>
                <strong>{project.title}</strong>
              </div>
            </div>
          </div>
          <div className="journey-paste">
            <span>↗</span>
            <span className="journey-url">{project.url}</span>
            <b>{isDocument ? 'Preview' : 'Analyze'}</b>
          </div>
          <div className="journey-connector">
            <span />
          </div>
          <div className="journey-list">
            <div className="journey-list-title">
              <span>PARTS FROM YOUR {sourceName}</span>
              <small>Review before sourcing</small>
            </div>
            <div className="journey-row journey-row-one">
              <span className="step-icon step-icon-one">01</span>
              <div>
                <strong>{project.parts[0]}</strong>
                <small>
                  {source === 'youtube'
                    ? 'Check the source details'
                    : isDocument
                      ? 'From the parts section'
                      : 'Quoted from the guide or README'}
                </small>
              </div>
              <span className="journey-check">✓</span>
            </div>
            <div className="journey-row journey-row-two">
              <span className="step-icon step-icon-two">02</span>
              <div>
                <strong>{project.parts[1]}</strong>
                <small>Confirm the model</small>
              </div>
              <span className="journey-check">✓</span>
            </div>
            <div className="journey-row journey-row-three">
              <span className="step-icon step-icon-three">03</span>
              <div>
                <strong>{project.parts[2]}</strong>
                <small className="journey-spec-old">{project.before}</small>
                <small className="journey-spec-new">{project.after}</small>
              </div>
              <span className="journey-edit">↻</span>
              <span className="journey-highlight" />
            </div>
          </div>
          <div className="journey-conversation">
            <div className="journey-question">
              <small>You</small>
              <span>{project.question}</span>
            </div>
            <div className="journey-answer">
              <small>Project assistant</small>
              <span>{project.answer}</span>
            </div>
          </div>
          <div className="journey-seller-branch">
            <div className="journey-branch-line" />
            <small>{project.seller.toUpperCase()}</small>
            <div className="journey-seller-options">
              <span>
                <b>Seller option A ↗</b>
                <small>Check specs &amp; stock</small>
              </span>
              <span>
                <b>Seller option B ↗</b>
                <small>Check delivery</small>
              </span>
            </div>
            <p>Illustrative options. Confirm details on the seller page.</p>
          </div>
          <div className="journey-saved">
            <span>✓</span>
            <div>
              <strong>{project.title} · saved</strong>
              <small>Sign in to keep your parts list and conversation.</small>
            </div>
          </div>
        </div>
        <div className="journey-controls">
          <span>
            {isDocument
              ? 'Concept only. Uploads are not available yet.'
              : source === 'article'
                ? 'Articles, blogs and GitHub. One project flow.'
                : 'From a saved video to your own build.'}
          </span>
          {!reduced && (
            <button
              type="button"
              onClick={() => {
                if (ended) {
                  setReplay(value => value + 1)
                  setEnded(false)
                  setPaused(false)
                } else setPaused(value => !value)
              }}
            >
              {ended ? 'Replay ↻' : paused ? 'Play' : 'Pause'}
            </button>
          )}
        </div>
      </div>
    </section>
  )
}
