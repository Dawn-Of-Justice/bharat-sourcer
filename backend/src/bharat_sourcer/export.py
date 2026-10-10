"""Redacted project views and the HTML/PDF export. Pure rendering; no network I/O."""

from datetime import datetime
from html import escape
from typing import Literal

from bharat_sourcer.schemas import (
    BomItem,
    Evidence,
    Job,
    Model,
    PartRequirement,
    ProjectContext,
    Report,
    ReportLine,
    Status,
    VerifiedOffer,
    now,
)
from bharat_sourcer.youtube_meta import apply_retention

SNAPSHOT_NOTICE = (
    "Prices, stock and compatibility are snapshots taken at each offer's checked_at time, "
    "copied from seller pages; they are not live quotes or verified seller facts. "
    "Tax and shipping are not included. Compatibility covers declared specifications only."
)
DEMO_NOTICE = "DEMO JOB: sample fixture data, not real extraction, sourcing or prices."


class SharedProject(Model):
    """Read-only, redacted project view for share links and exports.

    Excludes the job id, job token, owner identity, chat history, events, resistor
    advice and grounded-search attribution; nothing here grants access to the job.
    """

    shared: Literal[True] = True
    demo: bool
    status: Status
    source_url: str
    project: ProjectContext | None = None
    created_at: datetime
    updated_at: datetime
    items: list[BomItem]
    report: Report | None = None
    notice: str


def redact(job: Job) -> SharedProject:
    job = apply_retention(job.model_copy(deep=True))
    report = None
    if job.report:
        report = job.report.model_copy(deep=True)
        for line in report.lines:
            line.attribution = None
            line.code_patch = None  # Code patches are owner-only.
    return SharedProject(
        demo=job.demo,
        status=job.status,
        source_url=str(job.input.url),
        project=job.project.model_copy(deep=True) if job.project else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
        items=[item.model_copy(deep=True) for item in job.items],
        report=report,
        notice=(DEMO_NOTICE + " " if job.demo else "") + SNAPSHOT_NOTICE,
    )


def lines(view: SharedProject) -> list[ReportLine]:
    """Report lines when a report exists; draft BOM items otherwise."""
    if view.report and view.report.lines:
        return view.report.lines
    return [
        ReportLine(item=item, sourcing_status="already_owned" if item.user_has_it else "not_run")
        for item in view.items
    ]


def selected(line: ReportLine) -> VerifiedOffer | None:
    if line.selected_offer_url is None:
        return None
    return next((o for o in line.offers if o.url == line.selected_offer_url), None)


def requirement_text(requirement: PartRequirement) -> str:
    operator = {"equals": "=", "at_least": ">=", "at_most": "<="}[requirement.operator]
    unit = f" {requirement.unit}" if requirement.unit else ""
    label = " (inferred)" if requirement.origin == "inferred" else ""
    return f"{requirement.name} {operator} {requirement.value}{unit}{label}"


