"""Single import point for every ORM model.

SQLAlchemy resolves string-based relationship targets (e.g. `Membership.user
-> "User"`) against its class registry, so *all* mapped classes must be
imported before the first mapper configuration. Importing this one module
guarantees that. Alembic's `env.py` also imports it so autogenerate sees the
full metadata, and `main.py` imports it at startup.
"""

from fusionflow.db.base import Base
from fusionflow.modules.admin.models import (
    AuditLog,
    BusinessTemplate,
    BusinessTemplateConnectorType,
    FeatureFlag,
    FeatureFlagOverride,
    ImpersonationSession,
    Plan,
    PlanFeatureFlag,
    PlanResourceLimit,
    ResourceLimitOverride,
    WorkflowComponent,
    WorkflowNodeTemplate,
    WorkflowStarterTemplate,
)
from fusionflow.modules.auth.models import RefreshToken, User
from fusionflow.modules.broadcast_campaigns.models import BroadcastCampaign
from fusionflow.modules.business_objects.models import (
    ObjectFieldDefinition,
    ObjectRecord,
    ObjectTypeDefinition,
)
from fusionflow.modules.catalog.models import (
    Coupon,
    DiscountType,
    Offer,
    ProductService,
    ProductServiceType,
)
from fusionflow.modules.connectors.models import (
    ConnectorAccessOverride,
    ConnectorAccessRequest,
    ConnectorAccessRequestStatus,
    ConnectorCategory,
    ConnectorCredential,
    ConnectorEvent,
    ConnectorEventType,
    ConnectorInstance,
    ConnectorOAuthState,
    ConnectorState,
    ConnectorType,
    HealthStatus,
)
from fusionflow.modules.connectors.whatsapp.models import (
    WhatsAppTemplate,
    WhatsAppTemplateCategory,
    WhatsAppTemplateStatus,
)
from fusionflow.modules.custom_fields.models import (
    EntityType,
    FieldDefinition,
    FieldTemplate,
    FieldType,
)
from fusionflow.modules.customers.models import Customer, CustomerFieldDefinition
from fusionflow.modules.inbox.models import Conversation, Message, MessageDirection, MessageSenderType
from fusionflow.modules.kb.models import KbArticle, KbArticleStatus
from fusionflow.modules.media_library.models import MediaAsset
from fusionflow.modules.orders.models import Order, OrderStatus
from fusionflow.modules.payments.models import Payment, PaymentStatus
from fusionflow.modules.predefined_automations.models import PredefinedAutomation
from fusionflow.modules.quick_replies.models import QuickReply
from fusionflow.modules.tenancy.models import (
    Business,
    BusinessStatus,
    Membership,
    MembershipRole,
)
from fusionflow.modules.tickets.models import (
    Ticket,
    TicketMessage,
    TicketMessageAuthorType,
    TicketStatus,
)
from fusionflow.modules.workflows.models import (
    RunStatus,
    StepStatus,
    ValidationStatus,
    Workflow,
    WorkflowRun,
    WorkflowRunStep,
    WorkflowStatus,
    WorkflowTrigger,
    WorkflowTriggerInbox,
    WorkflowUserComponent,
    WorkflowVersion,
)

__all__ = [
    "AuditLog",
    "Base",
    "BroadcastCampaign",
    "Business",
    "BusinessStatus",
    "BusinessTemplate",
    "BusinessTemplateConnectorType",
    "ConnectorAccessOverride",
    "ConnectorAccessRequest",
    "ConnectorAccessRequestStatus",
    "ConnectorCategory",
    "ConnectorCredential",
    "ConnectorEvent",
    "ConnectorEventType",
    "ConnectorInstance",
    "ConnectorOAuthState",
    "ConnectorState",
    "ConnectorType",
    "Conversation",
    "Coupon",
    "Customer",
    "CustomerFieldDefinition",
    "DiscountType",
    "EntityType",
    "FeatureFlag",
    "FeatureFlagOverride",
    "FieldDefinition",
    "FieldTemplate",
    "FieldType",
    "HealthStatus",
    "ImpersonationSession",
    "KbArticle",
    "KbArticleStatus",
    "MediaAsset",
    "Membership",
    "MembershipRole",
    "Message",
    "MessageDirection",
    "MessageSenderType",
    "ObjectFieldDefinition",
    "ObjectRecord",
    "ObjectTypeDefinition",
    "Offer",
    "Order",
    "OrderStatus",
    "Payment",
    "PaymentStatus",
    "Plan",
    "PlanFeatureFlag",
    "PlanResourceLimit",
    "PredefinedAutomation",
    "ProductService",
    "ProductServiceType",
    "QuickReply",
    "RefreshToken",
    "ResourceLimitOverride",
    "RunStatus",
    "StepStatus",
    "Ticket",
    "TicketMessage",
    "TicketMessageAuthorType",
    "TicketStatus",
    "User",
    "ValidationStatus",
    "WhatsAppTemplate",
    "WhatsAppTemplateCategory",
    "WhatsAppTemplateStatus",
    "Workflow",
    "WorkflowComponent",
    "WorkflowNodeTemplate",
    "WorkflowRun",
    "WorkflowRunStep",
    "WorkflowStarterTemplate",
    "WorkflowStatus",
    "WorkflowTrigger",
    "WorkflowTriggerInbox",
    "WorkflowUserComponent",
    "WorkflowVersion",
]
