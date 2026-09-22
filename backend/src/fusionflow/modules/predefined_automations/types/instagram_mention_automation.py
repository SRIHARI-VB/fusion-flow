"""`instagram.mention_automation` — auto-reply to a comment on SOMEONE
ELSE'S Instagram post in which they `@mention` this connected account, when
the comment's text matches a configured keyword. Sibling to
`instagram_dm_automation.py`, same wizard-config-to-graph shape, but
triggered by `instagram.mention_received` instead of
`instagram.message_received`.

Caption-vs-comment-mention limitation: `instagram.mention_received` fires
for BOTH a comment mention ("hey check out @us in this pic") and a caption
mention (the post's own caption/description tags this account, with no
comment involved at all). Only the former has a `comment_id` to reply to -
see `workflows/nodes/instagram_mention_received.py`'s output schema, where
`comment_id`/`text`/`from_id`/`from_username` are all just empty strings
when the mention wasn't a comment (or when Meta's detail-lookup failed).
This automation does not special-case that: a caption mention's empty
`trigger.text` simply won't match any configured keyword (falling through
to the chain's "no match" terminal), and if it somehow did match, the
downstream `reply_to_comment` action would fail outright on an empty/missing
`comment_id` (see `instagram/adapter.py::perform_action`'s `reply_to_comment`
branch, which requires a non-empty `comment_id`). That failure is an
accepted limitation of this automation type, not something this module
tries to work around.

Config shape:
    {
      "trigger_keywords": ["thanks", "love this"],  # empty = match every mention
      "matching_method": "contains",                  # exact|contains|starts_with|ends_with
      "reply_text": "Thanks for the shoutout!",        # required - the comment reply text
      "reply_delay_minutes": 2,                        # optional, 1-1440 - wait before replying
    }

Generated graph shape: trigger (`instagram.mention_received`) -> the same
OR-chained `condition.field_compare` sequence
`graph_helpers.build_keyword_condition_chain` builds for the other Instagram
automation types (or, when `trigger_keywords` is empty, a direct edge -
"every mention" replies with no keyword filtering) -> optionally a
`flow.delay` node (only when `reply_delay_minutes` is set) -> a single
`connector.action` node calling `instagram.perform_action("reply_to_comment",
...)`, replying to `trigger.comment_id`.

No Auto-React or media attachment here (unlike the DM automation type):
`reply_to_comment` posts a public text-only comment reply, and comment-level
reactions aren't an Instagram capability this codebase supports (only DM
message reactions are, via `react_to_message` - not applicable to a comment
reply).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import build_keyword_condition_chain
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "instagram.mention_automation"

MatchingMethod = Literal["exact", "contains", "starts_with", "ends_with"]

_METHOD_TO_OPERATOR: dict[MatchingMethod, str] = {
    "exact": "eq",
    "contains": "contains",
    "starts_with": "starts_with",
    "ends_with": "ends_with",
}


class InstagramMentionAutomationConfig(BaseModel):
    trigger_keywords: list[str] = Field(default_factory=list)  # empty = match everything
    matching_method: MatchingMethod = "contains"
    reply_text: str = Field(min_length=1)
    reply_delay_minutes: int | None = Field(default=None, ge=1, le=1440)


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = InstagramMentionAutomationConfig.model_validate(config)
    instance_id = str(connector_instance_id)

    nodes: list[dict[str, Any]] = [
        {
            "id": "trigger",
            "type": "trigger",
            "position": {"x": 0, "y": 0},
            "data": {"nodeType": "instagram.mention_received", "label": "Mention Received", "config": {}},
        },
        {
            "id": "action-reply",
            "type": "action",
            "position": {"x": 1040 if parsed.reply_delay_minutes else 780, "y": 0},
            "data": {
                "nodeType": "connector.action",
                "label": "Reply to Comment",
                "config": {
                    "connector_instance_id": instance_id,
                    "action": "reply_to_comment",
                    "params": {"comment_id": "{{trigger.comment_id}}", "text": parsed.reply_text},
                },
            },
        },
    ]

    # When a reply delay is configured, the keyword chain's match target
    # becomes the `flow.delay` node instead of the reply action directly,
    # with a single plain edge from the delay node on to the reply action -
    # the delay node itself has no declared output handles (it's a plain
    # action, not a branch), so this edge needs no `sourceHandle`.
    match_target_id = "action-reply"
    edges: list[dict[str, Any]] = []
    if parsed.reply_delay_minutes is not None:
        match_target_id = "delay-reply"
        nodes.append(
            {
                "id": "delay-reply",
                "type": "action",
                "position": {"x": 780, "y": 0},
                "data": {
                    "nodeType": "flow.delay",
                    "label": "Wait Before Replying",
                    "config": {"minutes": parsed.reply_delay_minutes},
                },
            }
        )
        edges.append({"id": "e-delay-reply-action-reply", "source": "delay-reply", "target": "action-reply"})

    operator = _METHOD_TO_OPERATOR[parsed.matching_method]
    chain_nodes, chain_edges = build_keyword_condition_chain(
        trigger_node_id="trigger",
        field_path="trigger.text",
        keywords=parsed.trigger_keywords,
        operator=operator,
        on_match_target_id=match_target_id,
        start_x=260,
    )
    nodes.extend(chain_nodes)
    edges.extend(chain_edges)

    return {"nodes": nodes, "edges": edges}


registry.register(
    PredefinedAutomationType(
        automation_type=AUTOMATION_TYPE,
        connector_type_key="instagram",
        label="Mention Auto-Reply",
        description="Automatically reply to a comment where someone mentions this account, when it matches a keyword.",
        build_graph=build_graph,
    )
)
