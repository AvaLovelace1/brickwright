"""A record: a self-contained LEGO build attempt on disk.

A record is a directory holding the build code, its prompt, metadata,
and the outputs of the last verification/build.
"""

from __future__ import annotations

import re
import shutil
import uuid
from collections import Counter
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from importlib import resources
from math import isfinite
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from .config import Config, Effort
from .tools.software_rendering import VIEW_ORDER

# <YYYYMMDD>-<HHMMSS>[-<slug>]-<8 hex>, e.g. 20260614-103245-red-castle-a1b2c3d4.
ID_PATTERN = r"\d{8}-\d{6}-(?:[a-z0-9-]+-)?[0-9a-f]{8}"

# The names of the files and directories that make up a record's on-disk layout.
BUILD_NAME = "build.py"
META_NAME = "meta.json"
MESSAGES_NAME = "messages.jsonl"
OUT_DIRNAME = "out"
DIAGNOSTICS_DIRNAME = "diagnostics"
CONNECTIVITY_DIRNAME = "connectivity"
LDR_NAME = "build.ldr"
MESH_NAME = "build.glb"
RENDER_NAME = "build.png"
# Single angled renders: from the viewpoint-matching agent, and from the builder.
VIEWPOINT_NAME = "viewpoint.png"
ANGLE_RENDER_NAME = "build_angle.png"
REPORT_NAME = "report.json"
CRITIQUE_NAME = "critique.json"
SNAPSHOTS_DIRNAME = "snapshots"
SUBAGENTS_DIRNAME = "subagents"
VIEWPOINTS_DIRNAME = "viewpoints"  # one numbered session per viewpoint-matching run

_RECORD_TEMPLATE = (resources.files("brickwright") / "_build_template.py").read_text()


class Status(str, Enum):
    """Where a record stands in its lifecycle."""

    CREATED = "created"  # just initialized; not yet verified
    VALID = "valid"  # built and passed verification
    INVALID = "invalid"  # built but physically invalid (collision/floating/check)
    ERROR = "error"  # the build itself raised or timed out


class StopReason(str, Enum):
    """Why generation stopped, independently of the build's physical validity."""

    FINALIZED = "finalized"
    MAX_COST = "max_cost"
    UNKNOWN_COST = "unknown_cost"
    MAX_TURNS = "max_turns"
    MAX_VALIDATIONS = "max_validations"
    MODEL_STOPPED = "model_stopped"
    ERROR = "error"


class Generation(BaseModel):
    """How a record's ``build.py`` was produced."""

    model_config = ConfigDict(frozen=True)

    model: str | None  # None if unknown
    effort: Effort | None  # None if unknown
    external: bool = False  # driven by an external agent through the CLI
    config: dict[str, Any] | None = (
        None  # resolved settings, excluding output directory
    )


class Timing(BaseModel):
    """Where a run's wall-clock time went, in seconds. ``llm``, ``other``, and the
    per-tool times in ``tools`` sum to ``total``.

    For the in-process driver, every field is measured.
    For an externally driven run, only the per-tool times are measured (per CLI
    command); the unmeasured remainder is attributed to ``llm`` and ``other``
    stays 0.
    """

    model_config = ConfigDict(frozen=True)

    total: float = 0.0  # whole run, wall-clock
    llm: float = 0.0  # model/agent thinking
    tools: dict[str, float] = {}  # wall-clock per tool, keyed by tool name
    other: float = 0.0  # loop overhead (in-process driver only)


class PromptTokensDetails(BaseModel):
    """Breakdown of the prompt token usage."""

    model_config = ConfigDict(frozen=True)

    cached_tokens: int | None = None  # prompt tokens served from the prompt cache


class CompletionTokensDetails(BaseModel):
    """Breakdown of the completion token usage."""

    model_config = ConfigDict(frozen=True)

    reasoning_tokens: int | None = None  # reasoning tokens, not shown in the output
    accepted_prediction_tokens: int | None = None  # predicted-output tokens used
    rejected_prediction_tokens: int | None = None  # predicted-output tokens discarded


class Usage(BaseModel):
    """Token counts and cost accumulated over a run's completions."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float | None = None  # None when the cost is unknown
    known_cost_usd: float = 0.0  # known subtotal, even when the total is unknown
    prompt_tokens_details: PromptTokensDetails = PromptTokensDetails()
    completion_tokens_details: CompletionTokensDetails = CompletionTokensDetails()


class ValidationFailures(BaseModel):
    """Why a run's validations failed, tallied by reason."""

    model_config = ConfigDict(frozen=True)

    build_errors: dict[str, int] = {}  # count by raising exception type
    failing_checks: dict[str, int] = {}  # count by failing check name


