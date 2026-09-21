"""Every registered `PredefinedAutomationType`.

Importing this package registers all of the above with the process-wide
`predefined_automations.registry` singleton as a side effect - matching
`workflows.nodes`'s identical "import for side effect" pattern.
"""

from fusionflow.modules.predefined_automations.types import (  # noqa: F401
    instagram_comment_automation,
    whatsapp_appointment_booking,
)

__all__ = ["instagram_comment_automation", "whatsapp_appointment_booking"]
