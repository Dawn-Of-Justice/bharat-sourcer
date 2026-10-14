import type { FabricationPlan, FabricationService } from './api'
import { kindLabel } from './fabrication'
import { secureLink } from './ReportBits'

// Made-to-order lines (a 3D-printed part or a custom PCB): the AI decided the part is made from design files, so
// sourcing links fabrication services instead of sellers (docs/contracts/README.md v0.42.0).

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function ServiceLink({ service }: { service: FabricationService }) {
  const url = secureLink(service.url)
  return url ? (
    <a href={url} target="_blank" rel="noopener noreferrer nofollow">
      {service.name} ↗
    </a>
  ) : (
    <>{service.name}</>
  )
}

// The first service as a short link, for one-line notes (build checklist, parts list rows).
export function FirstService({ plan }: { plan: FabricationPlan }) {
  const first = plan.services?.[0]
  return first ? <ServiceLink service={first} /> : null
}

// The full block for the part panel: services, what to upload and the project's own design files.
export function FabricationCard({ plan }: { plan: FabricationPlan }) {
  const services = plan.services ?? []
  const designs = (plan.design_links ?? []).filter(url => secureLink(url))
  const fallback = plan.method === 'curated_fallback'
  return (
    <div className="pp-part-callout pp-made">
      <strong>Made to order</strong>
      <p>
        This part is made from the project's design files, not bought ready-made. Order it from a {kindLabel(plan)}.
      </p>
      <p>Upload: {plan.upload}.</p>
      {services.length > 0 && (
        <ul className="pp-made-services">
          {services.map(service => (
            <li key={service.url}>
              <ServiceLink service={service} />
              {service.ships_to_india === 'yes' && <small> · says it delivers in India</small>}
              {service.note && <small className="pp-made-note">{service.note}</small>}
            </li>
          ))}
        </ul>
      )}
      {designs.length > 0 ? (
        <p>
          Design files from the project:{' '}
          {designs.map((url, index) => (
            <span key={url}>
              {index > 0 && ', '}
              <a href={url} target="_blank" rel="noopener noreferrer nofollow">
                {hostOf(url)} ↗
              </a>
            </span>
          ))}
        </p>
      ) : (
        <p>The project's sources did not link the design files; look for them on the project page or repository.</p>
      )}
      <small className="pp-made-fine">
        {fallback
          ? 'Discovery was unavailable, so these are well-known services that were not checked live. '
          : 'Found by web search and checked on the service pages; AI-assessed. '}
        Price, delivery and shipping to India are set by the service; check before ordering.
      </small>
    </div>
  )
}