class Meta(BaseModel):
    """The schema of a record's ``meta.json``."""

    model_config = ConfigDict(frozen=True)

    id: str
    created: datetime | None = None
    status: Status = Status.CREATED
    validated_source_sha256: str | None = None
    exported_source_sha256: str | None = None
    finalized: bool = False
    stop_reason: StopReason | None = None
    over_budget: bool = False
    prompt: str = ""
    prompt_image: str | None = None
    generation: Generation
    turns: int = 0  # model turns taken by the generate loop
    validations: int = 0  # number of times the build was validated
    validation_failures: ValidationFailures | None = None  # why validations failed
    critique_rounds: int = 0  # number of outer visual-critique rounds run
    tool_calls: dict[str, int] = {}  # how many times each tool/command was called
    timing: Timing | None = None  # detailed per-phase wall-clock breakdown
    usage: Usage | None = None  # token usage & cost info
    forked_from: str | None = None


class Snapshot:
    """Handle to one snapshot directory."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def build_path(self) -> Path:
        return self.path / BUILD_NAME

    @property
    def report_path(self) -> Path:
        return self.path / REPORT_NAME

    @property
    def render_path(self) -> Path:
        """The multi-view contact sheet of this snapshot's build, if one was saved."""
        return self.path / RENDER_NAME

    def read_build(self) -> str:
        return self.build_path.read_bytes().decode("utf-8")

    def read_report(self) -> str:
        return self.report_path.read_text()


class UsageTracker:
    """Track running totals of token counts, cost, and token-detail breakdowns."""

    def __init__(self) -> None:
        self._prompt = 0
        self._completion = 0
        self._total = 0
        self._cost = 0.0
        self._cost_known = False
        self._has_unknown_cost = False
        self._prompt_details: Counter[str] = Counter()
        self._completion_details: Counter[str] = Counter()

    def add(self, usage: Usage) -> None:
        self._prompt += usage.prompt_tokens
        self._completion += usage.completion_tokens
        self._total += usage.total_tokens
        if (
            usage.cost_usd is not None
            and isfinite(usage.cost_usd)
            and usage.cost_usd >= 0
        ):
            self._cost += usage.cost_usd
            self._cost_known = True
        else:
            self._has_unknown_cost = True
            if isfinite(usage.known_cost_usd) and usage.known_cost_usd >= 0:
                self._cost += usage.known_cost_usd
        self._prompt_details.update(
            usage.prompt_tokens_details.model_dump(exclude_none=True)
        )
        self._completion_details.update(
            usage.completion_tokens_details.model_dump(exclude_none=True)
        )

    @property
    def cost(self) -> float:
        return self._cost

    @property
    def cost_known(self) -> bool:
        return self._cost_known and not self._has_unknown_cost

    @property
    def has_unknown_cost(self) -> bool:
        return self._has_unknown_cost

    def usage(self) -> Usage:
        return Usage(
            prompt_tokens=self._prompt,
            completion_tokens=self._completion,
            total_tokens=self._total,
            cost_usd=round(self._cost, 6) if self.cost_known else None,
            known_cost_usd=round(self._cost, 6),
            prompt_tokens_details=PromptTokensDetails(**self._prompt_details),
            completion_tokens_details=CompletionTokensDetails(
                **self._completion_details
            ),
        )


