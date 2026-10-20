# 参与贡献

欢迎提交问题和 Pull Request。涉及安全漏洞时请先阅读 [SECURITY.md](SECURITY.md)，不要在公开 Issue 中披露利用细节或个人数据。

1. 阅读根目录及对应前后端目录的 AGENTS.md；行为变更同步需求与 OpenSpec。
2. 使用 Node.js 22、Python 3.14 和 uv；按锁文件安装，不上传 `.env`、密钥、真实录音、用户截图或数据库备份。
3. 后端执行 `uv run ruff format --check src tests migrations infra`、`uv run ruff check src tests migrations infra`、`uv run pytest -q`。
4. 前端执行 `npm ci`、`npm run format:check`、`npm run lint`、`npm run build`。
5. 测试使用合成数据。云端集成测试必须连接专用 `ai_agent_test` 数据库及独立 Redis 命名空间，不能清空共享服务。Mac不启动基础服务容器。
6. PR说明问题、改动、验证结果及未验证项；UI变更附合成数据截图，不提交真实个人信息。

CI默认只运行离线检查。集成或真实模型测试需维护者在隔离环境显式启用，不能给外部PR注入生产密钥。新文件遵守 Python 300行及TSX 200行限制。

贡献者需确认提交内容有权按项目MIT许可证分发；第三方依赖及素材保留其原始授权。
