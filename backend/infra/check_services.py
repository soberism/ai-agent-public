"""通过本地 SSH 隧道验证云端开发服务；只执行连接与只读查询。"""

from kombu import Connection
from redis import Redis
from sqlalchemy import create_engine, text

from backend.core.config import Settings

settings = Settings()
engine = create_engine(settings.database_url, connect_args={"connect_timeout": 5})
try:
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1
        version = connection.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
        assert version, "pgvector 扩展尚未启用"
        print(f"PostgreSQL: OK; pgvector: {version}")
finally:
    engine.dispose()

with Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password.get_secret_value(),
    socket_connect_timeout=5,
    socket_timeout=5,
) as redis:
    assert redis.ping()
    print("Redis authenticated PING: OK")

with Connection(
    hostname=settings.rabbitmq_host,
    port=settings.rabbitmq_port,
    userid=settings.rabbitmq_user,
    password=settings.rabbitmq_password.get_secret_value(),
    virtual_host=settings.rabbitmq_vhost,
    connect_timeout=5,
) as connection:
    connection.ensure_connection(max_retries=0)
    print("RabbitMQ authenticated AMQP: OK")
