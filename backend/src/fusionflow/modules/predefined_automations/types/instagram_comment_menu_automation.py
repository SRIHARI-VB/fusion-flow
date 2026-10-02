"""`instagram.comment_menu_automation` — a comment-triggered "lead capture"
flow: reply (publicly and/or via a text-only Private Reply) when a comment
on a scoped post/reel matches a keyword, then hand off to a second,
DM-triggered keyword menu where each option replies with its own text (and
optional media), except one designated option which creates a support
ticket instead.

Why two trigger chains, not one message: Meta's Send API can only address
a `recipient.id` (needed for button templates, media, or any rich
content) inside an already-open 24h messaging window - a first-time
commenter has no such window. The one mechanism that *can* reach a
brand-new commenter is a Private Reply (`recipient.comment_id`), and per
`instagram/adapter.py::send_private_reply`'s own docstring that channel is
text-only on Meta's side. So the rich, menu-driven experience (and the
ticket-creating option) can only begin once the commenter replies to that
first DM - which opens a normal messaging window and fires
`instagram.message_received` for Chain B. This is the same reason real
"comment X and I'll DM you" growth tools always do a plain-text nudge
first and the richer experience second, not a platform limitation unique
to this app.

Config shape:
    {
      "trigger_keywords": ["demo"],                  # [] = match every comment
      "matching_method": "contains",                   # exact|contains|starts_with|ends_with
      "media_ids": ["1784...5"],                       # [] = every post/reel on the account
      "reply_comment_text": "Check your DMs!" | null,  # public reply; null/empty disables it
      "private_reply_text": "Thanks! Reply SERVICES, PRICING, or DEMO to learn more.",
      "menu_matching_method": "contains",
      "menu_options": [                                 # plain-text/media reply options
        {"keyword": "services", "reply_text": "...", "media_url": null, "media_type": null},
        {"keyword": "pricing", "reply_text": "...", "media_url": "https://...", "media_type": "image"},
      ],
      "ticket_keyword": "demo",                         # the one option that creates a ticket instead
      "ticket_subject": "Instagram demo request from {{trigger.from}}",
      "ticket_confirmation_text": "Thanks! We've logged this and our team will reach out.",
    }

Generated graph shape:

  Chain A (comment -> private reply): trigger `instagram.comment_received`
  -> `graph_helpers.build_scoped_keyword_condition_chain` (post/reel scope,
  then keyword) -> optional `connector.action` "Reply to Comment" ->
  `connector.action` "Send Private Reply" (always present - the one
  required action, since this automation's whole point is to start that
  DM).

  Chain B (DM -> menu/ticket): trigger `instagram.message_received` ->
  `graph_helpers.build_branching_condition_chain` on `trigger.text`, one
  case per `menu_options` entry plus one for `ticket_keyword` -> each
  `menu_options` case: `connector.action` "Send DM" (text), optionally
  chained into `connector.action` "Send Media" when that option has a
  `media_url` - same per-option media chaining as
  `instagram_button_menu_automation.py`'s per-button media node. The
  ticket case: `create_ticket` (no `customer_id` - Instagram comments/DMs
  don't link to a `Customer` record today, see that node's own docstring
  for why this field is optional) -> `connector.action` "Send DM"
  (confirmation).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import (
    build_branching_condition_chain,
    build_scoped_keyword_condition_chain,
)
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "instagram.comment_menu_automation"

MatchingMethod = Literal["exact", "contains", "starts_with", "ends_with"]

_METHOD_TO_OPERATOR: dict[MatchingMethod, str] = {
    "exact": "eq",
    "contains": "icontains",
    "starts_with": "starts_with",
    "ends_with": "ends_with",
}


class MenuOption(BaseModel):
    keyword: str = Field(min_length=1)
    reply_text: str = Field(min_length=1)
    media_url: str | None = None
    media_type: str | None = None


class InstagramCommentMenuAutomationConfig(BaseModel):
    trigger_keywords: list[str] = Field(default_factory=list)  # empty = match every comment
    matching_method: MatchingMethod = "contains"
    media_ids: list[str] = Field(default_factory=list)  # [] = account-wide (every post/reel)
    reply_comment_text: str | None = None
    private_reply_text: str = Field(min_length=1)
    menu_matching_method: MatchingMethod = "contains"
    menu_options: list[MenuOption] = Field(default_factory=list, max_length=5)
    ticket_keyword: str = Field(min_length=1)
    ticket_subject: str = Field(min_length=1)
    ticket_confirmation_text: str = Field(min_length=1)


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = InstagramCommentMenuAutomationConfig.model_validate(config)
    instance_id = str(connector_instance_id)

    nodes: list[dict[str, Any]] = [
        {
            "id": "trigger-comment",
            "type": "trigger",
            "position": {"x": 0, "y": 0},
            "data": {"nodeType": "instagram.comment_received", "label": "Comment Received", "config": {}},
        },
        {
            "id": "trigger-message",
            "type": "trigger",
            "position": {"x": 0, "y": 500},
            "data": {"nodeType": "instagram.message_received", "label": "DM Received", "config": {}},
        },
    ]
    edges: list[dict[str, Any]] = []

    # --- Chain A: comment match -> (optional public reply) -> Private Reply ---
    chain_a_actions: list[dict[str, Any]] = []
    if parsed.reply_comment_text:
        chain_a_actions.append(
            {
                "id": "action-reply",
                "type": "action",
                "data": {
                    "nodeType": "connector.action",
                    "label": "Reply to Comment",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "reply_to_comment",
                        "params": {"comment_id": "{{trigger.comment_id}}", "text": parsed.reply_comment_text},
                    },
                },
            }
        )
    chain_a_actions.append(
        {
            "id": "action-private-reply",
            "type": "action",
            "data": {
                "nodeType": "connector.action",
                "label": "Send Private Reply",
                "config": {
                    "connector_instance_id": instance_id,
                    "action": "send_private_reply",
                    "params": {"comment_id": "{{trigger.comment_id}}", "text": parsed.private_reply_text},
                },
            },
        }
    )

    chain_a_x = 780
    for offset, action_node in enumerate(chain_a_actions):
        action_node["position"] = {"x": chain_a_x + offset * 260, "y": 0}
        nodes.append(action_node)
        if offset > 0:
            edges.append(
                {
                    "id": f"e-{chain_a_actions[offset - 1]['id']}-{action_node['id']}",
                    "source": chain_a_actions[offset - 1]["id"],
                    "target": action_node["id"],
                }
            )

    operator_a = _METHOD_TO_OPERATOR[parsed.matching_method]
    chain_a_nodes, chain_a_edges = build_scoped_keyword_condition_chain(
        trigger_node_id="trigger-comment",
        scope_field_path="trigger.media_id",
        scope_values=parsed.media_ids,
        keyword_field_path="trigger.text",
        keywords=parsed.trigger_keywords,
        keyword_operator=operator_a,
        on_match_target_id=chain_a_actions[0]["id"],
        scope_id_prefix="media",
        start_x=260,
    )
    nodes.extend(chain_a_nodes)
    edges.extend(chain_a_edges)

    # --- Chain B: DM keyword branch -> per-option reply, or ticket + confirmation ---
    chain_b_x = 780
    case_targets: list[tuple[str, str]] = []
    for index, option in enumerate(parsed.menu_options):
        reply_id = f"action-menu-{index}"
        nodes.append(
            {
                "id": reply_id,
                "type": "action",
                "position": {"x": chain_b_x, "y": 500 + index * 220},
                "data": {
                    "nodeType": "connector.action",
                    "label": f"Reply: {option.keyword}",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "send_direct_message",
                        "params": {"recipient_id": "{{trigger.from}}", "text": option.reply_text},
                    },
                },
            }
        )
        if option.media_url:
            media_id = f"{reply_id}-media"
            nodes.append(
                {
                    "id": media_id,
                    "type": "action",
                    "position": {"x": chain_b_x + 260, "y": 500 + index * 220},
                    "data": {
                        "nodeType": "connector.action",
                        "label": f"Media: {option.keyword}",
                        "config": {
                            "connector_instance_id": instance_id,
                            "action": "send_media_message",
                            "params": {
                                "recipient_id": "{{trigger.from}}",
                                "media_url": option.media_url,
                                "media_type": option.media_type or "image",
                            },
                        },
                    },
                }
            )
            edges.append({"id": f"e-{reply_id}-{media_id}", "source": reply_id, "target": media_id})
        case_targets.append((option.keyword, reply_id))

    ticket_id = "action-ticket"
    ticket_confirm_id = "action-ticket-confirm"
    nodes.append(
        {
            "id": ticket_id,
            "type": "action",
            "position": {"x": chain_b_x, "y": 500 + len(parsed.menu_options) * 220},
            "data": {
                "nodeType": "create_ticket",
                "label": "Create Ticket",
                "config": {"subject": parsed.ticket_subject, "customer_id": None},
            },
        }
    )
    nodes.append(
        {
            "id": ticket_confirm_id,
            "type": "action",
            "position": {"x": chain_b_x + 260, "y": 500 + len(parsed.menu_options) * 220},
            "data": {
                "nodeType": "connector.action",
                "label": "Confirm Ticket",
                "config": {
                    "connector_instance_id": instance_id,
                    "action": "send_direct_message",
                    "params": {"recipient_id": "{{trigger.from}}", "text": parsed.ticket_confirmation_text},
                },
            },
        }
    )
    edges.append({"id": f"e-{ticket_id}-{ticket_confirm_id}", "source": ticket_id, "target": ticket_confirm_id})
    case_targets.append((parsed.ticket_keyword, ticket_id))

    operator_b = _METHOD_TO_OPERATOR[parsed.menu_matching_method]
    chain_b_nodes, chain_b_edges = build_branching_condition_chain(
        trigger_node_id="trigger-message",
        field_path="trigger.text",
        operator=operator_b,
        cases=case_targets,
        id_prefix="menu-case",
        start_x=260,
    )
    nodes.extend(chain_b_nodes)
    edges.extend(chain_b_edges)

    return {"nodes": nodes, "edges": edges}


registry.register(
    PredefinedAutomationType(
        automation_type=AUTOMATION_TYPE,
        connector_type_key="instagram",
        label="Comment-to-DM Menu",
        description=(
            "Reply to a comment keyword with a Private Reply DM, then let the commenter pick a "
            "menu option by replying - one option can create a support ticket instead of a text reply."
        ),
        build_graph=build_graph,
    )
)
