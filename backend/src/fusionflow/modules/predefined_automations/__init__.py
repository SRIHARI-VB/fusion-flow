"""Predefined automations: guided, wizard-configured automations that are
ordinary `Workflow`/`WorkflowVersion` rows under the hood - never opened in
the canvas editor. See `service.py`'s module docstring for the full
design rationale.
"""

from fusionflow.modules.predefined_automations import types as _types  # noqa: F401 - registers every automation type
