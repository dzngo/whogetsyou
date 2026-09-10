"""Explicit ADK 2 graph for Question Bank campaign execution."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from inspect import isawaitable
from collections.abc import AsyncGenerator
from typing import Any, Protocol
import uuid
import logging

from google.adk import Event, Workflow
from google.adk.runners import Runner
from pydantic import PrivateAttr
from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode, JoinNode

from question_bank.adk_app.commands import (
    CancelCampaign,
    GenerateCampaign,
    ResumeCampaign,
    StatusCampaign,
    parse_campaign_command as parse_command,
)
from question_bank.contracts import canonical_data


BATCH_STAGE_NAMES = (
    "campaign_initialization",
    "mission_planner",
    "creative_agent_1",
    "creative_agent_2",
    "creative_agent_3",
    "creative_agent_4",
    "creative_join_and_proposal_persistence",
    "duplicate_preflight",
    "routine_quality_review",
    "uncertainty_review",
    "local_semantic_scan",
    "semantic_llm_chunks",
    "admission_decision",
    "observation_agent",
    "metadata_agent",
    "final_diversity_evidence",
    "persist_and_export",
    "next_batch_or_complete",
)


class WorkflowBackend(Protocol):
    """Application boundary called by visible ADK workflow nodes."""

    def execute(self, stage: str, node_input: Any) -> Any:
        """Execute one named production stage and return structured output."""


def _node(backend: WorkflowBackend, name: str) -> FunctionNode:
    async def execute(node_input):
        result = await asyncio.to_thread(backend.execute, name, node_input)
        return await result if isawaitable(result) else result

    execute.__name__ = name
    # ADK 2.0's node_input binding currently infers a raw JSON-schema dict and
    # then passes it to Pydantic's TypeAdapter when the START input is Content.
    # State binding still forwards a parameter literally named `node_input`,
    # while avoiding that invalid schema-validation path.
    return FunctionNode(func=execute, name=name)


class _BackendJoinNode(JoinNode):
    """Join all creative branches and run the real persistence boundary."""

    def __init__(self, backend: WorkflowBackend) -> None:
        super().__init__(name="creative_join_and_proposal_persistence")
        self._backend = backend

    async def _run_impl(
        self, *, ctx: Context, node_input: Any
    ) -> AsyncGenerator[Event, None]:
        result = await asyncio.to_thread(self._backend.execute, self.name, node_input)
        if isawaitable(result):
            result = await result
        if isinstance(result, Event):
            yield result
        else:
            yield Event(output=result, branch=ctx._invocation_context.branch)


def build_campaign_workflow(backend: WorkflowBackend) -> Workflow:
    """Build the production campaign graph used identically by Web and CLI."""
    nodes = {name: _node(backend, name) for name in BATCH_STAGE_NAMES}
    creative_join = _BackendJoinNode(backend)
    nodes["creative_join_and_proposal_persistence"] = creative_join
    initialization = nodes["campaign_initialization"]
    planner = nodes["mission_planner"]
    creative = tuple(nodes[f"creative_agent_{index}"] for index in range(1, 5))
    after_join = (
        nodes["duplicate_preflight"],
        nodes["routine_quality_review"],
        nodes["uncertainty_review"],
        nodes["local_semantic_scan"],
        nodes["semantic_llm_chunks"],
        nodes["admission_decision"],
        nodes["observation_agent"],
        nodes["metadata_agent"],
        nodes["final_diversity_evidence"],
        nodes["persist_and_export"],
        nodes["next_batch_or_complete"],
    )
    edges: list[tuple[Any, ...]] = [("START", initialization, planner)]
    edges.extend((planner, creative_node, creative_join) for creative_node in creative)
    edges.append((creative_join, *after_join))
    edges.append((nodes["next_batch_or_complete"], {"NEXT_BATCH": planner}))
    return Workflow(
        name="question_bank_campaign",
        description="Generate, evaluate, admit, classify, and export Question Bank proposals.",
        edges=edges,
        max_concurrency=4,
    )


def build_root_workflow(backend: WorkflowBackend) -> Workflow:
    """Build the command router loaded by ADK Web and used by the CLI runner."""
    campaign = build_campaign_workflow(backend)

    def parse_campaign_command(node_input):
        text = _command_text(node_input)
        try:
            command = parse_command(text)
        except ValueError as error:
            return Event(route="ERROR", output={"command": text, "error": str(error)})
        route = {
            GenerateCampaign: "GENERATE",
            StatusCampaign: "STATUS",
            CancelCampaign: "CANCEL",
            ResumeCampaign: "RESUME",
        }[type(command)]
        return Event(route=route, output=canonical_data(asdict(command)))

    parser = FunctionNode(
        func=parse_campaign_command,
        name="parse_campaign_command",
    )
    status = _node(backend, "campaign_status")
    cancel = _node(backend, "campaign_cancel")
    resume = _node(backend, "campaign_resume")
    command_error = _node(backend, "command_error")
    return Workflow(
        name="question_bank_operator",
        description="Operate the Question Bank campaign workflow with explicit commands.",
        edges=[
            ("START", parser),
            (
                parser,
                {
                    "GENERATE": campaign,
                    "STATUS": status,
                    "CANCEL": cancel,
                    "RESUME": resume,
                    "ERROR": command_error,
                },
            ),
            (resume, campaign),
        ],
        max_concurrency=4,
    )


class ServerOwnedWorkflow(Workflow):
    """Keep an ADK Web graph alive when its event client disconnects."""

    _execution_workflow: Workflow = PrivateAttr()

    async def _run_impl(self, *, ctx: Context, node_input: Any):
        command_text = _command_text(ctx.user_content or node_input)
        try:
            command = parse_command(command_text)
        except ValueError:
            async for event in super()._run_impl(ctx=ctx, node_input=node_input):
                yield event
            return
        if isinstance(command, (GenerateCampaign, ResumeCampaign)):
            service = ctx._invocation_context.session_service
            app_name = ctx.session.app_name
            session_id = f"server-campaign-{uuid.uuid4().hex}"
            await service.create_session(
                app_name=app_name,
                user_id=ctx.user_id,
                session_id=session_id,
            )
            runner = Runner(
                agent=self._execution_workflow,
                app_name=app_name,
                session_service=service,
            )

            async def pump() -> None:
                async for _ in runner.run_async(
                    user_id=ctx.user_id,
                    session_id=session_id,
                    new_message=ctx.user_content,
                ):
                    pass

            task = asyncio.create_task(pump(), name=session_id)
            _SERVER_TASKS.add(task)
            task.add_done_callback(_finish_server_task)
            yield Event(output={
                "accepted": True,
                "campaign_id": command.campaign_id,
                "execution_session_id": session_id,
            })
            return
        async for event in super()._run_impl(ctx=ctx, node_input=node_input):
            yield event


_SERVER_TASKS: set[asyncio.Task] = set()


def _finish_server_task(task: asyncio.Task) -> None:
    _SERVER_TASKS.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logging.getLogger(__name__).error(
            "server-owned campaign failed", exc_info=error
        )


async def wait_for_server_tasks() -> None:
    """Wait until server-owned campaign invocations finish (tests/shutdown)."""
    while _SERVER_TASKS:
        await asyncio.gather(*tuple(_SERVER_TASKS), return_exceptions=True)


def build_web_root_agent(backend: WorkflowBackend) -> Workflow:
    """Wrap the same operator graph in a server-owned execution boundary."""
    root = build_root_workflow(backend)
    web = ServerOwnedWorkflow(
        name=root.name,
        description=root.description,
        edges=root.edges,
        max_concurrency=root.max_concurrency,
    )
    web._execution_workflow = build_root_workflow(backend)
    return web


def _command_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    text = getattr(value, "text", None)
    if isinstance(text, str):
        return text
    parts = getattr(value, "parts", None)
    if parts:
        return "".join(str(getattr(part, "text", "")) for part in parts)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        content = value.get("content")
        if isinstance(content, str):
            return content
    raise ValueError("command input must contain text")
