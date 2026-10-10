// Cartoon project illustrations, not construction or wiring diagrams.
export default function JourneyProjectArt({ kind }: { kind: 'article' | 'document' }) {
  return (
    <svg className="journey-project-art" viewBox="0 0 130 120" fill="none" aria-hidden="true">
      <rect width="130" height="120" fill={kind === 'article' ? '#dce9d3' : '#e2e9e5'} />
      {kind === 'article' ? (
        <>
          <ellipse cx="65" cy="107" rx="48" ry="5" fill="#b5c8a4" />
          <path d="M22 72H75L69 105H29Z" fill="#cf8b66" stroke="#925e48" strokeWidth="2" />
          <rect x="19" y="68" width="59" height="10" rx="3" fill="#e6aa80" stroke="#925e48" strokeWidth="2" />
          <path d="M48 69V26" stroke="#5b8051" strokeWidth="4" />
          <path d="M48 49C27 52 22 36 24 30C40 27 49 37 48 49Z" fill="#709d60" stroke="#517b4b" strokeWidth="2" />
          <path d="M48 35C48 17 65 14 71 18C73 29 64 40 48 35Z" fill="#91b573" stroke="#517b4b" strokeWidth="2" />
          <path d="M48 62C51 45 65 43 70 48C71 60 59 67 48 62Z" fill="#719e60" stroke="#517b4b" strokeWidth="2" />
          <rect x="90" y="76" width="27" height="27" rx="5" fill="#62969b" stroke="#3e7279" strokeWidth="2" />
          <circle cx="103" cy="89" r="6" fill="#d0e4d9" />
          <path d="M103 76V48Q103 38 92 38H81V49" stroke="#5b9ea9" strokeWidth="4" strokeLinecap="round" />
          <path className="journey-water-drop" d="M81 49Q70 63 81 64Q92 63 81 49Z" fill="#69acbb" />
          <path d="M36 74V85M39 74V85" stroke="#345e53" strokeWidth="2" />
        </>
      ) : (
        <>
          <ellipse cx="65" cy="109" rx="39" ry="5" fill="#bccdc5" />
          <path d="M59 72H71V100H59Z" fill="#6d9890" stroke="#355f58" strokeWidth="2" />
          <path d="M43 100H87L95 109H35Z" fill="#8ab1a3" stroke="#355f58" strokeWidth="2" />
          <circle cx="65" cy="47" r="35" fill="#f5f1d9" stroke="#355f58" strokeWidth="3" />
          <g className="journey-fan-blades" fill="#79a8a1" stroke="#436f68" strokeWidth="1.5">
            <path d="M65 47C43 39 42 18 55 18C68 18 73 31 65 47Z" />
            <path d="M65 47C84 33 103 41 96 53C89 64 76 63 65 47Z" />
            <path d="M65 47C68 70 51 82 45 71C38 59 47 48 65 47Z" />
          </g>
          <circle cx="65" cy="47" r="27" stroke="#fffaf0" strokeWidth="1.5" opacity=".7" />
          <circle cx="65" cy="47" r="7" fill="#e3bb6a" stroke="#355f58" strokeWidth="2" />
          <circle cx="76" cy="103" r="3" fill="#e3bb6a" />
        </>
      )}
    </svg>
  )
}