STYLE = """
:root{--ink:#14303a;--muted:#5b6f69;--line:#dfe6df;--soft:#f5f8f4;--brand:#19766d;
--warn:#8a5a1c;
--warn-bg:#fff6e6;--bad:#a33a2c;--bad-bg:#fdf0ed}
*{box-sizing:border-box}
body{margin:0;background:#eef2ee;color:var(--ink);
font:13px/1.5 system-ui,-apple-system,"Segoe UI","DejaVu Sans",
Roboto,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{max-width:900px;margin:24px auto;padding:36px 40px;background:#fff;
border:1px solid var(--line);
border-radius:14px}
a{color:var(--brand);text-decoration:none}a:hover{text-decoration:underline}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;padding-bottom:14px;
border-bottom:2px solid var(--ink);margin-bottom:22px}
.brand{display:flex;align-items:center;gap:9px;font-weight:800;font-size:15px;
letter-spacing:-.2px}
.mark{display:grid;place-items:center;width:26px;height:26px;border-radius:7px;
background:var(--ink);
color:#fff;font-size:15px}
.accent{color:var(--brand)}
.doc-kind{color:var(--muted);font-size:12px;text-align:right}
h1{margin:0 0 6px;font-size:26px;line-height:1.2;letter-spacing:-.4px}
.lead{margin:0 0 10px;color:#33504a;font-size:14px}
.meta{margin:0;color:var(--muted);font-size:12px}
h2{margin:28px 0 10px;font-size:16px;letter-spacing:-.1px}
h3{margin:0;font-size:14px}
.notice{margin:14px 0 0;padding:9px 12px;border-radius:8px;border:1px solid #e7d3a8;
background:var(--warn-bg);color:#5c4520;font-size:12px}
.notice.demo{border-color:#e7b3ab;background:var(--bad-bg);color:var(--bad);font-weight:700}
.summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:20px}
.stat{padding:12px 14px;border:1px solid var(--line);border-radius:10px;background:var(--soft)}
.stat b{display:block;font-size:18px;line-height:1.25}
.stat>span{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em;
font-weight:700}
.stat.total{background:var(--ink);border-color:var(--ink);color:#fff}
.stat.total>span{color:#cfe3dc}
.tag{display:inline-block;margin-left:4px;padding:0 6px;border-radius:999px;background:#e8eee8;
color:var(--muted);font-size:10px;font-weight:700;letter-spacing:0;text-transform:none;
vertical-align:1px}
.stat.total .tag{background:#2c4d55;color:#d9ebe4}
.seller{margin:0 0 14px;border:1px solid var(--line);border-radius:12px;break-inside:avoid}
.seller-head{display:flex;justify-content:space-between;align-items:baseline;gap:10px;
padding:11px 14px;
background:var(--soft);border-bottom:1px solid var(--line);border-radius:12px 12px 0 0}
.seller-head span{color:var(--muted);font-size:12px}
table{width:100%;border-collapse:collapse}
th{padding:7px 14px;color:var(--muted);font-size:10px;font-weight:700;letter-spacing:.06em;
text-transform:uppercase;text-align:left;border-bottom:1px solid var(--line)}
td{padding:9px 14px;border-bottom:1px solid #edf1ec;vertical-align:top}
tr:last-child td{border-bottom:0}
.num{text-align:right;white-space:nowrap}
.part{font-weight:700}
.sub{display:block;color:var(--muted);font-size:11px}
.pill{display:inline-block;margin-top:3px;padding:0 6px;border-radius:4px;background:#e6f2ea;
color:#0d6b5f;font-size:10px;font-weight:700}
.pill.pending{background:var(--warn-bg);color:var(--warn)}
.totals{margin:0;padding:10px 14px;border-top:1px solid var(--line);display:grid;
grid-template-columns:1fr auto;gap:3px 16px;font-size:12px}
.totals dt{color:var(--muted)}.totals dd{margin:0;text-align:right}
.totals .grand{font-weight:800;color:var(--ink)}
.note{padding:0 14px 11px;color:var(--muted);font-size:11px}
.todo{margin:0;padding:0;list-style:none;border:1px solid #efd3a3;border-radius:12px;
break-inside:avoid}
.todo>li{padding:10px 14px;border-bottom:1px solid #f4e6c8}.todo>li:last-child{border-bottom:0}
.todo ul{margin:4px 0 0;padding-left:18px;color:var(--muted);font-size:12px}
.plain{border:1px solid var(--line);border-radius:12px}
.plain ul{margin:0;padding-left:16px}
.evidence{margin:0;padding:0;list-style:none}
.evidence>li{padding:8px 0;border-bottom:1px solid #edf1ec;break-inside:avoid}
.evidence ul{margin:3px 0 0;padding-left:18px;color:#33504a;font-size:12px}
.time{font-variant-numeric:tabular-nums;color:var(--brand);font-weight:700}
.facts{margin:6px 0 0;padding-left:18px;color:#33504a}
footer{margin-top:30px;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);
font-size:11px}
footer p{margin:0 0 6px}
.noprint{margin:16px auto 0;max-width:900px;padding:0 4px;color:var(--muted);font-size:12px;
text-align:right}
@media (max-width:700px){.page{margin:0;padding:22px 16px;border:0;border-radius:0}
.summary{grid-template-columns:repeat(2,minmax(0,1fr))}th,td{padding:7px 8px}}
@media print{body{background:#fff}.page{max-width:none;margin:0;padding:0;
border:0}.noprint{display:none}
h2{break-after:avoid}thead{display:table-header-group}tr{break-inside:avoid}a{color:var(--ink)}}
@page{size:A4;margin:14mm 12mm}
"""