class Record:
    """Handle to one record directory. Construct via :meth:`create`/:meth:`load`."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    # --- Layout ---

    @property
    def id(self) -> str:
        return self.path.name

    @property
    def build_path(self) -> Path:
        return self.path / BUILD_NAME

    @property
    def meta_path(self) -> Path:
        return self.path / META_NAME

    @property
    def prompt_image_path(self) -> Path | None:
        """The copied-in prompt image, or ``None`` if this record has no image."""
        name = self.read_meta().prompt_image
        return self.path / name if name else None

    @property
    def messages_path(self) -> Path:
        """JSONL log of every message exchanged during the agent run."""
        return self.path / MESSAGES_NAME

    @property
    def out_dir(self) -> Path:
        return self.path / OUT_DIRNAME

    @property
    def ldr_path(self) -> Path:
        return self.out_dir / LDR_NAME

    @property
    def mesh_path(self) -> Path:
        return self.out_dir / MESH_NAME

    @property
    def diagnostics_dir(self) -> Path:
        return self.out_dir / DIAGNOSTICS_DIRNAME

    @property
    def diagnostics_ldr_path(self) -> Path:
        return self.diagnostics_dir / LDR_NAME

    @property
    def diagnostics_mesh_path(self) -> Path:
        return self.diagnostics_dir / MESH_NAME

    @property
    def connectivity_dir(self) -> Path:
        return self.out_dir / CONNECTIVITY_DIRNAME

    @property
    def connectivity_ldr_path(self) -> Path:
        return self.connectivity_dir / LDR_NAME

    @property
    def connectivity_mesh_path(self) -> Path:
        return self.connectivity_dir / MESH_NAME

    @property
    def connectivity_report_path(self) -> Path:
        return self.connectivity_dir / "components.json"

    @property
    def render_path(self) -> Path:
        """The combined multi-view contact sheet (for human viewing / snapshots)."""
        return self.out_dir / RENDER_NAME

    def render_views(self) -> list[tuple[str, Path]]:
        """``(view name, PNG path)`` for each single-view render, in canonical order."""
        return [(name, self.out_dir / f"build_{name}.png") for name in VIEW_ORDER]

    @property
    def angle_render_path(self) -> Path:
        """A single angled render, overwritten each time the builder renders a pose."""
        return self.out_dir / ANGLE_RENDER_NAME

    @property
    def viewpoint_path(self) -> Path:
        """A single angled render, overwritten each time the viewpoint agent renders."""
        return self.out_dir / VIEWPOINT_NAME

    @property
    def report_path(self) -> Path:
        return self.out_dir / REPORT_NAME

    @property
    def critique_path(self) -> Path:
        """The latest visual-critique verdict, written by the outer critique loop."""
        return self.out_dir / CRITIQUE_NAME

    @property
    def snapshots_dir(self) -> Path:
        """History of the build: one snapshot per ``validate`` and per critique round."""
        return self.path / SNAPSHOTS_DIRNAME

    @property
    def subagents_dir(self) -> Path:
        """Directory for subagent records."""
        return self.path / SUBAGENTS_DIRNAME

    # --- build.py / meta.json access ---

    def read_build(self) -> str:
        return self.build_path.read_bytes().decode("utf-8")

    def write_build(self, source: str) -> None:
        changed = self.build_path.exists() and self.read_build() != source
        self.build_path.write_text(source)
        if changed and self.meta_path.exists():
            self.clear_exports()
            self.report_path.unlink(missing_ok=True)
            self.update_meta(status=Status.CREATED, validated_source_sha256=None)

    @property
    def source_sha256(self) -> str:
        """Digest of the current source, including edits made outside the tools."""
        return sha256(self.build_path.read_bytes()).hexdigest()

    def clear_exports(self) -> None:
        """Discard generated outputs and their completion marker; keep snapshots."""
        paths = [
            self.ldr_path,
            self.mesh_path,
            self.render_path,
            self.angle_render_path,
            self.viewpoint_path,
            self.diagnostics_ldr_path,
            self.diagnostics_mesh_path,
            self.connectivity_ldr_path,
            self.connectivity_mesh_path,
            self.connectivity_report_path,
            *(path for _, path in self.render_views()),
        ]
        for path in paths:
            path.unlink(missing_ok=True)
        self.update_meta(finalized=False, exported_source_sha256=None)

    def read_meta(self) -> Meta:
        meta = Meta.model_validate_json(self.meta_path.read_text())
        digest = self.source_sha256 if self.build_path.is_file() else None
        if meta.validated_source_sha256 not in (None, digest):
            meta = meta.model_copy(
                update={
                    "status": Status.CREATED,
                    "validated_source_sha256": None,
                    "exported_source_sha256": None,
                    "finalized": False,
                }
            )
        if meta.finalized and (
            meta.status is not Status.VALID
            or meta.exported_source_sha256 != digest
            or meta.validated_source_sha256 != digest
            or not self.ldr_path.is_file()
        ):
            meta = meta.model_copy(update={"finalized": False})
        return meta

    def write_meta(self, meta: Meta) -> None:
        self.meta_path.write_text(meta.model_dump_json(indent=2) + "\n")

    def update_meta(self, **changes: Any) -> Meta:
        """Merge ``changes`` into the metadata on disk and return the new meta."""
        meta = self.read_meta()
        unknown = set(changes) - set(type(meta).model_fields)
        if unknown:
            raise TypeError(f"unknown meta field(s): {', '.join(sorted(unknown))}")
        meta = meta.model_copy(update=changes)
        self.write_meta(meta)
        return meta

    # --- Snapshots ---

    @property
    def snapshots(self) -> list[Snapshot]:
        """Every snapshot taken for this record, oldest first."""
        if not self.snapshots_dir.is_dir():
            return []
        return [Snapshot(child) for child in _numbered_dirs(self.snapshots_dir)]

    def add_snapshot(self, source: str, report_json: str) -> Snapshot:
        """Archive a build's source and its report as the next numbered snapshot."""
        snapshot = Snapshot(_next_numbered_dir(self.snapshots_dir))
        snapshot.build_path.write_text(source)
        snapshot.report_path.write_text(report_json)
        return snapshot

    def add_render_snapshot(self) -> Snapshot | None:
        """Snapshot the current build with its contact sheet.

        A no-op returning ``None`` when there is no render to capture.
        """
        if not self.render_path.exists():
            return None
        report = self.report_path.read_text() if self.report_path.exists() else ""
        snapshot = self.add_snapshot(self.read_build(), report)
        shutil.copyfile(self.render_path, snapshot.render_path)
        return snapshot

    # --- Viewpoint sessions ---

    @property
    def viewpoints_dir(self) -> Path:
        """History of the viewpoint-matching agent: one numbered session per run."""
        return self.path / VIEWPOINTS_DIRNAME

    def new_viewpoint_session(self) -> Path:
        """Create and return the next numbered viewpoint-session directory.

        One per :func:`match_viewpoint` run (i.e. per critique round). Each holds the
        agent's candidate renders, its matched render, and its transcript.
        """
        return _next_numbered_dir(self.viewpoints_dir)

    # --- Lifecycle ---

    @classmethod
    def create(
        cls,
        config: Config,
        *,
        prompt: str = "",
        image: Path | str | None = None,
        from_id: str | None = None,
        external: bool = False,
    ) -> Record:
        """Create a new record directory and return a handle to it.

        With ``from_id``, the new record is forked from that existing record;
        otherwise ``build.py`` starts from the template. ``external`` marks the
        record as CLI-driven.
        """
        # Resolve the prompt and image first (a fork inherits its source's
        # prompt and prompt image) so the id can carry a readable slug derived
        # from them.
        cloned_src: str | None = None
        if from_id is not None:
            source = cls.load(config, from_id)
            cloned_src = source.read_build()
            source_meta = source.read_meta()
            if not prompt and image is None:
                prompt = source_meta.prompt
            if image is None:
                image = source.prompt_image_path
        image = Path(image) if image is not None else None

        # Read the image before touching disk, so a bad path does not leave a half-created record.
        prompt_image = None
        image_bytes = b""
        if image is not None:
            prompt_image = f"prompt{image.suffix}"
            image_bytes = image.read_bytes()

        slug = _slugify(prompt) or (_slugify(image.stem) if image is not None else "")
        record_id = new_id(slug)
        path = config.records_dir / record_id
        path.mkdir(parents=True, exist_ok=False)
        rec = cls(path)
        rec.out_dir.mkdir()

        rec.write_build(cloned_src if cloned_src is not None else get_template())

        if prompt_image is not None:
            (path / prompt_image).write_bytes(image_bytes)

        rec.write_meta(
            Meta(
                id=record_id,
                generation=Generation(
                    model=config.model,
                    effort=config.effort,
                    external=external,
                    config=config.model_dump(mode="json", exclude={"records_dir"}),
                ),
                prompt=prompt,
                prompt_image=prompt_image,
                created=datetime.now(UTC).astimezone().replace(microsecond=0),
                forked_from=from_id,
            )
        )
        return rec

    @classmethod
    def load(cls, config: Config, record_id: str) -> Record:
        """Load an existing record by id."""
        path = config.records_dir / record_id
        if not (path / META_NAME).is_file():
            raise FileNotFoundError(f"no record {record_id!r} in {config.records_dir}")
        return cls(path)


