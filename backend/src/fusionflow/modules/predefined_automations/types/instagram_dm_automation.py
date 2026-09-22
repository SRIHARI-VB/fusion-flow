"""`instagram.dm_automation` — auto-reply to an inbound Instagram direct
message when its text matches a configured keyword. Sibling to
`instagram_comment_automation.py`, same wizard-config-to-graph shape, but
triggered by `instagram.message_received` (a DM) instead of
`instagram.comment_received`.

Config shape:
    {
      "trigger_keywords": ["price", "hours"],  # non-empty, required
      "matching_method": "contains",             # exact|contains|starts_with|ends_with
      "reply_text": "Here are our hours...",     # required - the DM sent back
    }

Generated graph shape: trigger (`instagram.message_received`) -> the same
OR-chained `condition.field_compare` sequence
`graph_helpers.build_keyword_condition_chain` builds for the comment
automation -> a single `connector.action` node calling
`instagram.perform_action("send_direct_message", ...)`, replying to
`trigger.from` (the sender's Instagram-scoped id, already the right shape
for the Send API's `recipient.id` - see `instagram/adapter.py::
handle_webhook`'s `_extract_inbound_message` payload).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import build_keyword_condition_chain
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "instagram.dm_automation"

MatchingMethod = Literal["exact", "contains", "starts_with", "ends_with"]

_METHOD_TO_OPERATOR: dict[MatchingMethod, str] = {
    "exact": "eq",
    "contains": "contains",
    "starts_with": "starts_with",
    "ends_with": "ends_with",
}


class InstagramDmAutomationConfig(BaseModel):
    trigger_keywords: list[str] = Field(default_factory=list)  # empty = match everything
    matching_method: MatchingMethod = "contains"
    reply_text: str = Field(min_length=1)


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = InstagramDmAutomationConfig.model_validate(config)
    instance_id = str(connector_instance_id)

    nodes: list[dict[str, Any]] = [
        {
            "id": "trigger",
            "type": "trigger",
            "position": {"x": 0, "y": 0},
            "data": {"nodeType": "instagram.message_received", "label": "DM Received", "config": {}},
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

    operator = _METHOD_TO_OPERATOR[parsed.matching_method]
    chain_nodes, chain_edges = build_keyword_condition_chain(
        trigger_node_id="trigger",
        field_path="trigger.text",
        keywords=parsed.trigger_keywords,
        operator=operator,
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
        label="DM Auto-Reply",
        description="Automatically reply to a direct message when its text matches a keyword.",
        build_graph=build_graph,
    )
)
