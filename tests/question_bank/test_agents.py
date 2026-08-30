import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from question_bank.agents import (
    AgentRunner,
    ModelRouting,
    ProposalEvaluation,
    ProposalProduction,
    ReleaseRevalidator,
    TaxonomyAgentGroup,
    ThemeClassifier,
)
from question_bank.contracts import CreativeConcept, EnrichmentBrief, QuestionLevel
from question_bank.core import AdmissionDecider, QuestionBank
from question_bank.modules import QuestionBankNeighborIndex, TaxonomyRegistry
from tests.question_bank.test_core import accepted_package


class ScriptedLLM:
    def __init__(self, preset: str, calls: list[dict[str, Any]]) -> None:
        self.preset = preset
        self.model_name = preset
        self.calls = calls

    def parse_structured(self, messages, response_model):
        role = messages[0]["content"].split("ROLE:", 1)[1].splitlines()[0].strip()
        self.calls.append({"role": role, "preset": self.preset, "messages": messages})
        if response_model.__name__ == "ConceptBatchOutput":
            return response_model(
                concepts=[
                    {
                        "summary": f"{role} concept",
                        "aspect_id": "self_understanding",
                        "perspective_id": "restoration",
                        "semantic_scenario": f"{role} scenario",
                        "answer_space": f"{role} answer",
                        "taxonomy_status": "approved",
                    }
                ]
            )
        if response_model.__name__ == "ConceptDedupOutput":
            payload = json.loads(messages[1]["content"])
            return response_model(
                keep_concept_ids=[concept["concept_id"] for concept in payload["concepts"]]
            )
        if response_model.__name__ == "ProposalOutput":
            payload = json.loads(messages[1]["content"])
            scout_role = payload["concept"]["scout_role"]
            return response_model(
                question="What small ritual helps you feel like yourself again?",
                wording_pattern=f"open-{scout_role}",
            )
        if response_model.__name__ == "JudgmentOutput":
            payload = json.loads(messages[1]["content"])
            facets = {}
            if role == "ontology_judge":
                proposal = payload["proposal"]
                facets = {
                    "aspect_id": proposal["aspect_id"],
                    "perspective_id": proposal["perspective_id"],
                    "semantic_scenario": proposal["semantic_scenario"],
                    "answer_space": proposal["answer_space"],
                    "wording_pattern": proposal["wording_pattern"],
                }
            return response_model(passed=True, uncertain=False, reason_codes=["pass"], facet_values=facets)
        if response_model.__name__ == "RelationOutput":
            return response_model(
                semantic_repeat=False,
                uncertain=False,
                reason_codes=["distinct"],
                scenario_relation="different",
                perspective_relation="same",
                answer_space_relation="different",
                aspect_relation="same",
                wording_pattern_relation="different",
            )
        if response_model.__name__ == "ChallengeOutput":
            return response_model(complete=True, uncertainty_reason_codes=[])
        if response_model.__name__ == "ThemeOutput":
            return response_model(memberships=["identity"], uncertain=False, reason_codes=["direct_fit"])
        if response_model.__name__ == "TaxonomyCandidateOutput":
            return response_model(
                facet="aspect",
                label="Restoration",
                definition="Ways people return to a settled sense of self",
                aliases=[],
                exclusions=["generic relaxation"],
            )
        raise AssertionError(response_model)

    def complete_text(self, messages):
        raise AssertionError("Only structured output is permitted")


class AgentSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.calls: list[dict[str, Any]] = []
        self.runner = AgentRunner(
            Path(self.tempdir.name) / "workflow.sqlite3",
            llm_factory=lambda preset: ScriptedLLM(preset, self.calls),
        )
        self.brief = EnrichmentBrief(
            "brief-1",
            "brief-key-1",
            QuestionLevel.DEEP,
            {
                "region_id": "region-1",
                "theme_id": "identity",
                "aspect_id": "self_understanding",
                "perspective_id": "restoration",
            },
            "taxonomy-v1",
            "snapshot-empty",
            concepts_per_scout=1,
        )

    def tearDown(self) -> None:
        self.runner.close()
        self.tempdir.cleanup()

    def test_model_routing_uses_exact_requested_creative_model(self) -> None:
        routing = ModelRouting()
        for role in (*routing.SCOUT_ROLES, "composer", "taxonomy_candidate_author"):
            self.assertEqual("gemini-3.5-flash-high", routing.preset_for(role))
        for role in ("clarity_openness_judge", "evidence_challenger", "theme_classifier"):
            self.assertEqual("gpt-5.4-mini-high", routing.preset_for(role))

    def test_proposal_group_runs_four_isolated_scouts_and_one_composer_each(self) -> None:
        batch = ProposalProduction(self.runner).propose(self.brief)
        self.assertEqual(4, len(batch.proposals))
        scout_calls = [call for call in self.calls if call["role"] in ModelRouting.SCOUT_ROLES]
        composer_calls = [call for call in self.calls if call["role"] == "composer"]
        self.assertEqual(4, len(scout_calls))
        self.assertEqual(4, len(composer_calls))
        self.assertTrue(all(call["preset"] == "gemini-3.5-flash-high" for call in scout_calls + composer_calls))
        self.assertTrue(all("theme" not in str(call["messages"]).lower() for call in scout_calls + composer_calls))

    def test_evaluation_uses_four_independent_gpt_judges_and_challenger(self) -> None:
        proposal = ProposalProduction(self.runner).propose(self.brief).proposals[0]
        bank = QuestionBank(Path(self.tempdir.name) / "bank.sqlite3")
        snapshot = bank.snapshot({"revision_ids": []})
        result = ProposalEvaluation(
            self.runner,
            QuestionBankNeighborIndex(bank),
            AdmissionDecider(),
        ).evaluate(
            proposal,
            {
                "snapshot_id": snapshot.snapshot_id,
                "taxonomy_definitions": {
                    "version_id": "taxonomy-v1",
                    "aspects": [{"id": "self_understanding"}],
                    "perspectives": [{"id": "restoration"}],
                },
            },
        )
        self.assertEqual("accept", result.outcome.decision.value)
        judge_roles = {judgment.role for judgment in result.evidence.judgments}
        self.assertEqual(set(ModelRouting.EVALUATION_ROLES), judge_roles)
        evaluation_calls = [call for call in self.calls if call["role"] in (*ModelRouting.EVALUATION_ROLES, "evidence_challenger")]
        self.assertTrue(all(call["preset"] == "gpt-5.4-mini-high" for call in evaluation_calls))
        bank.close()

    def test_theme_is_assigned_only_after_acceptance(self) -> None:
        proposal = ProposalProduction(self.runner).propose(self.brief).proposals[0]
        classification = ThemeClassifier(self.runner).classify(proposal, ["identity", "wellbeing"])
        self.assertTrue(classification.resolved)
        self.assertEqual(["identity"], classification.memberships)
        self.assertEqual(2, len(classification.classifier_invocation_ids))

    def test_taxonomy_group_uses_gemini_author_and_independent_gpt_checks(self) -> None:
        registry = TaxonomyRegistry(Path(self.tempdir.name) / "taxonomy.sqlite3")
        concepts = [
            CreativeConcept(
                f"c-{index}", f"brief-{index}", "aspect_scout", f"support {index}",
                "unclassified", "restoration", f"scenario-{index % 3}", f"answer-{index % 2}", "unclassified",
            )
            for index in range(6)
        ]
        _, decision = TaxonomyAgentGroup(self.runner, registry).evaluate_gap(concepts, {"aspects": []}, {"regions": []})
        self.assertEqual("accept", decision.decision.value)
        author = [call for call in self.calls if call["role"] == "taxonomy_candidate_author"]
        judges = [call for call in self.calls if call["role"].startswith("taxonomy_") and call["role"] != "taxonomy_candidate_author"]
        self.assertEqual("gemini-3.5-flash-high", author[0]["preset"])
        self.assertEqual(9, len(judges))
        self.assertTrue(all(call["preset"] == "gpt-5.4-mini-high" for call in judges))
        registry.close()

    def test_release_revalidator_runs_fresh_quality_and_relation_agents(self) -> None:
        bank = QuestionBank(Path(self.tempdir.name) / "release-bank.sqlite3")
        first_package = accepted_package("release-admit-1")
        first = bank.admit(first_package)
        second_package = accepted_package("release-admit-2")
        second_package.proposal.proposal_id = "proposal-release-2"
        second_package.proposal.text = "Which place helps you reset after a demanding day?"
        second_package.proposal.semantic_scenario = "recovering in a personally calming place"
        second_package.proposal.answer_space = "a personally calming place"
        second_package.evidence.evidence_id = "evidence-release-2"
        second_package.evidence.proposal_id = second_package.proposal.proposal_id
        second_package.evidence.resolved_facets["semantic_scenario"] = second_package.proposal.semantic_scenario
        second_package.evidence.resolved_facets["answer_space"] = second_package.proposal.answer_space
        second_package.outcome.outcome_id = "outcome-release-2"
        second_package.outcome.proposal_id = second_package.proposal.proposal_id
        second_package.outcome.evidence_id = second_package.evidence.evidence_id
        second_package.theme_classification.classification_id = "themes-release-2"
        second_package.theme_classification.proposal_id = second_package.proposal.proposal_id
        second = bank.admit(second_package)
        snapshot = bank.snapshot({"revision_ids": [first.revision_id, second.revision_id]})
        gates = ReleaseRevalidator(
            self.runner,
            QuestionBankNeighborIndex(bank),
            lambda version_id: {
                "version_id": version_id,
                "aspects": [{"id": "self_understanding"}],
                "perspectives": [{"id": "restoration"}],
            },
        ).revalidate(
            [first, second],
            [first_package, second_package],
            snapshot.snapshot_id,
            {"taxonomy_version_id": "taxonomy-v1", "policy_versions": {"quality": "v1"}},
        )
        self.assertTrue(all(gates.values()))
        relation_calls = [call for call in self.calls if call["role"] == "neighbor_relation_judge"]
        self.assertEqual(1, len(relation_calls))
        bank.close()


if __name__ == "__main__":
    unittest.main()
