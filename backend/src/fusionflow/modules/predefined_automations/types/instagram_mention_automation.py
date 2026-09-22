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
      "trigger_keywords": ["thanks", "love this"],  # non-empty, required
      "matching_method": "contains",                  # exact|contains|starts_with|ends_with
      "reply_text": "Thanks for the shoutout!",        # required - the comment reply text
    }

Generated graph shape: trigger (`instagram.mention_received`) -> the same
OR-chained `condition.field_compare` sequence
`graph_helpers.build_keyword_condition_chain` builds for the other Instagram
automation types -> a single `connector.action` node calling
`instagram.perform_action("reply_to_comment", ...)`, replying to
`trigger.comment_id`.
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
            "position": {"x": 780, "y": 0},
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
        label="Mention Auto-Reply",
        description="Automatically reply to a comment where someone mentions this account, when it matches a keyword.",
        build_graph=build_graph,
    )
)
