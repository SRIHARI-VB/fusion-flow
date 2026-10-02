"""Every registered `PredefinedAutomationType`.

Importing this package registers all of the above with the process-wide
`predefined_automations.registry` singleton as a side effect - matching
`workflows.nodes`'s identical "import for side effect" pattern.
"""

from fusionflow.modules.predefined_automations.types import (  # noqa: F401
    instagram_button_menu_automation,
    instagram_comment_automation,
    instagram_comment_menu_automation,
    instagram_comment_moderation,
    instagram_dm_automation,
    instagram_handoff_automation,
    instagram_mention_automation,
    instagram_reaction_automation,
    instagram_referral_automation,
    instagram_story_reply_automation,
    whatsapp_appointment_booking,
)

__all__ = [
    "instagram_button_menu_automation",
    "instagram_comment_automation",
    "instagram_comment_menu_automation",
    "instagram_comment_moderation",
    "instagram_dm_automation",
    "instagram_handoff_automation",
    "instagram_mention_automation",
    "instagram_reaction_automation",
    "instagram_referral_automation",
    "instagram_story_reply_automation",
    "whatsapp_appointment_booking",
]
