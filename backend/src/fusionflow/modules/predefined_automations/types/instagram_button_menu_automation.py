"""`instagram.button_menu_automation` — reply to a keyword-matched inbound
Instagram DM with a text prompt plus up to 3 tappable buttons, then reply
again with each button's own configured text when that button is tapped.

Config shape:
    {
      "trigger_keywords": ["menu", "help"],       # non-empty, required
      "matching_method": "contains",                # exact|contains|starts_with|ends_with
      "menu_text": "How can we help?",              # required - the prompt sent with the buttons
      "buttons": [                                   # 1-3 entries, required
        {"title": "Pricing", "reply_text": "Our pricing is..."},
        {"title": "Support", "reply_text": "Contact support at..."},
      ],
    }

Generated graph shape: TWO independent trigger chains in one graph (see
`workflows/engine/outbox_poller.py::_rebuild_triggers`, which registers a
`WorkflowTrigger` row for every trigger-kind node in the graph, not just
the first one):

  Chain A - send the menu: trigger `instagram.message_received` ->
  `graph_helpers.build_keyword_condition_chain` OR-chain on `trigger.text`
  -> a single `connector.action` node calling `instagram.perform_action(
  "send_button_template", ...)`, addressed to `trigger.from`, one button
  per configured `ButtonConfig` with payload `f"BTN_{i}"`.

  Chain B - handle a tap: trigger `instagram.postback_received` ->
  `graph_helpers.build_branching_condition_chain` on `trigger.payload`
  (`eq` against each `BTN_{i}` payload) -> one `connector.action` node PER
  BUTTON calling `instagram.perform_action("send_direct_message", ...)`
  with that button's own `reply_text`, addressed to `trigger.from` (the
  tapper's Instagram-scoped id - see `instagram_postback_received.py`'s
  output schema).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import (
    build_branching_condition_chain,
    build_keyword_condition_chain,
)
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "instagram.button_menu_automation"

MatchingMethod = Literal["exact", "contains", "starts_with", "ends_with"]

_METHOD_TO_OPERATOR: dict[MatchingMethod, str] = {
    "exact": "eq",
    "contains": "contains",
    "starts_with": "starts_with",
    "ends_with": "ends_with",
}


class ButtonConfig(BaseModel):
    title: str = Field(min_length=1, max_length=20)  # Meta's button title length limit
    reply_text: str = Field(min_length=1)


class InstagramButtonMenuAutomationConfig(BaseModel):
    trigger_keywords: list[str] = Field(default_factory=list)  # empty = match everything
    matching_method: MatchingMethod = "contains"
    menu_text: str = Field(min_length=1)
    buttons: list[ButtonConfig] = Field(min_length=1, max_length=3)


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = InstagramButtonMenuAutomationConfig.model_validate(config)
    instance_id = str(connector_instance_id)

    nodes: list[dict[str, Any]] = [
        {
            "id": "trigger-message",
            "type": "trigger",
            "position": {"x": 0, "y": 0},
            "data": {"nodeType": "instagram.message_received", "label": "DM Received", "config": {}},
        },
        {
            "id": "trigger-postback",
            "type": "trigger",
            "position": {"x": 0, "y": 300},
            "data": {"nodeType": "instagram.postback_received", "label": "Button Tapped", "config": {}},
        },
        {
            "id": "action-send-menu",
            "type": "action",
            "position": {"x": 780, "y": 0},
            "data": {
                "nodeType": "connector.action",
                "label": "Send Menu",
                "config": {
                    "connector_instance_id": instance_id,
                    "action": "send_button_template",
                    "params": {
                        "recipient_id": "{{trigger.from}}",
                        "text": parsed.menu_text,
                        "buttons": [
                            {"title": button.title, "payload": f"BTN_{index}"}
                            for index, button in enumerate(parsed.buttons)
                        ],
                    },
                },
            },
        },
    ]

    for index, button in enumerate(parsed.buttons):
        nodes.append(
            {
                "id": f"action-btn-{index}",
                "type": "action",
                "position": {"x": 780 + index * 260, "y": 300},
                "data": {
                    "nodeType": "connector.action",
                    "label": f"Reply: {button.title}",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "send_direct_message",
                        "params": {"recipient_id": "{{trigger.from}}", "text": button.reply_text},
                    },
                },
            }
        )

    operator = _METHOD_TO_OPERATOR[parsed.matching_method]
    menu_chain_nodes, menu_chain_edges = build_keyword_condition_chain(
        trigger_node_id="trigger-message",
        field_path="trigger.text",
        keywords=parsed.trigger_keywords,
        operator=operator,
        on_match_target_id="action-send-menu",
        id_prefix="menu-match",
        start_x=260,
    )
    nodes.extend(menu_chain_nodes)
    edges = list(menu_chain_edges)

    btn_chain_nodes, btn_chain_edges = build_branching_condition_chain(
        trigger_node_id="trigger-postback",
        field_path="trigger.payload",
        operator="eq",
        cases=[(f"BTN_{index}", f"action-btn-{index}") for index in range(len(parsed.buttons))],
        id_prefix="btn-match",
        start_x=260,
    )
    nodes.extend(btn_chain_nodes)
    edges.extend(btn_chain_edges)

    return {"nodes": nodes, "edges": edges}


registry.register(
    PredefinedAutomationType(
        automation_type=AUTOMATION_TYPE,
        connector_type_key="instagram",
        label="Button Menu",
        description=(
            "Reply to a keyword with a menu of tappable buttons, each sending its own "
            "follow-up reply when tapped."
        ),
        build_graph=build_graph,
    )
)
