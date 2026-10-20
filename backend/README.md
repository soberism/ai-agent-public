# 安排儿后端

Python 3.14 + FastAPI + SQLAlchemy + LangGraph + Celery。PostgreSQL保存业务数据与图检查点，pgvector用于材料检索，Redis保存会话、配额和摘要租约，RabbitMQ承载异步任务。

## 开发启动

在本目录执行 `cp .env.example .env`，填入自己拥有的云端服务配置。`CURSOR_SECRET`及`EMAIL_VERIFICATION_SECRET`各使用独立的至少32字符随机值；数据库、Redis及RabbitMQ密码不能使用示例值。

如需SSH隧道，先将自己的私钥及可信known_hosts放入忽略目录`.local/`，或设置`SSH_IDENTITY_FILE`、`SSH_KNOWN_HOSTS_FILE`。核验服务器指纹后，运行：

```bash
SSH_HOST=your-server.example.com SSH_USER=your-user bash infra/tunnel.sh
```

默认转发15432、16379、15673三个本地端口；已有隧道可直接复用。也可使用已获授权且受保护的直接连接，不依赖本项目维护者的服务器。

```bash
uv sync --locked
uv run python infra/check_services.py
uv run alembic upgrade head
uv run uvicorn backend.app:app --reload --no-proxy-headers
```

另开两个终端，使用相同`.env`启动回答和摘要Worker：

```bash
uv run celery -A backend.features.assistant.agent_celery.celery worker --concurrency=1 --without-gossip --without-mingle -Q celery
uv run celery -A backend.features.assistant.agent_celery.celery worker --concurrency=1 --without-gossip --without-mingle -Q assistant-summary
```

若修改`ASSISTANT_SUMMARY_QUEUE`，第二条命令的队列名称也必须同步。摘要不能只依赖回答Worker消费，否则快速追问会阻塞。API默认8000，`/health`表示存活、`/ready`同时检查数据库，`/docs`提供接口文档。应用不会在启动时自动迁移。

## 必填与可选能力

- 数据库、Redis、RabbitMQ及`CURSOR_SECRET`是基础配置。
- 注册需SMTP和`EMAIL_VERIFICATION_SECRET`；不提供默认账号。
- 对话需`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`；向量和转写可独立配置。
- 转写还需FFmpeg。IMAP默认关闭，只有显式配置`IMAP_OWNER_ID`的账号可扫描该服务器邮箱；其他账号不能借用连接。绑定值取该账号`GET /api/auth/me`的id，不能由扫描请求指定。
- LangSmith默认关闭。启用后会外发规则脱敏的执行内容；自由文本脱敏并不完整。
- 开发HTTP使用`COOKIE_SECURE=false`，仅development允许。正式部署使用HTTPS、Secure Cookie、精确Origin和已核验的代理地址。

## 安全与配额

默认每账号最多1个queued/running对话或执行任务；待确认计划可以保留，取消及状态查询不消耗额度。对话20次/60秒、200次/24小时；转写10次/60秒、100次/24小时；重建索引1次/60秒、10次/24小时。所有额度从首次计数开始，按账号存于Redis，可通过`.env.example`中的`AI_*`参数配置；0及负数不是关闭限制的方式。额度拒绝不会增加计数；队列发布失败等已接受的尝试仍计数。数据库行锁保证并发请求不能绕过活跃任务限制，Redis不可用时不放行昂贵请求。

上传仅允许经内容头确认的常见栅格图像、UTF-8纯文本同域预览，HTML、SVG、PDF及未知格式强制下载并设置nosniff与sandbox CSP。对话过期或新建时，在同一数据库事务删除关联检查点，撤销对应摘要缓存；原有24小时有效期仍适用。

## 检查

```bash
uv run ruff format --check src tests migrations infra
uv run ruff check src tests migrations infra
uv run pytest -q
```

离线测试不连接云端，集成测试需要`RUN_INTEGRATION=1 POSTGRES_DB=ai_agent_test`及专用测试库，不能针对真实用户库执行。仅清理测试账号和独立Redis命名空间；默认异步任务改投随机测试队列，结束后只删除该队列。显式真实Worker回放继续使用各自的随机队列。独立部署见[部署指南](../docs/部署指南.md)，开源内容边界见[开源说明](../docs/开源说明.md)。
