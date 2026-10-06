"""Patient detail snapshots and delayed calendar cancellation retries."""
from alembic import op
import sqlalchemy as sa

revision = "0041_patient_booking_reset"
down_revision = "0040_inbox_processing_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patient_visits", sa.Column("patient_name", sa.String(200), nullable=True))
    op.add_column("patient_visits", sa.Column("patient_phone", sa.String(40), nullable=True))
    op.execute("""UPDATE patient_visits v SET patient_name=c.name, patient_phone=c.phone
                  FROM customers c WHERE c.id=v.customer_id AND c.tenant_id=v.tenant_id""")
    op.add_column("workflow_trigger_inbox", sa.Column("available_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("workflow_trigger_inbox", "available_at")
    op.drop_column("patient_visits", "patient_phone")
    op.drop_column("patient_visits", "patient_name")
