"""Compile-only checks of code patches in isolated Cloud Run jobs (code-adapt tier 3).

Flow: the owner asks for a check; the board comes from the request or the BOM
(`data/compile_boards.json`). The API stores a queued `CompileCheck` and starts the Cloud
Run job for the board's core family with one override, the run id. The runner
(`backend/compile/runner.py`) has no permissions, no secrets and no internet route (Direct
VPC egress to a subnet without NAT; Private Google Access reaches this API only). It asks
this API for the sketch, compiles it with pinned cores and libraries baked into its
image, and posts the result back. Both internal routes accept only ID tokens for the
runner's service account.

The API builds the sketch itself: it downloads the repository snapshot through the guarded
fetcher, checks each patched file against the sha256 recorded when the patch was made,
applies the diffs and sends the sketch folder's source files. PlatformIO projects are not
compiled (their build scripts run repository Python).

A failed AI draft gets at most two repair rounds: one model call each, through the same
validators as the first draft, then a new compile. Results are idempotent: only the
current run id of a queued check is accepted. Compiling never uploads or runs code.
"""

import io
import json
import logging
import re
import secrets
import tarfile
from datetime import UTC, datetime, timedelta
from functools import cache
from importlib import resources
from posixpath import basename, dirname
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field

from bharat_sourcer.code_patches import RAW_HOST, CodePatchService, digest
from bharat_sourcer.jobs import JobError
from bharat_sourcer.schemas import (
    CodePatch,
    CodePatchFile,
    CompileBoard,
    CompileBoards,
    CompileCheck,
    CompileRequest,
    Job,
    Model,
)
from bharat_sourcer.sourcing.fetch import FetchError
from bharat_sourcer.usage import JobLedger, attribute, paid_allowed

log = logging.getLogger(__name__)

SKETCH_SUFFIXES = (".ino", ".cpp", ".c", ".h", ".hpp", ".s", ".tpp", ".ipp")
TARBALL_BYTES = 8_000_000
TAR_MEMBERS = 20_000
FILE_BYTES = 300_000
SKETCH_FILES = 150
SKETCH_BYTES = 1_500_000
CHECK_MINUTES = 15
MAX_REPAIRS = 2
LOG_LINES = 40
LOG_CHARS = 6000
RUN_ID = re.compile(r"^([0-9a-f-]{36})\.([\w-]{1,40})\.([1-3])\.([0-9a-f]{16})$")
SEGMENT = re.compile(r"[A-Za-z0-9._~ +-]{1,100}")


@cache
def boards() -> list[dict]:
    data = resources.files("bharat_sourcer").joinpath("data/compile_boards.json")
    return json.loads(data.read_text("utf-8"))["boards"]


def board_for(fqbn: str) -> dict | None:
    return next((b for b in boards() if b["fqbn"] == fqbn), None)


def detect_boards(job: Job) -> list[dict]:
    """Distinct boards named in the BOM; per part name the longest matching alias wins."""
    found: list[dict] = []
    for item in job.items:
        name = " ".join(item.raw_name.lower().replace("_", " ").split())
        best, length = None, 0
        for board in boards():
            if any(word in name for word in board.get("exclude", [])):
                continue
            for alias in board["names"]:
                pattern = rf"(?<![\w-]){re.escape(alias)}(?![\w-])"
                if len(alias) > length and re.search(pattern, name):
                    best, length = board, len(alias)
        if best and best not in found:
            found.append(best)
    return found


def board_list() -> str:
    return ", ".join(b["fqbn"] for b in boards())


class CompileUnavailable(Exception):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason, self.detail = reason, detail


class RunnerResult(Model):
    """What the runner reports; text fields are trimmed again before storing."""

    status: Literal["compiles", "compile_failed", "timeout", "error"]
    log: str | None = Field(default=None, max_length=50_000)
    core: str | None = Field(default=None, max_length=200)
    size: str | None = Field(default=None, max_length=1000)
    detail: str | None = Field(default=None, max_length=1000)


def trim_log(text: str | None) -> str | None:
    if not text:
        return None
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    errors = [line for line in lines if re.search(r"\berror\b", line, re.IGNORECASE)]
    # Lead with the error lines, then the rest for context, without duplicates.
    ordered = list(dict.fromkeys(errors + lines))[:LOG_LINES]
    return "\n".join(ordered)[:LOG_CHARS] or None


# --- sketch assembly ------------------------------------------------------------------------