JOB_STATUS = {
    "queued": "Reading the source",
    "extracting": "Reading the source",
    "awaiting_confirmation": "Parts list awaiting review",
    "resolving": "Finding sellers",
    "sourcing": "Finding sellers",
    "paused": "Paused",
    "done": "Order plan ready",
    "failed": "Needs attention",
}
LINE_STATUS = {
    "offers_found": "Offers found",
    "no_verified_offers": "No verified offer yet",
    "already_owned": "You have it",
    "not_run": "Not searched yet",
    "failed": "Search failed",
}
COST_STATUS = {"known": "", "estimated": "est.", "unknown": "unknown"}


def link(url, text=None) -> str:
    # Values are validated http(s) URLs; still escape for the attribute context.
    value = escape(str(url), quote=True)
    return f'<a href="{value}" rel="noopener noreferrer nofollow">{escape(text or str(url))}</a>'


def host(url) -> str:
    return str(url).split("//", 1)[-1].split("/", 1)[0].removeprefix("www.")


def inr(value) -> str:
    """Indian digit grouping: 123456.5 -> ₹1,23,456.50."""
    if value is None:
        return ""
    whole, _, paise = f"{float(value):.2f}".partition(".")
    sign = "-" if whole.startswith("-") else ""
    whole = whole.lstrip("-")
    head, tail = whole[:-3], whole[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join([*groups, tail])}.{paise}"


def amount(cost) -> str:
    """A CostAmount with its status; an unknown total shows the known part as 'at least'."""
    if cost is None:
        return ""
    tag = COST_STATUS.get(cost.status, cost.status)
    if cost.amount_inr is not None:
        value = inr(cost.amount_inr)
    elif cost.partial_inr is not None and float(cost.partial_inr) > 0:
        value = f"at least {inr(cost.partial_inr)}"
    else:
        value, tag = "Unknown", ""
    return escape(value) + (f" <span class='tag'>{escape(tag)}</span>" if tag else "")


def day(value) -> str:
    return f"{value.day} {value.strftime('%b %Y')}"


def source_label(url: str) -> str:
    name = host(url)
    if name in {"youtube.com", "m.youtube.com", "youtu.be"}:
        return "YouTube video"
    if name == "github.com":
        return "GitHub repository"
    return name


def evidence_html(ev: Evidence) -> str:
    e = escape
    if ev.source == "video":
        return f"<span class='time'>{e(ev.timestamp or '')}</span> {e(ev.observation)}"
    if ev.source == "code":
        where = f"{ev.file}:{ev.line}" if ev.file else "code"
        place = link(ev.url, where) if ev.url else e(where)
        return f"{place} &ldquo;{e(ev.quote or '')}&rdquo; &mdash; {e(ev.observation)}"
    origin = link(ev.url, host(ev.url)) if ev.url else ""
    return f"&ldquo;{e(ev.quote or '')}&rdquo; {origin} &mdash; {e(ev.observation)}"


def qty_text(item: BomItem) -> str:
    unit = f" {item.qty_unit}" if item.qty_unit and item.qty_unit != "pcs" else ""
    return f"{item.qty or ''}{unit}"


def seller_section(group, report: Report) -> str:
    e = escape
    by_id = {line.item.line_id: line for line in report.lines}
    rows = []
    for entry in group.lines:
        line = by_id.get(entry.line_id)
        buy = (
            f"{entry.packs} &times; pack of {entry.pack_qty}"
            if entry.pack_qty
            else str(entry.units)
        )
        spare = entry.units - entry.qty
        if spare > 0:
            buy += f"<span class='sub'>{spare} spare</span>"
        if not entry.selected:
            reason = entry.blocked_reason or "Not selected yet"
            if not reason.lower().startswith("not selected"):
                reason = f"Not selected: {reason}"
            pill = f"<span class='pill pending'>{e(reason)}</span>"
        elif entry.selection_source == "user":
            copied = line is not None and line.copied_choice
            pill = f"<span class='pill'>{'Copied choice' if copied else 'Your choice'}</span>"
        else:
            pill = "<span class='pill'>Recommended</span>"
        rows.append(
            f"<tr><td><span class='part'>{e(entry.name)}</span>"
            f"<span class='sub'>{e(entry.title or 'Listing')} &middot; "
            f"{link(entry.offer_url, 'open listing')}</span>{pill}</td>"
            f"<td class='num'>{entry.qty}</td><td class='num'>{buy}</td>"
            f"<td class='num'>{inr(entry.unit_price_inr)}</td>"
            f"<td class='num'><strong>{inr(entry.line_price_inr)}</strong></td></tr>"
        )
    notes = []
    if group.free_shipping_gap_inr:
        notes.append(f"Add {inr(group.free_shipping_gap_inr)} more for free shipping.")
    if group.policy:
        policy = group.policy
        checked = f" (checked {day(policy.checked_on)})" if policy.checked_on else ""
        source = (
            link(policy.source_url, "Shipping policy") if policy.source_url else "Shipping policy"
        )
        flag = " Not verified." if policy.unverified else ""
        notes.append(f"{source}{checked}.{flag}")
    count = len(group.lines)
    return (
        f"<section class='seller'><div class='seller-head'><h3>{e(group.seller)}</h3>"
        f"<span>{count} part{'s' * (count != 1)}</span></div>"
        "<table><thead><tr><th>Part</th><th class='num'>Need</th><th class='num'>Buy</th>"
        "<th class='num'>Unit</th><th class='num'>Price</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table><dl class='totals'>"
        f"<dt>Parts</dt><dd>{inr(group.subtotal_inr)}</dd>"
        f"<dt>GST</dt><dd>{amount(group.gst)}</dd>"
        f"<dt>Shipping</dt><dd>{amount(group.shipping)}</dd>"
        f"<dt class='grand'>Seller total</dt><dd class='grand'>{amount(group.total)}</dd></dl>"
        + (f"<div class='note'>{' '.join(notes)}</div>" if notes else "")
        + "</section>"
    )


