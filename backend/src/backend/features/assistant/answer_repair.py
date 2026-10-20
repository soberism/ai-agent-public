"""Expose the missing read capabilities when repairing an incomplete answer."""

from backend.features.assistant import tool_registry


def revise_answer(state):
    missing = set(state["decision"].get("requested_domains", []))
    found = tool_registry.search(
        state.get("resolved_request") or state["prompt"], mode="read", limit=10
    )
    if missing:
        found = [item for item in found if item["domain"] in missing]
        described = [tool_registry.describe(item["name"]) for item in found[:5]]
    else:
        described = state["described_tools"]
        found = [*found, *state["discovered_tools"]]
    candidates = {item["name"]: item for item in found}
    return {
        "discovered_tools": list(candidates.values())[:10],
        "described_tools": described,
        "claim_retries": state.get("claim_retries", 0) + 1,
        "stalled_on": "invalid-answer: " + state["decision"]["answer"][:1200],
    }
