from __future__ import annotations

import asyncio
import threading
import unittest

from google.adk import Event
from google.adk.runners import InMemoryRunner
from google.genai import types

from question_bank.adk_app.workflow import (
    BATCH_STAGE_NAMES,
    build_campaign_workflow,
    build_root_workflow,
    build_web_root_agent,
    wait_for_server_tasks,
)


class RecordingBackend:
    def execute(self, stage: str, node_input):
        return Event(output={"stage": stage, "input": node_input})


class BarrierBackend(RecordingBackend):
    def __init__(self) -> None:
        self.barrier = threading.Barrier(4, timeout=2)

    def execute(self, stage: str, node_input):
        if stage.startswith("creative_agent_"):
            self.barrier.wait()
        return super().execute(stage, node_input)


class DisconnectBackend:
    def __init__(self) -> None:
        self.completed = threading.Event()

    def execute(self, stage: str, node_input):
        if stage == "campaign_initialization":
            return Event(output={"campaign_id": "detached", "execution_token": "owner"})
        if stage == "mission_planner":
            threading.Event().wait(0.15)
        if stage == "next_batch_or_complete":
            self.completed.set()
        return Event(output={"campaign_id": "detached", "execution_token": "owner"})


class AdkWorkflowTopologyTests(unittest.TestCase):
    def test_campaign_graph_exposes_every_production_component(self) -> None:
        workflow = build_campaign_workflow(RecordingBackend())

        node_names = {node.name for node in workflow.graph.nodes}

        self.assertEqual(set(BATCH_STAGE_NAMES) | {"__START__"}, node_names)
        self.assertEqual(4, workflow.max_concurrency)

    def test_web_and_cli_root_route_to_the_same_campaign_workflow(self) -> None:
        root = build_root_workflow(RecordingBackend())

        node_names = {node.name for node in root.graph.nodes}

        self.assertEqual(
            {
                "__START__",
                "parse_campaign_command",
                "question_bank_campaign",
                "campaign_status",
                "campaign_cancel",
                "campaign_resume",
                "command_error",
            },
            node_names,
        )

    def test_root_command_executes_through_the_adk_runner(self) -> None:
        backend = RecordingBackend()

        async def run() -> list[Event]:
            runner = InMemoryRunner(
                agent=build_root_workflow(backend), app_name="question-bank-test"
            )
            await runner.session_service.create_session(
                app_name="question-bank-test", user_id="operator", session_id="session"
            )
            return [
                event
                async for event in runner.run_async(
                    user_id="operator",
                    session_id="session",
                    new_message=types.Content(
                        role="user", parts=[types.Part(text="status campaign=sample")]
                    ),
                )
            ]

        events = asyncio.run(run())

        self.assertTrue(any(event.output and event.output.get("stage") == "campaign_status" for event in events))

    def test_only_creative_fanout_can_reach_four_way_concurrency(self) -> None:
        async def run() -> None:
            runner = InMemoryRunner(
                agent=build_campaign_workflow(BarrierBackend()),
                app_name="question-bank-concurrency-test",
            )
            await runner.session_service.create_session(
                app_name="question-bank-concurrency-test",
                user_id="operator", session_id="session",
            )
            async for _ in runner.run_async(
                user_id="operator", session_id="session",
                new_message=types.Content(
                    role="user", parts=[types.Part(text="campaign")]
                ),
            ):
                pass

        asyncio.run(run())

    def test_web_campaign_survives_event_client_disconnect(self) -> None:
        backend = DisconnectBackend()

        async def run() -> None:
            runner = InMemoryRunner(
                agent=build_web_root_agent(backend),
                app_name="question-bank-disconnect-test",
            )
            await runner.session_service.create_session(
                app_name="question-bank-disconnect-test",
                user_id="operator", session_id="session",
            )
            events = runner.run_async(
                user_id="operator", session_id="session",
                new_message=types.Content(
                    role="user", parts=[types.Part(text=(
                        "generate campaign=detached proposal_target=20 "
                        "level=shallow bank=v2.1 budget_usd=1"
                    ))],
                ),
            )
            accepted = None
            async for event in events:
                if event.output and event.output.get("accepted"):
                    accepted = event.output
                    break
            self.assertIsNotNone(accepted)
            await events.aclose()
            await asyncio.wait_for(wait_for_server_tasks(), timeout=2)
            completed = backend.completed.is_set()
            self.assertTrue(completed)
            session = await runner.session_service.get_session(
                app_name="question-bank-disconnect-test",
                user_id="operator",
                session_id=accepted["execution_session_id"],
            )
            self.assertIsNotNone(session)
            paths = {
                event.node_info.path for event in session.events if event.node_info
            }
            for stage in BATCH_STAGE_NAMES:
                self.assertTrue(any(f"/{stage}@" in path for path in paths), stage)

        asyncio.run(run())

    def test_web_invalid_command_uses_structured_error_route(self) -> None:
        async def run() -> list[Event]:
            runner = InMemoryRunner(
                agent=build_web_root_agent(RecordingBackend()),
                app_name="question-bank-web-error-test",
            )
            await runner.session_service.create_session(
                app_name="question-bank-web-error-test",
                user_id="operator", session_id="session",
            )
            return [event async for event in runner.run_async(
                user_id="operator", session_id="session",
                new_message=types.Content(
                    role="user", parts=[types.Part(text="bogus")]
                ),
            )]

        events = asyncio.run(run())
        self.assertTrue(any(
            event.output and event.output.get("stage") == "command_error"
            for event in events
        ))


if __name__ == "__main__":
    unittest.main()
