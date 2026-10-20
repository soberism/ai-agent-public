import json

from openai import OpenAI, OpenAIError

from backend.core.langsmith_tracing import observed, traced_model
from backend.core.security import settings
from backend.features.assistant.preferences import model_context
from backend.features.assistant.prompts import PREFERENCE_RULES, PROTECTED_REPLY


@observed
def personalize(reply, instructions: str, memories: list[str]):
    if not settings.llm_api_key.get_secret_value():
        return reply
    try:
        response = traced_model(
            OpenAI(
                api_key=settings.llm_api_key.get_secret_value(),
                base_url=settings.llm_base_url,
            )
        ).chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{PREFERENCE_RULES} 默认自然亲和。"
                        "你只为后端回复生成简短的称呼或语气引导语。"
                        "只返回JSON对象，包含prefix字符串；不复述业务结果、不增加事实、"
                        "不声称操作完成、不添加问题或操作指令，不输出数字。"
                        "严谨专业或简洁直接时可只保留称呼，无称呼可返回空串。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "preferences": instructions,
                            "memories": memories,
                            "kind": reply.kind,
                            "result": reply.message,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
            timeout=8,
        )
        prefix = json.loads(response.choices[0].message.content or "{}").get(
            "prefix", ""
        )
        if (
            not isinstance(prefix, str)
            or len(prefix) > 40
            or any(char.isdigit() for char in prefix)
            or PROTECTED_REPLY.search(prefix)
            or any(
                word in prefix
                for word in (
                    "成功",
                    "失败",
                    "确认",
                    "删除",
                    "创建",
                    "完成",
                    "查询",
                    "？",
                    "?",
                )
            )
        ):
            return reply
        return reply.model_copy(update={"message": prefix + reply.message})
    except OpenAIError, ValueError, TypeError, KeyError, IndexError:
        return reply


def personalize_for_user(reply, session, owner_id):
    instructions, memories = model_context(session, owner_id)
    return personalize(reply, instructions, memories)