def repository(raw_url: str) -> tuple[str, str, str]:
    parts = urlsplit(raw_url)
    if (parts.hostname or "").lower() != RAW_HOST:
        raise CompileUnavailable("source_unavailable", "The code is not from a GitHub repository.")
    owner, repo, ref = parts.path.strip("/").split("/")[:3]
    return owner, repo, ref


def safe_member(name: str) -> str | None:
    """Repository-relative path of a tarball member, without the archive's top folder."""
    segments = name.split("/")[1:]
    if not segments or len(segments) > 10:
        return None
    if any(seg in {"", ".", ".."} or not SEGMENT.fullmatch(seg) for seg in segments):
        return None
    return "/".join(segments)


def read_tree(body: bytes) -> tuple[dict[str, str], bool]:
    """Source files (path -> text) of a repository tarball, and whether it has platformio.ini."""
    tree: dict[str, str] = {}
    platformio = False
    try:
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as archive:
            for index, member in enumerate(archive):
                if index >= TAR_MEMBERS:
                    raise CompileUnavailable("too_large", "The repository has too many files.")
                path = safe_member(member.name)
                if path is None or not member.isfile():
                    continue
                if basename(path).lower() == "platformio.ini":
                    platformio = True
                if not path.lower().endswith(SKETCH_SUFFIXES) or member.size > FILE_BYTES:
                    continue
                handle = archive.extractfile(member)
                data = handle.read(FILE_BYTES + 1) if handle else b""
                if b"\0" in data[:4096]:
                    continue
                tree[path] = data.decode("utf-8", errors="replace")
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise CompileUnavailable("source_unavailable", "The repository could not be read.") from exc
    return tree, platformio


def sketch_folder(tree: dict[str, str], patched: list[str]) -> str | None:
    """The folder of the sketch the patch belongs to: nearest folder up with an .ino file."""
    folders = {dirname(path) for path in tree if path.lower().endswith(".ino")}
    for path in patched:
        folder = dirname(path)
        while True:
            if folder in folders:
                return folder
            if not folder:
                break
            folder = dirname(folder)
    return None


def primary_ino(folder: str, names: list[str], tree: dict[str, str]) -> str | None:
    inos = sorted(n for n in names if "/" not in n and n.lower().endswith(".ino"))
    stem = basename(folder) if folder else ""
    if f"{stem}.ino" in inos:
        return f"{stem}.ino"
    if len(inos) == 1:
        return inos[0]
    prefix = f"{folder}/" if folder else ""
    setup = [n for n in inos if re.search(r"\bvoid\s+setup\s*\(", tree[prefix + n])]
    return setup[0] if len(setup) == 1 else None


def build_sketch(fetcher, patch: CodePatch) -> dict:
    """{"sketch", "folder", "files"} for the runner; raises CompileUnavailable."""
    from bharat_sourcer.code_adapt_ai import PatchError, apply_unified_diff

    if not patch.files:
        raise CompileUnavailable("sketch_not_found", "The patch changes no files.")
    owner, repo, ref = repository(patch.files[0].source_url)
    url = f"https://codeload.github.com/{owner}/{repo}/tar.gz/{ref}"
    try:
        page = fetcher.get(url, max_bytes=TARBALL_BYTES)
    except FetchError as exc:
        reason = "too_large" if "size" in str(exc) else "source_unavailable"
        detail = "The repository snapshot could not be downloaded."
        raise CompileUnavailable(reason, detail) from exc
    if page.status != 200:
        raise CompileUnavailable("source_unavailable", f"GitHub answered HTTP {page.status}.")
    tree, platformio = read_tree(page.body)
    for file in patch.files:
        text = tree.get(file.path)
        if text is None or digest(text) != file.sha256:
            raise CompileUnavailable(
                "source_changed",
                f"{file.path} changed since the patch was made; request a new patch.",
            )
        try:
            tree[file.path] = apply_unified_diff(text, file.diff)
        except PatchError as exc:
            raise CompileUnavailable("source_changed", "The patch no longer applies.") from exc
    folder = sketch_folder(tree, [f.path for f in patch.files])
    if folder is None:
        if platformio:
            raise CompileUnavailable(
                "platformio_not_supported",
                "PlatformIO projects are not compiled; their build scripts run project code.",
            )
        raise CompileUnavailable("sketch_not_found", "No Arduino sketch (.ino) holds the patch.")
    prefix = f"{folder}/" if folder else ""
    names = [path[len(prefix) :] for path in tree if path.startswith(prefix)]
    if folder == "":
        # A sketch at the repository root: only its own folder and src/, not other sketches.
        names = [n for n in names if "/" not in n or n.startswith("src/")]
    main = primary_ino(folder, names, tree)
    if main is None:
        raise CompileUnavailable("sketch_not_found", "The sketch's main .ino file is unclear.")
    if len(names) > SKETCH_FILES or sum(len(tree[prefix + n]) for n in names) > SKETCH_BYTES:
        raise CompileUnavailable("too_large", "The sketch is too large to compile here.")
    sketch = re.sub(r"[^A-Za-z0-9_.-]", "_", main[:-4])[:60].lstrip(".-") or "sketch"
    files = {}
    for name in names:
        target = f"{sketch}.ino" if name == main else name
        files[target] = tree[prefix + name]
    return {"sketch": sketch, "folder": folder or ".", "source": prefix + main, "files": files}


