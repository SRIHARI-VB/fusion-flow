"""Publish the clinic's button menus after deploying the batching backend.

Runs read-only unless --apply is supplied. Existing versions and routing
payloads are preserved. Never executes the workflow or sends a message.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import json
import uuid

from scripts.repair_clinic_instagram_workflow import RepairError, repair_workflow


WELCOME_IDS = ("send-main-menu", "send-main-menu-firsttime", "send-main-menu-returning")
TEXT_HINT = "(Or just type your answer if you don't see buttons.)"
SERVICE_FIRST = "dyn-send-services-page1"
SERVICE_SECOND = "dyn-send-services-page2"


def button_menus_graph(original: dict) -> dict:
    graph = deepcopy(original)
    nodes = {n["id"]: n for n in graph["nodes"]}
    if len(nodes) != len(graph["nodes"]):
        raise RepairError("Duplicate node IDs")
    for node_id in WELCOME_IDS:
        data = nodes.get(node_id, {}).get("data", {})
        config = data.get("config", {})
        if data.get("nodeType") != "connector.action" or config.get("action") not in (
            "send_quick_replies", "send_button_template",
        ):
            raise RepairError(f"Unexpected welcome menu: {node_id}")
        params = config["params"]
        options = params.get("replies") if config["action"] == "send_quick_replies" else params.get("buttons")
        if [b.get("payload") for b in options or []] != [
            "MENU_CONSULT", "MENU_TREATMENTS", "MENU_INFO", "MENU_SUPPORT",
        ]:
            raise RepairError(f"Welcome options changed: {node_id}")
        config["action"] = "send_button_template"
        params.pop("replies", None)
        params["buttons"] = options
        params["text"] = params["text"].replace(TEXT_HINT, "").rstrip()

    first = nodes.get(SERVICE_FIRST, {}).get("data", {})
    source = first.get("config", {}).get("source", {})
    if (first.get("nodeType") != "instagram.ask_choice" or source.get("module") != "services"
            or source.get("offset") != 0 or source.get("limit") not in (3, 100)):
        raise RepairError("Unexpected service picker")
    if SERVICE_SECOND in nodes:
        second = nodes[SERVICE_SECOND]["data"]
        expected_source = {**source, "offset": 3, "limit": 3}
        if (source["limit"] != 3 or second.get("nodeType") != "instagram.ask_choice"
                or second.get("config", {}).get("source") != expected_source
                or any(first["config"].get(k) != second["config"].get(k)
                       for k in ("connector_instance_id", "recipient_id"))):
            raise RepairError("Service pages no longer query the same list")
        affected = [e for e in graph["edges"] if SERVICE_SECOND in (e["source"], e["target"])]
        if (len(affected) != 1 or affected[0]["source"] != SERVICE_FIRST
                or affected[0].get("sourceHandle") is not None or (affected[0].get("data") or {}).get("filter")):
            raise RepairError("Unexpected service page connections")
        graph["nodes"] = [n for n in graph["nodes"] if n["id"] != SERVICE_SECOND]
        graph["edges"] = [e for e in graph["edges"] if e not in affected]
        if SERVICE_SECOND in json.dumps({"nodes": graph["nodes"], "edges": graph["edges"]}):
            raise RepairError("Another node still references the removed service page")
    elif source["limit"] != 100:
        raise RepairError("Second service page is unexpectedly missing")
    source["limit"] = 100

    slots = [n for n in graph["nodes"] if n["data"]["nodeType"] == "instagram.ask_calendar_slot"]
    if len(slots) != 12:
        raise RepairError("Expected all 12 reviewed clinic slot pickers")
    for node in slots:
        config = node["data"]["config"]
        if config.get("limit") not in (13, 288) or config.get("offset") != 0:
            raise RepairError(f"Slot pagination changed: {node['id']}")
        config["limit"] = 288  # A full day at the minimum five-minute duration.
    if any(n["data"].get("config", {}).get("action") == "send_quick_replies" for n in graph["nodes"]):
        raise RepairError("Unexpected additional quick-reply menu needs review")
    return graph


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=uuid.UUID, required=True)
    parser.add_argument("--workflow-id", type=uuid.UUID, required=True)
    parser.add_argument("--actor-email", required=True)
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from sqlalchemy import text
    from fusionflow.db import models as _models  # noqa: F401
    from fusionflow.db.session import async_session_factory, set_tenant_context

    async with async_session_factory() as session, session.begin():
        if not args.apply:
            await session.execute(text("SET TRANSACTION READ ONLY"))
        await set_tenant_context(session, args.tenant_id)
        report = await repair_workflow(session, **vars(args), graph_transform=button_menus_graph)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