def get_template() -> str:
    return _RECORD_TEMPLATE


def list_records(config: Config) -> list[Record]:
    """Every record under ``config.records_dir``, sorted by id (oldest first)."""
    if not config.records_dir.is_dir():
        return []
    return [
        Record(child)
        for child in sorted(config.records_dir.iterdir())
        if re.fullmatch(ID_PATTERN, child.name) and (child / META_NAME).is_file()
    ]


def new_id(slug: str = "") -> str:
    """A fresh, sortable, unique record id.

    The id always starts with a timestamp (so ids sort oldest-first) and ends
    with a random suffix (so ids stay unique). When ``slug`` is given, it is
    inserted between them to make the id recognizable at a glance.
    """
    stamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S")
    rand = uuid.uuid4().hex[:8]
    return f"{stamp}-{slug}-{rand}" if slug else f"{stamp}-{rand}"


def _next_numbered_dir(parent: Path) -> Path:
    """Create and return ``parent``'s next ``NNN`` subdirectory."""
    parent.mkdir(parents=True, exist_ok=True)
    existing = _numbered_dirs(parent)
    n = int(existing[-1].name) + 1 if existing else 1
    while True:
        path = parent / f"{n:03d}"
        try:
            path.mkdir()
        except FileExistsError:
            n += 1
        else:
            return path


def _numbered_dirs(parent: Path) -> list[Path]:
    return sorted(
        (
            child
            for child in parent.iterdir()
            if re.fullmatch(r"[0-9]+", child.name) and child.is_dir()
        ),
        key=lambda child: int(child.name),
    )


def _slugify(text: str, *, max_words: int = 4, max_len: int = 24) -> str:
    """A few lowercase words from ``text``, joined by hyphens, for use in an id.

    Returns ``""`` when ``text`` has no usable words.
    """
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:max_words])[:max_len].strip("-")
