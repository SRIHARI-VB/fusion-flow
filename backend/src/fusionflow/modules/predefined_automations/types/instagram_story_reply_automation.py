"""`instagram.story_reply_automation` — auto-reply via DM when someone
replies to a Story posted by this Instagram account and their reply text
matches a configured keyword. Sibling to `instagram_dm_automation.py`, same
wizard-config-to-graph shape, but triggered by
`instagram.story_reply_received` (a Story reply) instead of
`instagram.message_received` (a plain DM).

Config shape:
    {
      "trigger_keywords": ["discount", "code"],  # empty = match every reply
      "matching_method": "contains",               # exact|contains|starts_with|ends_with
      "reply_text": "Here's your discount code!",  # required - the DM sent back
      "media_url": "https://.../promo.jpg" | null,  # optional image/video sent alongside the text reply
      "media_type": "image" | "video" | null,       # only meaningful when media_url is set
      "react_emoji": "love" | null,                 # optional reaction on the triggering reply message
      "reply_delay_minutes": 5 | null,               # optional wait before any of the actions fire
    }

Generated graph shape: trigger (`instagram.story_reply_received`) -> the
same OR-chained `condition.field_compare` sequence
`graph_helpers.build_keyword_condition_chain` builds for the DM automation
(or, when `trigger_keywords` is empty, a single direct trigger->target edge
- "reply to every story reply") -> optionally a `flow.delay` node ("Reply
Delay") -> a sequentially-chained `action_nodes` list (same convergence
pattern `instagram_comment_automation.py` uses): the always-present
`send_direct_message` reply, then an optional `send_media_message` (Media
attachment), then an optional `react_to_message` (Auto-React) - order
doesn't matter functionally since none of the three depends on another's
output, but text-then-media-then-reaction is the most natural read order
for a run's activity log.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import build_keyword_condition_chain
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "instagram.story_reply_automation"

MatchingMethod = Literal["exact", "contains", "starts_with", "ends_with"]
ReactionEmoji = Literal["love", "like", "laugh", "wow", "sad", "angry"]

_METHOD_TO_OPERATOR: dict[MatchingMethod, str] = {
    "exact": "eq",
    "contains": "contains",
    "starts_with": "starts_with",
    "ends_with": "ends_with",
}


class InstagramStoryReplyAutomationConfig(BaseModel):
    trigger_keywords: list[str] = Field(default_factory=list)  # empty = match everything
    matching_method: MatchingMethod = "contains"
    reply_text: str = Field(min_length=1)
    media_url: str | None = Field(default=None)
    media_type: str | None = Field(default=None)
    react_emoji: ReactionEmoji | None = Field(default=None)
    reply_delay_minutes: int | None = Field(default=None, ge=1, le=1440)


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = InstagramStoryReplyAutomationConfig.model_validate(config)
    instance_id = str(connector_instance_id)

    nodes: list[dict[str, Any]] = [
        {
            "id": "trigger",
            "type": "trigger",
            "position": {"x": 0, "y": 0},
            "data": {"nodeType": "instagram.story_reply_received", "label": "Story Reply Received", "config": {}},
        }
    ]
    edges: list[dict[str, Any]] = []
    x = 780  # condition chain occupies x=260..~780 depending on keyword count; delay/actions start past it

    action_nodes: list[dict[str, Any]] = [
        {
            "id": "action-reply",
            "type": "action",
            "data": {
                "nodeType": "connector.action",
                "label": "Reply via DM",
                "config": {
                    "connector_instance_id": instance_id,
                    "action": "send_direct_message",
                    "params": {"recipient_id": "{{trigger.from}}", "text": parsed.reply_text},
                },
            },
        }
    ]
    if parsed.media_url:
        action_nodes.append(
            {
                "id": "action-media",
                "type": "action",
                "data": {
                    "nodeType": "connector.action",
                    "label": "Send Media",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "send_media_message",
                        "params": {
                            "recipient_id": "{{trigger.from}}",
                            "media_url": parsed.media_url,
                            "media_type": parsed.media_type or "image",
                        },
                    },
                },
            }
        )
    if parsed.react_emoji:
        action_nodes.append(
            {
                "id": "action-react",
                "type": "action",
                "data": {
                    "nodeType": "connector.action",
                    "label": "React to Reply",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "react_to_message",
                        "params": {
                            "recipient_id": "{{trigger.from}}",
                            "message_id": "{{trigger.message_id}}",
                            "reaction": parsed.react_emoji,
                        },
                    },
                },
            }
        )

    # Action nodes are unrestricted (no declared output handles), so they
    # chain sequentially via plain default-handle edges - only the FIRST
    # one is the condition chain's (or the delay node's) convergence target.
    delay_offset = 260 if parsed.reply_delay_minutes else 0
    for offset, action_node in enumerate(action_nodes):
        action_node["position"] = {"x": x + delay_offset + offset * 260, "y": 0}
        nodes.append(action_node)
        if offset > 0:
            edges.append(
                {
                    "id": f"e-{action_nodes[offset - 1]['id']}-{action_node['id']}",
                    "source": action_nodes[offset - 1]["id"],
                    "target": action_node["id"],
                }
            )

    # "Reply Delay" sits BETWEEN the keyword match and the action chain -
    # the condition chain's `on_match_target_id` becomes the delay node
    # instead of `action_nodes[0]`, with a single plain edge from the delay
    # node into the action chain once it resumes.
    first_target_id = action_nodes[0]["id"]
    if parsed.reply_delay_minutes:
        nodes.append(
            {
                "id": "action-delay",
                "type": "action",
                "position": {"x": x, "y": 0},
                "data": {
                    "nodeType": "flow.delay",
                    "label": "Reply Delay",
                    "config": {"minutes": parsed.reply_delay_minutes},
                },
            }
        )
        edges.append({"id": f"e-action-delay-{first_target_id}", "source": "action-delay", "target": first_target_id})
        first_target_id = "action-delay"

    operator = _METHOD_TO_OPERATOR[parsed.matching_method]
    chain_nodes, chain_edges = build_keyword_condition_chain(
        trigger_node_id="trigger",
        field_path="trigger.text",
        keywords=parsed.trigger_keywords,
        operator=operator,
        on_match_target_id=first_target_id,
        start_x=260,
    )
    nodes.extend(chain_nodes)
    edges.extend(chain_edges)

    return {"nodes": nodes, "edges": edges}


registry.register(
    PredefinedAutomationType(
        automation_type=AUTOMATION_TYPE,
        connector_type_key="instagram",
        label="Story Reply Auto-Reply",
        description=(
            "Automatically reply via DM when someone replies to one of your Stories and their "
            "message matches a keyword."
        ),
        build_graph=build_graph,
    )
)
