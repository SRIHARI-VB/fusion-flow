"""`instagram.reaction_automation` — auto-send a DM follow-up when someone
reacts to a message in a DM conversation with this Instagram account with a
specific reaction type (e.g. "love"). Sibling to `instagram_dm_automation.py`,
same wizard-config-to-graph shape, but triggered by
`instagram.message_reaction_received` instead of `instagram.message_received`,
and matching a single configured reaction type instead of free-text keywords
against message text.

Config shape:
    {
      "reaction_type": "love",                    # one of the fixed reaction types
      "reply_text": "Thanks for the love!",        # required - the DM sent back
    }

Generated graph shape: trigger (`instagram.message_reaction_received`) -> a
single-element `graph_helpers.build_keyword_condition_chain` comparing
`trigger.reaction` against the configured `reaction_type` -> a single
`connector.action` node calling `instagram.perform_action(
"send_direct_message", ...)`, replying to `trigger.from` (the reactor's
Instagram-scoped id, already the right shape for the Send API's
`recipient.id`).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import build_keyword_condition_chain
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "instagram.reaction_automation"

ReactionType = Literal["love", "like", "laugh", "wow", "sad", "angry"]


class InstagramReactionAutomationConfig(BaseModel):
    reaction_type: ReactionType = "love"
    reply_text: str = Field(min_length=1)


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = InstagramReactionAutomationConfig.model_validate(config)
    instance_id = str(connector_instance_id)

    nodes: list[dict[str, Any]] = [
        {
            "id": "trigger",
            "type": "trigger",
            "position": {"x": 0, "y": 0},
            "data": {
                "nodeType": "instagram.message_reaction_received",
                "label": "Message Reaction Received",
                "config": {},
            },
        },
        {
            "id": "action-reply",
            "type": "action",
            "position": {"x": 780, "y": 0},
            "data": {
                "nodeType": "connector.action",
                "label": "Reply via DM",
                "config": {
                    "connector_instance_id": instance_id,
                    "action": "send_direct_message",
                    "params": {"recipient_id": "{{trigger.from}}", "text": parsed.reply_text},
                },
            },
        },
    ]

    chain_nodes, chain_edges = build_keyword_condition_chain(
        trigger_node_id="trigger",
        field_path="trigger.reaction",
        keywords=[parsed.reaction_type],
        operator="eq",
        on_match_target_id="action-reply",
        start_x=260,
    )
    nodes.extend(chain_nodes)
    edges = chain_edges

    return {"nodes": nodes, "edges": edges}


registry.register(
    PredefinedAutomationType(
        automation_type=AUTOMATION_TYPE,
        connector_type_key="instagram",
        label="Reaction Follow-Up",
        description="Automatically send a DM follow-up when someone reacts to a message with a specific reaction.",
        build_graph=build_graph,
    )
)
