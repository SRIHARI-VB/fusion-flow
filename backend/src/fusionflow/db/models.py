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
)
from fusionflow.modules.auth.models import RefreshToken, User
from fusionflow.modules.catalog.models import (
    Coupon,
    DiscountType,
    Offer,
    ProductService,
    ProductServiceType,
)
from fusionflow.modules.connectors.models import (
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
from fusionflow.modules.custom_fields.models import (
    EntityType,
    FieldDefinition,
    FieldTemplate,
    FieldType,
)
from fusionflow.modules.customers.models import Customer
from fusionflow.modules.kb.models import KbArticle, KbArticleStatus
from fusionflow.modules.orders.models import Order, OrderStatus
from fusionflow.modules.payments.models import Payment, PaymentStatus
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
    WorkflowVersion,
)

__all__ = [
    "AuditLog",
    "Base",
    "Business",
    "BusinessStatus",
    "BusinessTemplate",
    "BusinessTemplateConnectorType",
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
    "Coupon",
    "Customer",
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
    "Membership",
    "MembershipRole",
    "Offer",
    "Order",
    "OrderStatus",
    "Payment",
    "PaymentStatus",
    "Plan",
    "PlanFeatureFlag",
    "ProductService",
    "ProductServiceType",
    "RefreshToken",
    "RunStatus",
    "StepStatus",
    "Ticket",
    "TicketMessage",
    "TicketMessageAuthorType",
    "TicketStatus",
    "User",
    "ValidationStatus",
    "Workflow",
    "WorkflowRun",
    "WorkflowRunStep",
    "WorkflowStatus",
    "WorkflowTrigger",
    "WorkflowTriggerInbox",
    "WorkflowVersion",
]
