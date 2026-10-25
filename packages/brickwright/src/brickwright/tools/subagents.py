"""Dispatch parallel, isolated subagents."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor

from pydantic import BaseModel, ConfigDict
from rich.console import Console

from ..config import Config
from ..record import Record, Usage
from .schemas import SubagentTask


class SubagentResult(BaseModel):
    """A subagent's outcome: whether it handed work back, and its verdict on that work."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    text: str = ""
    usage: Usage = Usage()
    record_id: str = ""
    reason: str = ""
    valid: bool | None = None  # last validation outcome; None if it never validated
    failed_checks: list[str] = []  # which checks were failing when it stopped
    finalized: bool = False  # whether the subagent wrapped up with ``finalize``


def dispatch_subagents(
    record: Record, tasks: list[SubagentTask], config: Config
) -> list[SubagentResult]:
    """Run ``tasks`` concurrently and return results in task order."""
    with ThreadPoolExecutor(max_workers=config.max_parallel_subagents) as pool:
        futures = [pool.submit(_run_subagent, record, t, config) for t in tasks]
    return [_collect(f) for f in futures]


def _collect(future: Future[SubagentResult]) -> SubagentResult:
    try:
        return future.result()
    except Exception as exc:
        return SubagentResult(ok=False, reason=f"subagent crashed: {exc}")


def _run_subagent(record: Record, task: SubagentTask, config: Config) -> SubagentResult:
    """Run one subagent to completion and return its text result."""
    worker_config = _worker_config(record, config, task.tier)
    record = Record.create(worker_config, prompt=task.prompt)
    try:
        # deferred: driver imports tools
        from ..driver.loop import run_agent
        from ..driver.narration import Narrator

        report = run_agent(
            record, worker_config, narrator=Narrator(Console(quiet=True))
        )
    except Exception as exc:  # a subagent crash must not take down its siblings
        return SubagentResult(
            ok=False, record_id=record.id, reason=f"subagent run failed: {exc}"
        )
    text = report.final_text or ""
    validation = report.report
    return SubagentResult(
        ok=bool(text),
        text=text,
        usage=report.usage,
        record_id=record.id,
        reason=""
        if text
        else "subagent produced no final answer (turn/cost budget likely hit)",
        valid=None if validation is None else validation.ok,
        failed_checks=[] if validation is None else validation.failed_checks,
        finalized=report.done,
    )


def _worker_config(record: Record, config: Config, tier: str | None) -> Config:
    """Derive the config a subagent runs under."""
    return config.model_copy(
        update={
            "records_dir": record.subagents_dir,
            "model": _resolve_subagent_model(config, tier),
            "subagents_enabled": False,
            "is_subagent": True,
            "max_turns": config.subagent_max_turns,
            "max_cost": config.subagent_max_cost,
        }
    )


def _resolve_subagent_model(config: Config, tier: str | None) -> str | None:
    """Resolve a task's tier to a model id for the main model's provider.

    An omitted tier, an unknown provider, or a tier absent from the provider's
    map all resolve to the main model.
    """
    if tier is None or config.model is None:
        return config.model
    import litellm

    try:
        _, provider, *_ = litellm.get_llm_provider(config.model)
    except litellm.exceptions.BadRequestError:
        return config.model
    tiers = config.subagent_tiers.get(provider)
    if not tiers or tier not in tiers:
        return config.model
    return tiers[tier]