# --- launching and identity -----------------------------------------------------------------


class CloudRunJobLauncher:
    """Starts `<prefix>-<family>` with the run id as its only override."""

    def __init__(self, settings):
        self.settings = settings

    def launch(self, family: str, run_id: str) -> None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        s = self.settings
        job = f"{s.compile_job_prefix}-{family}"
        name = f"projects/{s.gcp_project}/locations/{s.compile_region}/jobs/{job}"
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        with AuthorizedSession(credentials) as session:
            response = session.post(
                f"https://run.googleapis.com/v2/{name}:run",
                json={
                    "overrides": {
                        "containerOverrides": [
                            {"env": [{"name": "BS_COMPILE_RUN_ID", "value": run_id}]}
                        ],
                        "taskCount": 1,
                    }
                },
                timeout=20,
            )
            response.raise_for_status()


def runner_identity(settings, authorization: str | None) -> bool:
    """True for a Google ID token of the runner's service account for this API."""
    import google.auth.exceptions
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    audience = settings.compile_audience or settings.tasks_url
    if not authorization or not authorization.startswith("Bearer ") or not audience:
        return False
    try:
        claims = id_token.verify_oauth2_token(authorization[7:], Request(), audience=audience)
    except (ValueError, google.auth.exceptions.GoogleAuthError):
        return False
    return (
        claims.get("email") == settings.compile_service_account
        and claims.get("email_verified") is True
    )


# --- service --------------------------------------------------------------------------------


def new_check(job_id: str, line_id: str, board: dict, attempt: int, repairs: int) -> CompileCheck:
    requested = datetime.now(UTC)
    return CompileCheck(
        status="queued",
        fqbn=board["fqbn"],
        board=board["label"],
        run_id=f"{job_id}.{line_id}.{attempt}.{secrets.token_hex(8)}",
        attempt=attempt,
        repairs=repairs,
        requested_at=requested,
        expires_at=requested + timedelta(minutes=CHECK_MINUTES),
    )


