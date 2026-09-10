from __future__ import annotations

import unittest
from decimal import Decimal

from question_bank.adk_app.commands import (
    CancelCampaign,
    GenerateCampaign,
    ResumeCampaign,
    StatusCampaign,
    parse_campaign_command,
)


class AdkCampaignCommandTests(unittest.TestCase):
    def test_generate_command_is_explicit_spending_authorization(self) -> None:
        command = parse_campaign_command(
            "generate campaign=v21-lite-100 proposal_target=100 level=shallow "
            "bank=v2.1 budget_usd=6"
        )

        self.assertEqual(
            GenerateCampaign(
                campaign_id="v21-lite-100",
                proposal_target=100,
                level="shallow",
                bank="v2.1",
                budget_usd=Decimal("6.000000"),
            ),
            command,
        )

    def test_generate_rejects_ambiguous_or_unbounded_work(self) -> None:
        invalid = (
            "generate proposal_target=100 level=shallow bank=v2.1",
            "generate campaign=x proposal_target=101 level=shallow bank=v2.1 budget_usd=6",
            "generate campaign=x proposal_target=100 level=shallow bank=v2.1 budget_usd=-1",
            "generate campaign=x target=100 level=shallow bank=v2.1 budget_usd=6",
        )
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_campaign_command(text)

    def test_control_commands_are_deterministic(self) -> None:
        self.assertEqual(
            StatusCampaign(campaign_id="campaign-a"),
            parse_campaign_command("status campaign=campaign-a"),
        )
        self.assertEqual(
            CancelCampaign(campaign_id="campaign-a"),
            parse_campaign_command("cancel campaign=campaign-a"),
        )
        self.assertEqual(
            ResumeCampaign(campaign_id="campaign-a", budget_usd=Decimal("2.000000")),
            parse_campaign_command("resume campaign=campaign-a budget_usd=2"),
        )


if __name__ == "__main__":
    unittest.main()
