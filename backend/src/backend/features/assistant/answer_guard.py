"""Publish verified structured claims; never classify facts by answer wording."""

import json

from backend.features.assistant.autonomous_types import Decision
from backend.features.assistant.claim_verification import verify


def guard_decision(state, decision):
    if decision.action != "final_answer":
        return decision
    request = (
        decision.resolved_request or state.get("resolved_request") or state["prompt"]
    )
    if decision.answer_kind == "clarification" and not decision.claims:
        return decision
    factual = (
        decision.answer_kind in {"business", "document", "execution"}
        or decision.requires_current_data
        or state.get("requires_current_data", False)
        or bool(decision.claims)
        or bool(state["observations"] or state["knowledge"] or state.get("web_results"))
    )
    if not factual:
        return decision
    if decision.answer_kind == "execution":
        return Decision(
            action="final_answer",
            answer="目前还没有这项操作已完成的结果。如果有待确认的方案，请先核对后再确认执行。",
        )
    if (
        not decision.claims
        and not state["observations"]
        and not state.get("web_results")
    ):
        if (
            decision.answer_kind == "document"
            and not state["knowledge"]
            and not state.get("knowledge_count")
        ):
            return Decision(action="retrieve_knowledge", query=request[:300])
        if (
            (
                decision.requires_current_data
                or state.get("requires_current_data", False)
                or decision.answer_kind == "business"
            )
            and not state["discovered_tools"]
            and not state.get("stalled_on")
        ):
            return Decision(
                action="search_tools", query=request[:300], resolved_request=request
            )
    _, errors = verify(state, decision.claims)
    covered = {
        claim.domain for claim in decision.claims if not verify(state, [claim])[1]
    }
    missing = set(decision.requested_domains) - covered
    if missing:
        errors.append(
            "用户请求的业务类型尚未核实，请补查并分别给出结论："
            + "、".join(sorted(missing))
        )
    if not decision.claims:
        errors = ["事实回答必须提供逐项claims和本轮证据引用，不能只提供answer正文"]
    if errors and not state.get("claim_retries"):
        return Decision(
            action="revise_answer",
            answer="；".join(errors),
            resolved_request=request,
            requested_domains=sorted(missing),
        )
    verified_fields = [
        claim
        for claim in decision.claims
        if claim.kind == "field" and not verify(state, [claim])[1]
    ]
    published, lines, omitted = [], [], False
    seen = set()
    for claim in decision.claims:
        rendered, invalid = verify(state, [claim])
        identity = json.dumps(
            claim.model_dump(exclude={"evidence_ids"}),
            sort_keys=True,
            ensure_ascii=False,
        )
        if invalid or identity in seen:
            continue
        seen.add(identity)
        if (
            claim.kind == "count"
            and claim.value
            and len(
                {
                    field.subject_id
                    for field in verified_fields
                    if field.subject_id
                    and field.domain == claim.domain
                    and field.scope == claim.scope
                    and set(field.evidence_ids) == set(claim.evidence_ids)
                }
            )
            == claim.value
        ):
            rendered = [rendered[0].split("\n", 1)[0]]
        if sum(len(line) + 1 for line in lines) + len(rendered[0]) > 3600:
            omitted = True
            continue
        published.append(claim)
        lines.append(rendered[0])
    answer = (
        "\n".join(lines)
        or "这次还没能核实你要的信息。可以再试一次，或补充具体的事项名称、日期或资料。"
    )
    if not lines and state.get("web_results"):
        answer = "这次没能从网上核实你问的信息。可以换个关键词再查；实时信息请以官方渠道为准。"
    if errors and lines:
        answer += "\n其余结论暂未核实。"
    if omitted:
        answer += "\n部分已核实内容较长，请限定范围后查看。"
    return Decision(
        action="final_answer",
        answer_kind=decision.answer_kind,
        answer=answer,
        claims=published,
        resolved_request=request,
    )
