// Stylized illustration for the walkthrough, not a wiring reference.
export default function JourneyCircuit() {
  return (
    <svg className="journey-circuit" viewBox="0 0 420 170" fill="none" aria-hidden="true">
      <defs>
        <pattern id="journey-mat" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M20 0H0V20" stroke="#a8cbb5" strokeWidth=".6" />
        </pattern>
        <pattern id="journey-holes" width="11" height="11" patternUnits="userSpaceOnUse">
          <rect x="3" y="3" width="3" height="3" rx="1" fill="#9cae9c" />
        </pattern>
      </defs>
      <rect width="420" height="170" fill="#d5e6d6" />
      <rect width="420" height="170" fill="url(#journey-mat)" />
      <ellipse cx="219" cy="143" rx="162" ry="15" fill="#aac3ae" opacity=".45" />
      <g transform="translate(60 25) rotate(-5 125 60)">
        <rect x="0" y="6" width="245" height="117" rx="11" fill="#a9b9a2" />
        <rect width="245" height="117" rx="11" fill="#fff7df" stroke="#738f77" strokeWidth="2" />
        <path d="M15 13H230" stroke="#d77860" strokeWidth="2" />
        <path d="M15 103H230" stroke="#65a1aa" strokeWidth="2" />
        <rect x="13" y="20" width="220" height="75" fill="url(#journey-holes)" />
        <path d="M16 58H230" stroke="#c6cbb7" strokeWidth="4" />
        <path
          className="circuit-wire"
          d="M37 82V36Q37 21 55 21H128Q143 21 143 38V78"
          stroke="#db7757"
          strokeWidth="5"
          strokeLinecap="round"
        />
        <path d="M37 82V36Q37 21 55 21H128Q143 21 143 38V78" stroke="#ffca88" strokeWidth="1.5" strokeLinecap="round" />
        <path
          className="circuit-current"
          d="M37 82V36Q37 21 55 21H128Q143 21 143 38V78"
          stroke="#fff2b7"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <path d="M82 82V64M82 36V46" stroke="#708579" strokeWidth="3" />
        <rect x="75" y="43" width="14" height="24" rx="5" fill="#dfb879" stroke="#8c704b" strokeWidth="1.5" />
        <path d="M76 48H88M76 54H88M76 60H88" stroke="#825044" strokeWidth="3" />
        <path d="M114 85V71M125 85V71M136 85V71" stroke="#819184" strokeWidth="2" />
        <path d="M112 54Q125 47 138 54V73H112Z" fill="#33584d" stroke="#1d4039" strokeWidth="2" />
        <path d="M115 55H135" stroke="#729282" strokeWidth="2" />
        <path d="M187 79V48M199 79V48" stroke="#7f927d" strokeWidth="3" />
        <circle className="circuit-led-halo" cx="193" cy="36" r="29" fill="#ffd878" opacity="0" />
        <path
          className="circuit-led"
          d="M180 43V31a13 13 0 0 1 26 0V43Z"
          fill="#efbd58"
          stroke="#ac7b34"
          strokeWidth="2"
        />
        <rect x="177" y="43" width="32" height="6" rx="3" fill="#e4a74a" stroke="#ac7b34" strokeWidth="1.5" />
        <path d="M186 33V29Q186 24 190 24" stroke="#fff2bb" strokeWidth="3" strokeLinecap="round" />
        <g className="circuit-rays" stroke="#d99c36" strokeWidth="2" strokeLinecap="round">
          <path d="M193 9V3M170 19L165 14M216 19L221 14" />
        </g>
        <path d="M162 83H192" stroke="#56949e" strokeWidth="4" strokeLinecap="round" />
        <path d="M52 83V61M63 83V61" stroke="#7e8e78" strokeWidth="2" />
        <circle cx="57" cy="51" r="16" fill="#e9c799" stroke="#896f54" strokeWidth="2" />
        <path
          d="M49 43H61Q66 43 66 47Q66 50 61 50H53Q48 50 48 54Q48 58 53 58H65"
          stroke="#996248"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      </g>
      <g transform="translate(317 84) rotate(10)">
        <rect y="5" width="65" height="60" rx="6" fill="#729b80" />
        <rect width="65" height="60" rx="6" fill="#378176" stroke="#225c53" strokeWidth="2" />
        <path d="M10 17H21V28M53 17H43V28M12 48H25V37M53 47H40V37" stroke="#a3ca8c" strokeWidth="2" />
        <rect x="23" y="20" width="20" height="22" rx="2" fill="#274a42" stroke="#92b294" />
        <path d="M9 7H56M9 54H56" stroke="#e4c176" strokeWidth="4" strokeDasharray="3 5" />
        <circle cx="53" cy="32" r="3" fill="#eac16c" />
      </g>
      <path d="M307 116C325 115 315 57 347 60" stroke="#628eb0" strokeWidth="4" strokeLinecap="round" />
      <path d="M312 129C341 145 339 80 360 79" stroke="#d79556" strokeWidth="4" strokeLinecap="round" />
    </svg>
  )
}