def selected_table(report: Report) -> str:
    """Older or demo reports without an order plan: the selected offer per line."""
    e = escape
    rows = []
    for line in report.lines:
        offer = selected(line)
        listing = (
            f"{e(offer.seller)}<span class='sub'>{e(offer.title)} &middot; "
            f"{link(offer.url, 'open listing')}</span>"
            if offer
            else "<span class='sub'>No offer selected</span>"
        )
        rows.append(
            f"<tr><td><span class='part'>{e(line.item.raw_name)}</span></td>"
            f"<td class='num'>{e(qty_text(line.item))}</td><td>{listing}</td>"
            f"<td class='num'>{inr(line.price_inr)}</td>"
            f"<td class='num'><strong>{inr(line.subtotal_inr)}</strong></td></tr>"
        )
    return (
        "<section class='seller'><table><thead><tr><th>Part</th><th class='num'>Qty</th>"
        "<th>Selected offer</th><th class='num'>Unit</th><th class='num'>Price</th></tr>"
        "</thead><tbody>" + "".join(rows) + "</tbody></table></section>"
    )


def to_html(view: SharedProject) -> str:
    e = escape
    title = (view.project.title if view.project else None) or "Untitled project"
    report = view.report
    plan = report.order_plan if report else None
    part_lines = lines(view)
    owned = [line for line in part_lines if line.item.user_has_it]
    exported = now()
    count = len(part_lines)
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<meta name='referrer' content='no-referrer'>",
        f"<title>{e(title)} - Bharat Sourcer</title><style>{STYLE}</style></head><body>",
        "<p class='noprint'>To save a PDF, use your browser's Print command (Ctrl+P) and "
        "choose &ldquo;Save as PDF&rdquo;.</p><main class='page'>",
        "<div class='top'><div class='brand'><span class='mark'>B</span>"
        "<span>Bharat<span class='accent'>Sourcer</span></span></div>"
        f"<div class='doc-kind'>{'Order plan' if plan else 'Parts list'}<br>"
        f"Exported {e(day(exported))}</div></div>",
        f"<h1>{e(title)}</h1>",
    ]
    if view.project and view.project.description:
        parts.append(f"<p class='lead'>{e(view.project.description)}</p>")
    parts.append(
        f"<p class='meta'>Source: {link(view.source_url, source_label(view.source_url))}"
        f" &middot; {count} part{'s' * (count != 1)}"
        f" &middot; {e(JOB_STATUS.get(view.status, view.status))}</p>"
    )
    if view.demo:
        parts.append(f"<div class='notice demo'>{e(DEMO_NOTICE)}</div>")

    if plan:
        costing = plan.costing
        parts.append(
            "<div class='summary'>"
            "<div class='stat total'><span>Estimated total</span>"
            f"<b>{amount(costing.total)}</b></div>"
            f"<div class='stat'><span>Parts</span><b>{amount(costing.parts)}</b></div>"
            f"<div class='stat'><span>Sellers</span><b>{plan.seller_count}</b></div>"
            f"<div class='stat'><span>Still to source</span><b>{len(plan.unsourced)}</b></div>"
            "</div><h2>Order by seller</h2>"
        )
        parts.extend(seller_section(group, report) for group in plan.sellers)
        if not plan.sellers:
            parts.append("<p class='meta'>No offers could be selected yet.</p>")
        if plan.unsourced:
            parts.append("<h2>Still to source</h2><ul class='todo'>")
            for entry in plan.unsourced:
                steps = "".join(f"<li>{e(step)}</li>" for step in entry.next_steps)
                parts.append(
                    f"<li><span class='part'>{e(entry.name)}</span>"
                    f"<span class='sub'>{e(entry.message)}</span>"
                    + (f"<ul>{steps}</ul>" if steps else "")
                    + "</li>"
                )
            parts.append("</ul>")
    elif report:
        parts.append(
            "<h2>Selected offers</h2>"
            + selected_table(report)
            + "<p class='meta'>Selected parts subtotal: <strong>"
            f"{inr(report.selected_parts_subtotal_inr)}</strong> (excludes tax and shipping)</p>"
        )
    else:
        parts.append(
            "<div class='notice'>Sellers have not been searched yet; this is the parts list "
            "only.</div>"
        )

    if owned:
        names = ", ".join(e(line.item.raw_name) for line in owned)
        parts.append(f"<h2>Already have</h2><p class='meta'>{names}</p>")

    parts.append(
        "<h2>Full parts list</h2><section class='plain'><table><thead><tr><th>#</th>"
        "<th>Part</th><th class='num'>Qty</th><th>Requirements</th><th>Status</th></tr>"
        "</thead><tbody>"
    )
    for line in part_lines:
        item = line.item
        requirements = "".join(f"<li>{e(requirement_text(r))}</li>" for r in item.requirements)
        listed = f"<ul>{requirements}</ul>" if requirements else "<span class='sub'>None</span>"
        status = LINE_STATUS.get(line.sourcing_status, line.sourcing_status)
        parts.append(
            f"<tr><td>{e(item.line_id)}</td><td><span class='part'>{e(item.raw_name)}</span></td>"
            f"<td class='num'>{e(qty_text(item))}</td><td>{listed}</td><td>{e(status)}</td></tr>"
        )
    parts.append("</tbody></table></section>")

    if any(line.item.evidence for line in part_lines):
        parts.append("<h2>Where each part came from</h2><ul class='evidence'>")
        for line in part_lines:
            if line.item.evidence:
                found = "".join(f"<li>{evidence_html(ev)}</li>" for ev in line.item.evidence)
                parts.append(
                    f"<li><span class='part'>{e(line.item.raw_name)}</span><ul>{found}</ul></li>"
                )
        parts.append("</ul>")

    if view.project:
        p = view.project
        facts = [("Power", p.power), ("Controller", p.controller)]
        facts += [("Interfaces", ", ".join(p.interfaces) or None)]
        notes = [f"<li>{e(k)}: {e(v)}</li>" for k, v in facts if v]
        notes += [f"<li>Assumption: {e(a)}</li>" for a in p.assumptions]
        if p.summary or notes:
            parts.append("<h2>Project notes <span class='tag'>AI-inferred</span></h2>")
            if p.summary:
                parts.append(f"<p class='meta'>{e(p.summary)}</p>")
            if notes:
                parts.append("<ul class='facts'>" + "".join(notes) + "</ul>")

    footer = [
        "Prices, stock and compatibility are snapshots copied from seller pages when each "
        "offer was checked; they are not live quotes or verified seller facts. Compatibility "
        "covers declared specifications only."
    ]
    if plan:
        footer += [plan.disclaimer, plan.costing.disclaimer]
    footer.append(f"Generated by Bharat Sourcer on {day(exported)}. This is not an invoice.")
    parts.append("<footer>" + "".join(f"<p>{e(text)}</p>" for text in footer) + "</footer>")
    parts.append("</main></body></html>")
    return "".join(parts)


class PdfUnavailable(Exception):
    """WeasyPrint or its system libraries (Pango) are not installed here."""


def refuse_fetch(url: str, *args, **kwargs):
    # The export references no external resources; never let rendering fetch anything.
    raise ValueError(f"External resources are not loaded in exports: {url[:80]}")


def to_pdf(view: SharedProject) -> bytes:
    """The order plan as an A4 PDF, rendered from the same HTML as the printable page."""
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise PdfUnavailable(str(exc)) from exc
    return HTML(string=to_html(view), url_fetcher=refuse_fetch).write_pdf()
