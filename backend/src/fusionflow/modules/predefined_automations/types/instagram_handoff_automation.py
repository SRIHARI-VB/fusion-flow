"""`instagram.handoff_automation` — Instagram "Human Handoff": when an
inbound DM's text matches a configured escalation keyword (e.g. "talk to a
human", "agent"), send an acknowledgement DM and then mark the run's
originating Unified Inbox conversation as needing a human, so no other
predefined automation replies to it again until an agent manually resumes
it from the Inbox (`inbox.pause_automation` — see
`workflows/nodes/inbox_pause_automation.py`).

Config shape:
    {
      "trigger_keywords": ["talk to a human", "agent"],  # non-empty, required
      "matching_method": "contains",                       # exact|contains|starts_with|ends_with
      "ack_text": "Connecting you to our team...",          # required - the DM sent back
    }

Generated graph shape: trigger (`instagram.message_received`) -> the same
OR-chained `condition.field_compare` sequence
`graph_helpers.build_keyword_condition_chain` builds for the other Instagram
DM/comment automations -> two `connector.action`/`inbox.pause_automation`
nodes chained sequentially (ack DM first, then pause) — same
"unrestricted action nodes chain via plain default-handle edges" pattern
`instagram_comment_automation.py::build_graph` uses for its multi-action
chain.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import build_keyword_condition_chain
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "instagram.handoff_automation"

MatchingMethod = Literal["exact", "contains", "starts_with", "ends_with"]

_METHOD_TO_OPERATOR: dict[MatchingMethod, str] = {
    "exact": "eq",
    "contains": "contains",
    "starts_with": "starts_with",
    "ends_with": "ends_with",
}


class InstagramHandoffAutomationConfig(BaseModel):
    trigger_keywords: list[str] = Field(min_length=1)
    matching_method: MatchingMethod = "contains"
    ack_text: str = Field(min_length=1)


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = InstagramHandoffAutomationConfig.model_validate(config)
    instance_id = str(connector_instance_id)

    nodes: list[dict[str, Any]] = [
        {
            "id": "trigger",
            "type": "trigger",
            "position": {"x": 0, "y": 0},
            "data": {"nodeType": "instagram.message_received", "label": "DM Received", "config": {}},
        }
    ]
    edges: list[dict[str, Any]] = []
    x = 780  # condition chain occupies x=260..~780 depending on keyword count; actions start past it

    action_nodes: list[dict[str, Any]] = [
        {
            "id": "action-ack",
            "type": "action",
            "data": {
                "nodeType": "connector.action",
                "label": "Send Acknowledgement DM",
                "config": {
                    "connector_instance_id": instance_id,
                    "action": "send_direct_message",
                    "params": {"recipient_id": "{{trigger.from}}", "text": parsed.ack_text},
                },
            },
        },
        {
            "id": "action-pause",
            "type": "action",
            "data": {
                "nodeType": "inbox.pause_automation",
                "label": "Pause Automation for This Conversation",
                "config": {"connector_instance_id": instance_id},
            },
        },
    ]

    # Action nodes are unrestricted (no declared output handles), so they
    # chain sequentially via plain default-handle edges - only the FIRST
    # one is the condition chain's convergence target - same pattern as
    # `instagram_comment_automation.py::build_graph`.
    for offset, action_node in enumerate(action_nodes):
        action_node["position"] = {"x": x + offset * 260, "y": 0}
        nodes.append(action_node)
        if offset > 0:
            edges.append(
                {
                    "id": f"e-{action_nodes[offset - 1]['id']}-{action_node['id']}",
                    "source": action_nodes[offset - 1]["id"],
                    "target": action_node["id"],
                }
            )

    operator = _METHOD_TO_OPERATOR[parsed.matching_method]
    chain_nodes, chain_edges = build_keyword_condition_chain(
        trigger_node_id="trigger",
        field_path="trigger.text",
        keywords=parsed.trigger_keywords,
        operator=operator,
        on_match_target_id=action_nodes[0]["id"],
        start_x=260,
    )
    nodes.extend(chain_nodes)
    edges.extend(chain_edges)

    return {"nodes": nodes, "edges": edges}


registry.register(
    PredefinedAutomationType(
        automation_type=AUTOMATION_TYPE,
        connector_type_key="instagram",
        label="Human Handoff",
        description=(
            "Send an acknowledgement and pause automated replies for this conversation when a "
            "customer asks for a human — until an agent resumes it from the Inbox."
        ),
        build_graph=build_graph,
    )
)
