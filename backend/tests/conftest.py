import os

# 测试显式调用调度，防止后台循环发送测试或开发账号邮件。
os.environ["EMAIL_SCHEDULER_ENABLED"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

if os.environ.get("RUN_INTEGRATION") != "1":
    for key in ("POSTGRES_PASSWORD", "REDIS_PASSWORD", "RABBITMQ_PASSWORD"):
        os.environ.setdefault(key, "test-only")
    os.environ.setdefault("CURSOR_SECRET", "test-only-cursor-secret-32-characters")
from helpers import cloud  # noqa: F401
