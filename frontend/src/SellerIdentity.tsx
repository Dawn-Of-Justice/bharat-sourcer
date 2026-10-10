import type { ReportOffer } from './api'

export function sellerName(offer: ReportOffer): string {
  return offer.seller_name?.trim() || offer.seller
}

export function SellerIdentity({ offer }: { offer: ReportOffer }) {
  const trust = offer.trust
  const displayName = sellerName(offer)
  const domain = offer.seller_domain?.trim() || offer.seller
  const kind =
    offer.seller_kind === 'marketplace'
      ? 'Marketplace seller'
      : offer.seller_kind === 'platform_hosted'
        ? 'Hosted shop'
        : null
  const checkedAt =
    trust?.checked_at && !Number.isNaN(Date.parse(trust.checked_at))
      ? new Date(trust.checked_at).toLocaleString('en-IN')
      : null

  return (
    <div className="seller-identity">
      <div className="trust-badges">
        <strong>{displayName}</strong>
        {trust ? (
          <>
            {trust.label === 'established' && <span className="trust-badge trust-established">Established seller</span>}
            {trust.label === 'verified_basics' && (
              <span className="trust-badge trust-verified_basics">Verified basics</span>
            )}
            {trust.label === 'unverified' && (
              <span className="trust-badge trust-unverified">Unverified seller — check before paying</span>
            )}
            {trust.new_seller && <span className="trust-badge trust-new">New seller</span>}
            {trust.signals?.price_anomaly && (
              <span className="trust-badge trust-cheap">Unusually cheap — check seller</span>
            )}
          </>
        ) : (
          <span className="trust-badge trust-none">Trust not checked</span>
        )}
      </div>
      {(displayName !== domain || kind) && (
        <small className="trust-hint">
          {kind ? `${kind} · ` : ''}
          {domain}
        </small>
      )}
      {trust?.label === 'unverified' && (
        <small className="trust-hint">Check the seller before paying; prefer cash on delivery.</small>
      )}
      {trust && (
        <details className="trust-why">
          <summary>Why this trust label?</summary>
          <ul>
            {(trust.reasons ?? []).map((reason, index) => (
              <li key={index}>{reason}</li>
            ))}
            <li>
              Computed from public signals; GSTIN checks validate the number's format, not the business with the GST
              portal.
            </li>
            {checkedAt && <li>Checked {checkedAt}</li>}
          </ul>
        </details>
      )}
    </div>
  )
}
