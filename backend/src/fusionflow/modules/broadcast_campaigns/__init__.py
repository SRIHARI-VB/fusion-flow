"""Broadcast campaigns: a one-off scheduled bulk WhatsApp send, wrapping
the pre-existing `broadcast.scheduled_send` trigger + `WorkflowSchedule`
machinery (`modules.workflows`) with a tenant-facing "campaign" concept -
see `service.py`'s module docstring.
"""
