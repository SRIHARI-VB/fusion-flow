"""`patient_visits` - the "Patient Flow" Kanban module - plus
`memberships.is_doctor`, the flag that marks a staff member as
assignable in the doctor picker and gated behind step-up auth.

Revision ID: 0037_clinic_queue
Revises: 0036_user_sidebar_layouts
Create Date: 2026-09-28

`memberships` is a platform-level table (not tenant-scoped, no RLS - see
`modules/tenancy/models.py`'s module docstring), so `is_doctor` needs no
RLS work, unlike `patient_visits`.
"""

from typing import Sequence, Union

from alembic import op

from fusionflow.db.rls import enable_tenant_rls

revision: str = "0037_clinic_queue"
down_revision: Union[str, None] = "0036_user_sidebar_layouts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE memberships ADD COLUMN is_doctor BOOLEAN NOT NULL DEFAULT false")

    op.execute("CREATE TYPE patient_visit_stage AS ENUM ('reception', 'with_doctor', 'billing', 'completed')")
    op.execute("CREATE TYPE patient_visit_payment_mode AS ENUM ('cash', 'card', 'upi', 'insurance', 'other')")

    op.execute(
        """CREATE TABLE patient_visits (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	customer_id UUID NOT NULL,
	appointment_ref_id UUID,
	assigned_doctor_membership_id UUID,
	stage patient_visit_stage DEFAULT 'reception' NOT NULL,
	checked_in_at TIMESTAMP WITH TIME ZONE NOT NULL,
	doctor_started_at TIMESTAMP WITH TIME ZONE,
	consultation_notes TEXT,
	amount_to_collect NUMERIC(10, 2),
	billing_started_at TIMESTAMP WITH TIME ZONE,
	payment_mode patient_visit_payment_mode,
	amount_collected NUMERIC(10, 2),
	completed_at TIMESTAMP WITH TIME ZONE,
	position INTEGER DEFAULT '0' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE,
	FOREIGN KEY(assigned_doctor_membership_id) REFERENCES memberships (id) ON DELETE SET NULL,
	FOREIGN KEY(tenant_id) REFERENCES businesses (id) ON DELETE CASCADE
)"""
    )

    op.execute("CREATE INDEX ix_patient_visits_tenant_id ON patient_visits (tenant_id)")
    op.execute("CREATE INDEX ix_patient_visits_customer_id ON patient_visits (customer_id)")
    op.execute("CREATE INDEX ix_patient_visits_assigned_doctor_membership_id ON patient_visits (assigned_doctor_membership_id)")
    op.execute("CREATE INDEX ix_patient_visits_stage ON patient_visits (stage)")
    op.execute("CREATE INDEX ix_patient_visits_completed_at ON patient_visits (completed_at)")

    enable_tenant_rls(op, "patient_visits")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS patient_visits CASCADE")
    op.execute("DROP TYPE IF EXISTS patient_visit_payment_mode")
    op.execute("DROP TYPE IF EXISTS patient_visit_stage")
    op.execute("ALTER TABLE memberships DROP COLUMN IF EXISTS is_doctor")