class CompileService:
    def __init__(self, settings, jobs, patches: CodePatchService, launcher=None):
        self.settings, self.jobs, self.patches = settings, jobs, patches
        if launcher is None and settings.compile_backend == "cloud_run_job":
            launcher = CloudRunJobLauncher(settings)
        self.launcher = launcher

    def boards(self) -> CompileBoards:
        return CompileBoards(
            enabled=self.launcher is not None,
            boards=[
                CompileBoard(fqbn=b["fqbn"], label=b["label"], family=b["family"]) for b in boards()
            ],
        )

    def choose_board(self, job: Job, fqbn: str | None) -> dict:
        if fqbn:
            board = board_for(fqbn)
            if board is None:
                message = f"Board {fqbn} is not supported; use one of {board_list()}"
                raise JobError(422, "FQBN_UNSUPPORTED", message)
            return board
        found = detect_boards(job)
        if len(found) == 1:
            return found[0]
        named = "several boards" if found else "no supported board"
        raise JobError(
            422, "FQBN_REQUIRED", f"The parts list names {named}; choose one of {board_list()}"
        )

    # -- owner route -----------------------------------------------------------------------
    def request(self, job_id: str, line_id: str, token, body: CompileRequest) -> CodePatch:
        if self.launcher is None:
            raise JobError(503, "COMPILE_UNAVAILABLE", "Compile checks are not enabled here")
        job = self.jobs.get(job_id, token)
        patch = self.patches.line(job, line_id).code_patch
        if patch is None or patch.status != "ready":
            raise JobError(404, "PATCH_NOT_FOUND", "No code patch for this part")
        if job.demo:
            raise JobError(409, "INVALID_STATE", "Demo projects are not compiled")
        current = patch.compile
        if current and current.status == "queued" and current.expires_at > datetime.now(UTC):
            raise JobError(409, "COMPILE_IN_PROGRESS", "A compile check is already running")
        board = self.choose_board(job, body.fqbn)
        day = datetime.now(UTC).strftime("%Y%m%d")
        if not self.jobs.store.consume({f"compile-{day}": self.settings.compile_daily_limit}):
            raise JobError(429, "COMPILE_DAILY_LIMIT", "Daily compile checks are used up", 3600)
        check = new_check(job_id, line_id, board, attempt=1, repairs=0)
        made = patch.created_at

        def save(record):
            saved = self.patches.line(self.jobs._authorized(record, token), line_id).code_patch
            if saved is None or saved.created_at != made:
                raise JobError(409, "PROPOSAL_STALE", "The patch changed; request the check again")
            saved.compile = check
            saved.check = "not_checked"
            record.job.updated_at = datetime.now(UTC)

        record = self.jobs.store.mutate(job_id, save)
        if record is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return self.start(job_id, line_id, board["family"], check.run_id) or patch_of(
            record.job, line_id
        )

    def start(self, job_id: str, line_id: str, family: str, run_id: str) -> CodePatch | None:
        try:
            self.launcher.launch(family, run_id)
        except Exception as exc:  # noqa: BLE001 - any launch failure is reported on the check
            log.error("COMPILE_LAUNCH_FAILED run=%s type=%s", run_id, type(exc).__name__)
            record = self.finish(
                run_id,
                status="unavailable",
                reason="launch_failed",
                detail="The compile runner could not be started; try again later.",
            )
            return patch_of(record.job, line_id) if record else None
        return None

    # -- runner routes ---------------------------------------------------------------------
    def locate(self, run_id: str):
        match = RUN_ID.fullmatch(run_id)
        if not match:
            return None, None, None
        job_id, line_id = match.group(1), match.group(2)
        record = self.jobs.store.get(job_id)
        if record is None or record.job.report is None:
            return None, None, None
        line = next((ln for ln in record.job.report.lines if ln.item.line_id == line_id), None)
        patch = line.code_patch if line else None
        if patch is None or patch.compile is None or patch.compile.run_id != run_id:
            return None, None, None
        return record.job, line_id, patch

    def bundle(self, run_id: str) -> dict:
        job, line_id, patch = self.locate(run_id)
        if patch is None or patch.compile.status != "queued":
            raise JobError(410, "RUN_STALE", "This compile run is no longer current")
        try:
            sketch = build_sketch(self.patches.fetcher, patch)
        except CompileUnavailable as exc:
            self.finish(run_id, status="unavailable", reason=exc.reason, detail=exc.detail)
            raise JobError(409, "COMPILE_UNAVAILABLE", exc.detail) from exc
        self.finish(run_id, sketch=sketch["source"], keep=True)
        return {"run_id": run_id, "fqbn": patch.compile.fqbn, **sketch}

    def result(self, run_id: str, body: RunnerResult) -> dict:
        job, line_id, patch = self.locate(run_id)
        if patch is None or patch.compile.status != "queued":
            return {"accepted": False}
        text = trim_log(body.log)
        if body.status == "compile_failed" and self.can_repair(job, patch):
            if self.repair(job, line_id, patch, text or ""):
                return {"accepted": True, "repair": True}
            note = "No AI repair: the budget, a source change or validation stopped it."
            text = ((text or "") + "\n" + note)[-LOG_CHARS:]
        if body.status in {"compiles", "compile_failed"}:
            self.finish(run_id, status=body.status, log=text, core=body.core, size=body.size)
        elif body.status == "timeout":
            self.finish(run_id, status="timeout", log=text, core=body.core)
        else:
            self.finish(
                run_id,
                status="unavailable",
                reason="runner_error",
                detail=(body.detail or "The compile runner failed.")[:500],
                log=text,
            )
        return {"accepted": True}

    def finish(self, run_id: str, *, keep: bool = False, **fields):
        """Update the current run's check; ignored once the run is no longer current."""
        job_id = run_id.split(".")[0]

        def change(record):
            patch = patch_of(record.job, RUN_ID.fullmatch(run_id).group(2))
            if patch is None or patch.compile is None or patch.compile.run_id != run_id:
                return
            if patch.compile.status != "queued":
                return
            values = {k: v for k, v in fields.items() if v is not None}
            if "size" in values:
                values["size"] = values["size"][:300]
            if "core" in values:
                values["core"] = values["core"][:100]
            if not keep:
                values["finished_at"] = datetime.now(UTC)
            patch.compile = patch.compile.model_copy(update=values)
            if values.get("status") in {"compiles", "compile_failed"}:
                patch.check = values["status"]
            record.job.updated_at = datetime.now(UTC)

        return self.jobs.store.mutate(job_id, change)

    # -- AI repair rounds ------------------------------------------------------------------
    def can_repair(self, job: Job, patch: CodePatch) -> bool:
        return (
            patch.origin == "ai_draft"
            and patch.compile.repairs < MAX_REPAIRS
            and self.settings.code_adapt_ai
            and not job.demo
        )

    def repair(self, job: Job, line_id: str, patch: CodePatch, compiler_log: str) -> bool:
        """One validated revision and a new compile run; False leaves the failure standing."""
        from bharat_sourcer import code_adapt_ai
        from bharat_sourcer.code_patches import source_files

        read = self.patches.read(source_files(job))
        for file in patch.files:
            text = read.get(file.path, (None,))[0]
            if text is None or digest(text) != file.sha256:
                return False
        inputs = self.patches.ai_inputs(read, patch.from_catalog_id, patch.to_catalog_id)
        if not inputs["files"] or any(f.path not in inputs["files"] for f in patch.files):
            return False
        day = datetime.now(UTC).strftime("%Y%m%d")
        if not self.jobs.store.consume({f"code-adapt-{day}": self.settings.code_adapt_daily_limit}):
            return False
        ledger = JobLedger(
            job.job_id, self.settings.job_gemini_budget_usd, previous=job.cost_estimate
        )
        generate = self.patches.generate or code_adapt_ai.make_gemini_generate(self.settings)
        with attribute(ledger, line_id):
            if not paid_allowed():
                return False
            result = code_adapt_ai.repair_after_compile(
                inputs["files"],
                {f.path: f.diff for f in patch.files},
                compiler_log,
                generate=generate,
                **{k: v for k, v in inputs.items() if k != "files"},
            )
        old = patch.compile
        board = board_for(old.fqbn) or {"fqbn": old.fqbn, "label": old.board, "family": ""}
        check = new_check(job.job_id, line_id, board, old.attempt + 1, old.repairs + 1)
        start = job.cost_estimate
        files = [
            CodePatchFile(
                path=path,
                diff=diff,
                source_url=read[path][1],
                sha256=digest(inputs["files"][path]),
            )
            for path, diff in result.diffs.items()
        ]

        def save(record):
            saved = patch_of(record.job, line_id)
            if saved is None or saved.compile is None or saved.compile.run_id != old.run_id:
                raise JobError(409, "RUN_STALE", "This compile run is no longer current")
            saved.ai_calls = min(saved.ai_calls + result.calls, 10)
            if record.job.cost_estimate == start:
                record.job.cost_estimate = ledger.snapshot()
            if not result.ok:
                return
            saved.files = files
            saved.accepted = False
            saved.check = "not_checked"
            saved.notes = (saved.notes + [f"AI note: {n}" for n in result.notes])[:20]
            saved.assumptions = (saved.assumptions + result.assumptions)[:10]
            saved.compile = check.model_copy(
                update={"detail": f"Repair round {check.repairs} after compiler errors."}
            )
            record.job.updated_at = datetime.now(UTC)

        try:
            self.jobs.store.mutate(job.job_id, save)
        except JobError:
            return True  # a newer run owns the check; nothing more to do for this result
        if not result.ok:
            return False
        self.start(job.job_id, line_id, board["family"], check.run_id)
        return True


def patch_of(job: Job, line_id: str) -> CodePatch | None:
    lines = job.report.lines if job.report else []
    return next((ln.code_patch for ln in lines if ln.item.line_id == line_id), None)


def authorize_runner(service: CompileService, authorization: str | None) -> None:
    if service.launcher is None or not runner_identity(service.settings, authorization):
        raise JobError(401, "RUNNER_AUTH_REQUIRED", "Compile runner identity required")
