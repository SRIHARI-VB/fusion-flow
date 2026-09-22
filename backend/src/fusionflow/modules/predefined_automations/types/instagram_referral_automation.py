"""`instagram.referral_automation` — "Ad/Link Campaign Router": send a
DIFFERENT auto-reply depending on WHICH ad or ig.me shortlink started the
conversation, matched by a substring of Meta's `ref` parameter (a value the
business itself sets when creating the ad/link - see
`workflows/nodes/instagram_referral_received.py`), falling back to a
configured default reply (or a no-op) when none of the configured rules
match.

Config shape:
    {
      "rules": [
        {"ref_match": "summer_sale", "reply_text": "Check out our summer sale!"},
        {"ref_match": "launch", "reply_text": "Welcome to our launch!"},
      ],  # non-empty, required - tried in order, first substring match wins
      "default_reply_text": "Hi! How can we help?",  # optional - sent when no rule's ref_match is found in trigger.ref
    }

Generated graph shape: trigger (`instagram.referral_received`) ->
`graph_helpers.build_branching_condition_chain` OR-chained
`condition.field_compare` sequence over `trigger.ref` (operator `contains`),
each case's `true` handle going to its OWN `connector.action`
("send_direct_message") node - unlike the sibling `build_keyword_condition_
chain` helper (used by `instagram_dm_automation.py`/`instagram_mention_
automation.py`), which converges every match on one shared target, this
automation needs a distinct reply per matched ref.

`build_branching_condition_chain` always appends its own `f"{id_prefix}-
no-match"` `log.noop` terminal for "no case matched", wired from the last
condition's `false` handle. When `default_reply_text` is configured, that
generated node's `data` payload is mutated in place - swapped from a
`log.noop` to a `connector.action` "send_direct_message" node - rather than
trying to fight the helper's edge-wiring: the incoming edge already points
at that same node id, so replacing what the node id *means* is sufficient
and correct. When no default reply is configured, the generated `log.noop`
is left as-is (a real terminal: no reply sent).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import build_branching_condition_chain
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "instagram.referral_automation"


class ReferralRule(BaseModel):
    #: Substring matched against `trigger.ref` (the referral string the
    #: business itself set when creating the ad/ig.me link) - not a full
    #: equality match, since a single ad's `ref` value may carry extra
    #: structure (e.g. campaign + variant) beyond just the identifier a
    #: rule wants to key off of.
    ref_match: str = Field(min_length=1, max_length=200)
    reply_text: str = Field(min_length=1)


class InstagramReferralAutomationConfig(BaseModel):
    rules: list[ReferralRule] = Field(min_length=1)
    #: Sent when no rule's `ref_match` is found in `trigger.ref`. `None`
    #: (the default) means "do nothing" - the chain's generated `log.noop`
    #: terminal is left untouched in that case.
    default_reply_text: str | None = None


def _reply_action_node(node_id: str, x: float, label: str, instance_id: str, reply_text: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "action",
        "position": {"x": x, "y": 0},
        "data": {
            "nodeType": "connector.action",
            "label": label,
            "config": {
                "connector_instance_id": instance_id,
                "action": "send_direct_message",
                "params": {"recipient_id": "{{trigger.from}}", "text": reply_text},
            },
        },
    }


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = InstagramReferralAutomationConfig.model_validate(config)
    instance_id = str(connector_instance_id)

    nodes: list[dict[str, Any]] = [
        {
            "id": "trigger",
            "type": "trigger",
            "position": {"x": 0, "y": 0},
            "data": {"nodeType": "instagram.referral_received", "label": "Ad/Link Referral Received", "config": {}},
        }
    ]

    # One reply action per rule, spaced out vertically so they don't overlap
    # visually on a hand-opened canvas - purely cosmetic, doesn't affect
    # graph semantics.
    action_x = 260 + len(parsed.rules) * 260
    for index, rule in enumerate(parsed.rules):
        nodes.append(
            _reply_action_node(
                node_id=f"action-reply-{index}",
                x=action_x,
                label=f"Reply for {rule.ref_match!r}",
                instance_id=instance_id,
                reply_text=rule.reply_text,
            )
        )

    cases: list[tuple[str, str]] = [
        (rule.ref_match, f"action-reply-{index}") for index, rule in enumerate(parsed.rules)
    ]

    chain_nodes, chain_edges = build_branching_condition_chain(
        trigger_node_id="trigger",
        field_path="trigger.ref",
        operator="contains",
        cases=cases,
        id_prefix="ref-case",
        start_x=260,
    )
    nodes.extend(chain_nodes)
    edges = chain_edges

    if parsed.default_reply_text is not None:
        no_match_id = "ref-case-no-match"
        for node in nodes:
            if node["id"] == no_match_id:
                node["data"] = {
                    "nodeType": "connector.action",
                    "label": "Default Reply",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "send_direct_message",
                        "params": {"recipient_id": "{{trigger.from}}", "text": parsed.default_reply_text},
                    },
                }
                node["type"] = "action"
                break

    return {"nodes": nodes, "edges": edges}


registry.register(
    PredefinedAutomationType(
        automation_type=AUTOMATION_TYPE,
        connector_type_key="instagram",
        label="Ad/Link Campaign Router",
        description="Send a different auto-reply depending on which ad or ig.me shortlink started the conversation.",
        build_graph=build_graph,
    )
)
