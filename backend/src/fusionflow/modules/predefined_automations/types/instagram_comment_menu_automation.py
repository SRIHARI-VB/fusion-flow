"""`instagram.comment_menu_automation` — a comment-triggered "lead capture"
flow: reply (publicly and/or via a text-only Private Reply) when a comment
on a scoped post/reel matches a keyword, then once the commenter replies
with anything at all, send a REAL tappable button-template menu (not a
"type a word" prompt) - up to 3 buttons, one of which can create a support
ticket instead of replying with text.

Why THREE trigger chains, not two, and why the second chain can't be
collapsed into the first: Meta's Send API can only address a
`recipient.id` (needed for a button template, or any rich content) inside
an already-open 24h messaging window - a first-time commenter has none.
The one channel that CAN reach them at all is a Private Reply
(`recipient.comment_id`), and per `instagram/adapter.py::send_private_reply`'s
own docstring that channel is text-only on Meta's side - there is no way
to attach buttons to it, full stop. So:

  1. Comment matches -> Private Reply (plain text, unavoidable - this is
     the one message Meta allows to someone who's never messaged this
     account before). Its copy should invite ANY reply, not ask them to
     type a specific word - the next chain reacts to any reply at all.
  2. That reply (now a real inbound DM - the window is open) -> send a
     genuine button-template message (`send_button_template`): up to 3
     tappable buttons, no free-typing involved from here on.
  3. A button tap is, per Meta's own delivery model (see
     `instagram_ask_choice.py`'s module docstring - button taps never
     resume a suspended node, they always start a fresh `WorkflowRun` via
     `instagram.postback_received`), handled as its own trigger chain,
     branching on the tapped button's payload.

Demo-account caveat (deliberately not engineered around): chain 2 reacts
to ANY inbound DM on this connector instance, not just ones that followed
chain 1's Private Reply - Instagram's webhook payload has no "this reply
followed that private reply" correlation to key off, so an unrelated DM
to this account would also see the button menu. Acceptable for a demo
account; a real deployment sharing the account with other DM-triggered
automations would need a correlation mechanism (e.g. a short-lived
"awaiting menu reply" flag per external contact) this doesn't build.

Config shape:
    {
      "trigger_keywords": ["demo"],                  # [] = match every comment
      "matching_method": "contains",                   # exact|contains|starts_with|ends_with
      "media_ids": ["1784...5"],                       # [] = every post/reel on the account
      "reply_comment_text": "Check your DMs!" | null,  # public reply; null/empty disables it
      "private_reply_text": "Thanks for your interest! Reply here and I'll show you your options.",
      "menu_text": "What would you like to know?",
      "buttons": [                                      # 1-3 entries, Meta's own button-template cap
        {"title": "Our Services", "reply_text": "...", "media_url": null, "media_type": null, "is_ticket_button": false},
        {"title": "Book a Demo", "reply_text": null, "media_url": null, "media_type": null, "is_ticket_button": true},
      ],
      "ticket_subject": "Instagram demo request from {{trigger.from}}",
      "ticket_confirmation_text": "Thanks! We've logged this and our team will reach out.",
    }
Exactly one button must have `is_ticket_button: true` - validated here
rather than left to the publish-time graph validator, so a misconfigured
wizard submission fails fast with a clear message instead of a confusing
generated-graph error.

Generated graph shape:

  Chain A (comment -> private reply): trigger `instagram.comment_received`
  -> `graph_helpers.build_scoped_keyword_condition_chain` (post/reel
  scope, then keyword) -> optional `connector.action` "Reply to Comment"
  -> `connector.action` "Send Private Reply" (always present).

  Chain B (any DM -> button menu): trigger `instagram.message_received`,
  wired with NO condition layer at all (every inbound DM reaches it - see
  this module's own "demo-account caveat" above) -> `connector.action`
  "Send Menu" (`send_button_template`, one button per configured entry,
  payload `f"MENU_{i}"`).

  Chain C (tap -> reply or ticket): trigger `instagram.postback_received`
  -> `graph_helpers.build_branching_condition_chain` on `trigger.payload`
  (`eq` against each `MENU_{i}`) -> per non-ticket button:
  `connector.action` "Send DM" (text), optionally chained into
  `connector.action` "Send Media" when that button has a `media_url` -
  same per-button media chaining as
  `instagram_button_menu_automation.py`'s per-button media node. The one
  ticket button: `create_ticket` (no `customer_id` - Instagram DMs don't
  link to a `Customer` record today) -> `connector.action` "Send DM"
  (confirmation).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

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

_MAX_BUTTONS = 3  # Meta's own button-template cap, same as send_button_template's.


class MenuButton(BaseModel):
    title: str = Field(min_length=1, max_length=20)  # Meta's button title length limit
    reply_text: str | None = None
    media_url: str | None = None
    media_type: str | None = None
    is_ticket_button: bool = False


class InstagramCommentMenuAutomationConfig(BaseModel):
    trigger_keywords: list[str] = Field(default_factory=list)  # empty = match every comment
    matching_method: MatchingMethod = "contains"
    media_ids: list[str] = Field(default_factory=list)  # [] = account-wide (every post/reel)
    reply_comment_text: str | None = None
    private_reply_text: str = Field(min_length=1)
    menu_text: str = Field(min_length=1)
    buttons: list[MenuButton] = Field(min_length=1, max_length=_MAX_BUTTONS)
    ticket_subject: str = Field(min_length=1)
    ticket_confirmation_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _exactly_one_ticket_button(self) -> "InstagramCommentMenuAutomationConfig":
        ticket_buttons = [b for b in self.buttons if b.is_ticket_button]
        if len(ticket_buttons) != 1:
            raise ValueError("exactly one button must have is_ticket_button=true")
        non_ticket_missing_reply = [b for b in self.buttons if not b.is_ticket_button and not b.reply_text]
        if non_ticket_missing_reply:
            raise ValueError("every non-ticket button needs a reply_text")
        return self


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
            "position": {"x": 0, "y": 450},
            "data": {"nodeType": "instagram.message_received", "label": "DM Received", "config": {}},
        },
        {
            "id": "trigger-postback",
            "type": "trigger",
            "position": {"x": 0, "y": 900},
            "data": {"nodeType": "instagram.postback_received", "label": "Button Tapped", "config": {}},
        },
    ]
    edges: list[dict[str, Any]] = []

    # Every run's frontier is seeded from EVERY trigger node in the graph,
    # not just the one matching the inbox event that caused it (see
    # `run_loop.py::execute_run` - it calls `graph.trigger_nodes()`
    # unconditionally). `instagram_button_menu_automation.py`'s two chains
    # stay safe from this by accident: a postback event has no `text`
    # field, so its "send menu" chain's keyword condition just evaluates
    # false; a DM/comment event has no `payload` field, so its postback
    # branch's `eq` comparisons do the same. This automation's chain B has
    # no such accidental gate (it deliberately has no keyword condition at
    # all - any reply should show the menu), so it needs an explicit guard
    # - same "guard-comment"-style node the hand-built Instagram Assistant
    # workflow already uses for exactly this reason.
    #
    # `trigger.comment_id` only exists on a real comment event
    # (`instagram.comment_received`'s own output schema) - message and
    # postback events both lack it. `trigger.payload` only exists on a
    # real postback event - comment and message events both lack it.
    # Together: comment_id present -> real comment; comment_id absent AND
    # payload absent -> real plain DM; payload present -> real button tap.

    # --- Chain A: comment match -> (optional public reply) -> Private Reply ---
    nodes.append(
        {
            "id": "guard-comment",
            "type": "condition",
            "position": {"x": 180, "y": -80},
            "data": {
                "nodeType": "condition.field_compare",
                "label": "Is Comment Event",
                "config": {"field_path": "trigger.comment_id", "operator": "neq", "value": None},
            },
        }
    )
    nodes.append(
        {
            "id": "guard-comment-noop",
            "type": "action",
            "position": {"x": 180, "y": 120},
            "data": {"nodeType": "log.noop", "label": "Not a Comment Event", "config": {}},
        }
    )
    edges.append({"id": "e-trigger-comment-guard-comment", "source": "trigger-comment", "target": "guard-comment"})
    edges.append(
        {
            "id": "e-guard-comment-false",
            "source": "guard-comment",
            "target": "guard-comment-noop",
            "sourceHandle": "false",
        }
    )

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
    # The helper always emits exactly one unconditional edge sourced from
    # `trigger_node_id` (see its own docstring - every combination of
    # empty/non-empty scope+keywords collapses to exactly one) - redirect
    # it to originate from `guard-comment`'s "true" handle instead of
    # `trigger-comment` directly, so the chain only proceeds for a real
    # comment event (see the guard-node comment above).
    for edge in chain_a_edges:
        if edge["source"] == "trigger-comment" and "sourceHandle" not in edge:
            edge["source"] = "guard-comment"
            edge["sourceHandle"] = "true"
            edge["id"] = f"e-guard-comment-true-{edge['target']}"
            break
    else:
        raise AssertionError(
            "expected build_scoped_keyword_condition_chain to emit exactly one unconditional edge from trigger_node_id"
        )
    nodes.extend(chain_a_nodes)
    edges.extend(chain_a_edges)

    # --- Chain B: any inbound DM -> send the real button-template menu ---
    nodes.append(
        {
            "id": "action-send-menu",
            "type": "action",
            "position": {"x": 440, "y": 450},
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
                            {"title": button.title, "payload": f"MENU_{index}"}
                            for index, button in enumerate(parsed.buttons)
                        ],
                    },
                },
            },
        }
    )
    nodes.append(
        {
            "id": "guard-dm-not-comment",
            "type": "condition",
            "position": {"x": 180, "y": 380},
            "data": {
                "nodeType": "condition.field_compare",
                "label": "Not a Comment Event",
                "config": {"field_path": "trigger.comment_id", "operator": "eq", "value": None},
            },
        }
    )
    nodes.append(
        {
            "id": "guard-dm-not-postback",
            "type": "condition",
            "position": {"x": 440, "y": 380},
            "data": {
                "nodeType": "condition.field_compare",
                "label": "Not a Button Tap",
                "config": {"field_path": "trigger.payload", "operator": "eq", "value": None},
            },
        }
    )
    nodes.append(
        {
            "id": "guard-dm-noop",
            "type": "action",
            "position": {"x": 180, "y": 560},
            "data": {"nodeType": "log.noop", "label": "Not a Plain DM", "config": {}},
        }
    )
    edges.append({"id": "e-trigger-message-guard-dm-1", "source": "trigger-message", "target": "guard-dm-not-comment"})
    edges.append(
        {
            "id": "e-guard-dm-1-true",
            "source": "guard-dm-not-comment",
            "target": "guard-dm-not-postback",
            "sourceHandle": "true",
        }
    )
    edges.append(
        {
            "id": "e-guard-dm-1-false",
            "source": "guard-dm-not-comment",
            "target": "guard-dm-noop",
            "sourceHandle": "false",
        }
    )
    edges.append(
        {
            "id": "e-guard-dm-2-true",
            "source": "guard-dm-not-postback",
            "target": "action-send-menu",
            "sourceHandle": "true",
        }
    )
    edges.append(
        {
            "id": "e-guard-dm-2-false",
            "source": "guard-dm-not-postback",
            "target": "guard-dm-noop",
            "sourceHandle": "false",
        }
    )

    # --- Chain C: button tap -> reply, or ticket + confirmation ---
    chain_c_x = 260
    case_targets: list[tuple[str, str]] = []
    for index, button in enumerate(parsed.buttons):
        if button.is_ticket_button:
            ticket_id = f"action-ticket-{index}"
            confirm_id = f"action-ticket-confirm-{index}"
            nodes.append(
                {
                    "id": ticket_id,
                    "type": "action",
                    "position": {"x": chain_c_x, "y": 900 + index * 220},
                    "data": {
                        "nodeType": "create_ticket",
                        "label": "Create Ticket",
                        "config": {"subject": parsed.ticket_subject, "customer_id": None},
                    },
                }
            )
            nodes.append(
                {
                    "id": confirm_id,
                    "type": "action",
                    "position": {"x": chain_c_x + 260, "y": 900 + index * 220},
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
            edges.append({"id": f"e-{ticket_id}-{confirm_id}", "source": ticket_id, "target": confirm_id})
            case_targets.append((f"MENU_{index}", ticket_id))
        else:
            reply_id = f"action-menu-{index}"
            nodes.append(
                {
                    "id": reply_id,
                    "type": "action",
                    "position": {"x": chain_c_x, "y": 900 + index * 220},
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
            if button.media_url:
                media_id = f"{reply_id}-media"
                nodes.append(
                    {
                        "id": media_id,
                        "type": "action",
                        "position": {"x": chain_c_x + 260, "y": 900 + index * 220},
                        "data": {
                            "nodeType": "connector.action",
                            "label": f"Media: {button.title}",
                            "config": {
                                "connector_instance_id": instance_id,
                                "action": "send_media_message",
                                "params": {
                                    "recipient_id": "{{trigger.from}}",
                                    "media_url": button.media_url,
                                    "media_type": button.media_type or "image",
                                },
                            },
                        },
                    }
                )
                edges.append({"id": f"e-{reply_id}-{media_id}", "source": reply_id, "target": media_id})
            case_targets.append((f"MENU_{index}", reply_id))

    chain_c_nodes, chain_c_edges = build_branching_condition_chain(
        trigger_node_id="trigger-postback",
        field_path="trigger.payload",
        operator="eq",
        cases=case_targets,
        id_prefix="menu-case",
        start_x=260,
    )
    nodes.extend(chain_c_nodes)
    edges.extend(chain_c_edges)

    return {"nodes": nodes, "edges": edges}


registry.register(
    PredefinedAutomationType(
        automation_type=AUTOMATION_TYPE,
        connector_type_key="instagram",
        label="Comment-to-DM Menu",
        description=(
            "Reply to a comment keyword with a Private Reply DM; once the commenter replies, send a "
            "real tappable button menu - one button can create a support ticket instead of a text reply."
        ),
        build_graph=build_graph,
    )
)
