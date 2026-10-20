# 安排儿 · ai-agent

中文 H5 家庭生活助手，使用 React、FastAPI、LangGraph 和 Celery。支持待办、日程、清单、餐食、材料、语音备忘、家庭共享，以及需要确认后执行写操作的 AI 对话。

AI通过服务端工具白名单读取数据；写操作先展示计划，用户确认后重新检查账号和资源权限。长对话摘要在回答结束后后台生成，下一轮复用或有界等待，不把历史回答当作当前业务证据。

| 目录 | 内容 |
| --- | --- |
| [frontend](frontend/README.md) | React 19、TypeScript、Vite 手机H5 |
| [backend](backend/README.md) | Python 3.14、FastAPI、LangGraph、Celery |
| [部署指南](docs/部署指南.md) | 自有服务器、配置、迁移、三个应用进程 |
| [开源说明](docs/开源说明.md) | 公开快照、隐私与第三方服务边界 |

## 开始使用

准备 Node.js 22、Python 3.14、uv，以及你自己的PostgreSQL/pgvector、Redis和RabbitMQ。Mac用于应用开发，基础服务放在自有Linux服务器。

1. 按后端说明复制 `backend/.env.example`，填入自己的服务配置和随机秘密。
2. 执行 `uv sync --locked`、`uv run alembic upgrade head`，启动API、回答Worker、摘要Worker。
3. 在frontend执行 `npm ci`、`npm run dev`，访问 `http://localhost:9988`。
4. 注册需要配置SMTP及验证码秘密；AI对话、向量检索和转写分别需要相应服务配置。没有配置的能力明确返回不可用。

不提供共享服务器、默认账号或预置生产凭据。费用由部署者使用的模型、邮件和云服务决定。开发过程的完整调研与部署记录不属于公开快照。

## 检查与贡献

根目录 `make format-check` 检查格式，`make lint` 检查前端ESLint；后端另执行Ruff和pytest。具体命令见 [贡献指南](CONTRIBUTING.md)。云端及真实模型测试默认跳过，需要专用测试环境显式启用；离线检查通过不代表真实模型业务验收通过。

安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。项目采用 [MIT](LICENSE)，第三方依赖遵循各自许可证；第三方调研截图及私人记录不随公开快照分发。
