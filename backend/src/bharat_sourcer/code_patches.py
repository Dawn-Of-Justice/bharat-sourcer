"""Owner-only code patches for substituted parts (docs/plans/code-adapt, tiers 1–2).

Flow: find the substitute edge from the chosen offer's catalogue ids, read the project's
code files that code evidence cited (raw.githubusercontent.com through the guarded
fetcher), apply the curated recipe, or, only when `BS_CODE_ADAPT_AI` is enabled and no
recipe exists, ask for a validated AI draft. The result is stored on the report line;
the download re-reads every file and refuses if any changed since the patch was made.
Patches are never compiled or run here.
"""

import hashlib
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from urllib.parse import urlsplit

from bharat_sourcer import code_adapt
from bharat_sourcer.catalog import load_catalog
from bharat_sourcer.jobs import JobError
from bharat_sourcer.schemas import CodePatch, CodePatchFile, CodePatchRequest, Job, ReportLine
from bharat_sourcer.sourcing.fetch import FetchError
from bharat_sourcer.usage import JobLedger, attribute, paid_allowed

RAW_HOST = "raw.githubusercontent.com"
CODE_FILE_BYTES = 200_000
MAX_FILES = 8
AI_MAX_FILES = 3
AI_MAX_BYTES = 60_000
BLOB = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/blob/([\w.-]+)/([^#?]+)")
LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")


def source_files(job: Job) -> dict[str, str]:
    """path -> raw URL for every code file that code evidence cited (bounded)."""
    found: dict[str, str] = {}
    lines = job.report.lines if job.report else []
    items = [line.item for line in lines] + list(job.items)
    for item in items:
        for evidence in item.evidence:
            if evidence.source != "code" or not evidence.url:
                continue
            match = BLOB.match(str(evidence.url))
            if not match:
                continue
            owner, repo, ref, path = match.groups()
            found.setdefault(path, f"https://{RAW_HOST}/{owner}/{repo}/{ref}/{path}")
    return dict(list(found.items())[:MAX_FILES])


def repo_root(raw_url: str) -> str:
    owner, repo, ref = urlsplit(raw_url).path.strip("/").split("/")[:3]
    return f"https://{RAW_HOST}/{owner}/{repo}/{ref}/"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def markers(entry) -> set[str]:
    """Identifiers that show code uses the original part (for tier-2 change locality)."""
    found = {lib.replace(" ", "_") for lib in entry.libraries}
    if entry.chip:
        found |= {entry.chip.upper(), entry.chip}
    return {m for m in found if m}


def includes(entry) -> set[str]:
    return {lib.replace(" ", "_") + ".h" for lib in entry.libraries} | {
        lib.replace(" ", "_") for lib in entry.libraries
    }


class CodePatchService:
    def __init__(self, settings, jobs, fetcher, generate=None):
        self.settings, self.jobs, self.fetcher = settings, jobs, fetcher
        self.generate = generate

    # -- reading ---------------------------------------------------------------
    def read(self, urls: dict[str, str]) -> dict[str, tuple[str, str]]:
        """path -> (text, raw url) for files that could be read as UTF-8 text."""
        texts = {}
        for path, url in urls.items():
            try:
                page = self.fetcher.get(url, max_bytes=CODE_FILE_BYTES)
            except FetchError:
                continue
            if page.status != 200 or (urlsplit(page.url).hostname or "").lower() != RAW_HOST:
                continue
            if b"\0" in page.body[:4096]:
                continue
            texts[path] = (page.body.decode("utf-8", errors="replace"), url)
        return texts

    def line(self, job: Job, line_id: str) -> ReportLine:
        if job.report is None:
            raise JobError(409, "INVALID_STATE", "Code patches need a sourcing report")
        line = next((ln for ln in job.report.lines if ln.item.line_id == line_id), None)
        if line is None:
            raise JobError(404, "LINE_NOT_FOUND", "Part not found")
        return line

    # -- creating --------------------------------------------------------------
    def create(self, job_id: str, line_id: str, token, request: CodePatchRequest) -> CodePatch:
        job = self.jobs.get(job_id, token)
        line = self.line(job, line_id)
        offer_url = str(request.offer_url or line.selected_offer_url or "") or None
        offer = next((o for o in line.offers if str(o.url) == offer_url), None)
        if offer_url is None or offer is None:
            raise JobError(422, "OFFER_REQUIRED", "Choose a saved offer for this part first")
        self.ledger = None
        start = job.cost_estimate
        patch = self.build(job, offer, line_id)
        patch.offer_url = offer.url
        ledger = self.ledger

        def save(record):
            saved_job = self.jobs._authorized(record, token)
            saved = self.line(saved_job, line_id)
            if not any(str(o.url) == offer_url for o in saved.offers):
                raise JobError(409, "PROPOSAL_STALE", "The offer changed; request a new patch")
            saved.code_patch = patch
            # Skip if a sourcing run wrote a newer estimate meanwhile; it owns the ledger.
            if ledger is not None and saved_job.cost_estimate == start:
                saved_job.cost_estimate = ledger.snapshot()
            saved_job.updated_at = datetime.now(UTC)

        if self.jobs.store.mutate(job_id, save) is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return patch

    def build(self, job: Job, offer, line_id: str | None = None) -> CodePatch:
        compat = offer.compatibility
        from_id = compat.required_catalog_id if compat else None
        to_id = compat.offered_catalog_id if compat else None
        base = {"from_catalog_id": from_id, "to_catalog_id": to_id}
        if not from_id or not to_id or from_id == to_id:
            return CodePatch(
                status="unavailable",
                reason="no_substitute",
                **base,
                detail="This offer is not a catalogue substitute for the part, so no code "
                "change is known.",
            )
        if compat and any(f.rule == "board_chip" for f in compat.findings):
            return CodePatch(
                status="unavailable",
                reason="out_of_scope_mcu",
                **base,
                detail="Porting code to a different microcontroller is out of scope.",
                notes=code_adapt.notes_for(from_id, to_id, None),
            )
        urls = source_files(job)
        read = self.read(urls)
        files = {path: text for path, (text, _) in read.items()}
        if urls and not read:
            return CodePatch(
                status="unavailable",
                reason="file_not_read",
                **base,
                detail="The project's code files could not be read right now.",
                notes=code_adapt.notes_for(from_id, to_id, None),
            )
        result = code_adapt.apply_recipe(files, from_id, to_id)
        if result.ok:
            return CodePatch(
                status="ready",
                origin="curated",
                accepted=True,
                **base,
                files=[
                    CodePatchFile(
                        path=f.path,
                        diff=f.diff,
                        source_url=read[f.path][1],
                        sha256=digest(f.original),
                    )
                    for f in result.files
                ],
                applied=result.applied,
                skipped=result.skipped,
                notes=result.notes,
            )
        if (
            result.reason == "recipe_not_applicable"
            and code_adapt.recipe_for(from_id, to_id) is None
            and files
            and self.settings.code_adapt_ai
            and not job.demo
        ):
            return self.ai_draft(job, read, from_id, to_id, result.notes, base, line_id)
        return CodePatch(
            status="unavailable",
            reason=result.reason,
            detail=result.detail,
            **base,
            notes=result.notes,
            skipped=result.skipped,
        )

    def ai_inputs(self, read, from_id, to_id) -> dict:
        """Model inputs for an edge: at most 3 files (60 KB) that use the original part."""
        catalog = load_catalog()
        original, substitute = catalog.get(from_id), catalog.get(to_id)
        marks = markers(original)
        relevant = {path: text for path, (text, _) in read.items() if any(m in text for m in marks)}
        chosen: dict[str, str] = {}
        size = 0
        for path, text in relevant.items():
            if len(chosen) == AI_MAX_FILES or size + len(text.encode()) > AI_MAX_BYTES:
                break
            chosen[path], size = text, size + len(text.encode())
        changes = [t for area, t in code_adapt.edge_changes(from_id, to_id) if area == "code"]
        return {
            "files": chosen,
            "original": json.loads(original.model_dump_json()),
            "substitute": json.loads(substitute.model_dump_json()),
            "changes": changes or ["Adapt the code to the substitute part."],
            "allowed_new_includes": includes(substitute),
            "original_markers": marks,
        }

    def ai_draft(self, job, read, from_id, to_id, notes, base, line_id=None) -> CodePatch:
        from bharat_sourcer import code_adapt_ai

        inputs = self.ai_inputs(read, from_id, to_id)
        chosen = inputs["files"]
        if not chosen:
            return CodePatch(
                status="unavailable",
                reason="file_not_read",
                **base,
                notes=notes,
                detail="No readable code file references the original part's library.",
            )
        day = datetime.now(UTC).strftime("%Y%m%d")
        if not self.jobs.store.consume({f"code-adapt-{day}": self.settings.code_adapt_daily_limit}):
            return CodePatch(
                status="unavailable",
                reason="budget",
                **base,
                notes=notes,
                detail="The daily AI code-draft budget is used up; try tomorrow.",
            )
        ledger = JobLedger(
            job.job_id, self.settings.job_gemini_budget_usd, previous=job.cost_estimate
        )
        self.ledger = ledger
        generate = self.generate or code_adapt_ai.make_gemini_generate(self.settings)
        with attribute(ledger, line_id):
            if not paid_allowed():
                return CodePatch(
                    status="unavailable",
                    reason="budget",
                    **base,
                    notes=notes,
                    detail="This project's AI budget for the current run is used up.",
                )
            result = code_adapt_ai.draft_patch(**inputs, generate=generate)
        if not result.ok:
            return CodePatch(
                status="unavailable",
                reason="ai_failed_validation",
                **base,
                notes=notes,
                ai_calls=result.calls,
                detail="; ".join(result.errors)[:500] or None,
            )
        return CodePatch(
            status="ready",
            origin="ai_draft",
            accepted=False,
            **base,
            ai_calls=result.calls,
            files=[
                CodePatchFile(
                    path=path, diff=diff, source_url=read[path][1], sha256=digest(chosen[path])
                )
                for path, diff in result.diffs.items()
            ],
            notes=notes + [f"AI note: {n}" for n in result.notes][:10],
            assumptions=result.assumptions[:10],
        )

    # -- accepting and downloading ----------------------------------------------
    def accept(self, job_id: str, line_id: str, token) -> CodePatch | None:
        def change(record):
            job = self.jobs._authorized(record, token)
            patch = self.line(job, line_id).code_patch
            if patch is None or patch.status != "ready":
                raise JobError(404, "PATCH_NOT_FOUND", "No code patch for this part")
            patch.accepted = True
            job.updated_at = datetime.now(UTC)

        record = self.jobs.store.mutate(job_id, change)
        if record is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return self.line(record.job, line_id).code_patch

    def download(self, job_id: str, line_id: str, token) -> bytes:
        from bharat_sourcer.code_adapt_ai import PatchError, apply_unified_diff

        job = self.jobs.get(job_id, token)
        patch = self.line(job, line_id).code_patch
        if patch is None or patch.status != "ready":
            raise JobError(404, "PATCH_NOT_FOUND", "No code patch for this part")
        if not patch.accepted:
            raise JobError(409, "PATCH_NOT_ACCEPTED", "Accept the AI draft before downloading")
        read = self.read({f.path: f.source_url for f in patch.files})
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in patch.files:
                text = read.get(file.path, (None,))[0]
                if text is None or digest(text) != file.sha256:
                    raise JobError(
                        409,
                        "SOURCE_CHANGED",
                        "The project's code changed since this patch was made; request a new patch",
                    )
                try:
                    archive.writestr(file.path, apply_unified_diff(text, file.diff))
                except PatchError as exc:
                    raise JobError(409, "SOURCE_CHANGED", "The patch no longer applies") from exc
            license_text = self.license(patch.files[0].source_url) if patch.files else None
            if license_text:
                archive.writestr("LICENSE", license_text)
            archive.writestr("README-BHARAT-SOURCER.txt", readme(patch, bool(license_text)))
        return buffer.getvalue()

    def license(self, source_url: str) -> str | None:
        root = repo_root(source_url)
        found = self.read({name: root + name for name in LICENSE_NAMES})
        return next((found[name][0] for name in LICENSE_NAMES if name in found), None)


def check_lines(patch: CodePatch) -> list[str]:
    run = patch.compile
    if run and patch.check == "compiles":
        when = run.finished_at.date().isoformat() if run.finished_at else "unknown date"
        return [
            f"Check: compiled for {run.board} ({run.fqbn}) with {run.core or 'pinned core'}",
            f"on {when}. Compile only: NOT tested on hardware. Review every change before",
            "uploading to a board.",
        ]
    if run and patch.check == "compile_failed":
        return [
            f"Check: did NOT compile for {run.board} ({run.fqbn}); see the compiler output in",
            "the app. Not tested on hardware.",
        ]
    return [
        "Check: NOT COMPILED and not tested on hardware. Review every change before",
        "uploading to a board.",
    ]


def readme(patch: CodePatch, has_license: bool) -> str:
    origin = {
        "curated": "Curated change from a maintained recipe",
        "ai_draft": "AI draft, validated by rules and accepted by the project owner",
    }[patch.origin or "curated"]
    lines = [
        "Bharat Sourcer code patch",
        "",
        f"Substitute: {patch.from_catalog_id} -> {patch.to_catalog_id}",
        f"Origin: {origin}",
        *check_lines(patch),
        f"Created: {patch.created_at.isoformat()}",
        "",
        "Files (patched copies of the original project's files):",
        *[f"- {f.path} (from {f.source_url})" for f in patch.files],
        "",
        "Applied:",
        *([f"- {a}" for a in patch.applied] or ["- see diffs"]),
        "",
        "Not patched; do these yourself:",
        *([f"- {n}" for n in patch.notes] or ["- nothing listed"]),
    ]
    if patch.assumptions:
        lines += ["", "AI assumptions:", *[f"- {a}" for a in patch.assumptions]]
    lines += [
        "",
        "License: the original project's LICENSE is included."
        if has_license
        else "License: no LICENSE file was found in the original repository; check the "
        "project's terms before sharing these files.",
    ]
    return "\n".join(lines) + "\n"
