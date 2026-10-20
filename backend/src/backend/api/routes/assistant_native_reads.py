"""保留已授权只读路由的原生证据，不经过 UI 摘要裁剪。"""

from uuid import UUID

from fastapi.encoders import jsonable_encoder

from backend.api.routes.assistant_features import prepare, validate
from backend.core.security import APIError
from backend.features.assistant.answer_evidence import LIST_DOMAINS
from backend.features.assistant.capabilities import CAPABILITIES
from backend.features.assistant.feature_replies import without_member_emails
from backend.features.assistant.feature_tools import contract


def native_read(name, payload, user, session):
    if not CAPABILITIES[name][2]:
        raise APIError(422, "INVALID_ACTION", "只能读取已开放的数据")
    args, _ = prepare(name, payload, user, session)
    parsed = validate(name, args)
    handler, _ = contract(name)
    values = {key: getattr(parsed, key) for key in parsed.model_fields_set}
    for key, value in values.items():
        if key.endswith("_id") or key == "id":
            values[key] = UUID(value)
    data = jsonable_encoder(handler(user=user, session=session, **values))
    if name in {
        "list_households",
        "incoming_invitations",
        "sharing_options",
        "get_sharing",
    }:
        data = without_member_emails(data)
    if isinstance(data, list):
        data = {"items": data}
    if name in LIST_DOMAINS:
        # These allowlisted routes return the full authorized list without pagination.
        data["complete"] = True
        data["total_count"] = len(data["items"])
    return data
