# 安排儿前端

React 19 + TypeScript + Vite的中文手机H5，使用服务端HttpOnly Cookie会话。包含待办、日程、清单、餐食、材料、家庭空间和AI对话，AI写操作在确认卡中确认。

## 启动

需要Node.js 22和已配置的后端。

```bash
npm ci
npm run dev
```

访问 `http://localhost:9988`。默认将 `/api` 代理到 `http://127.0.0.1:8000`；可用 `API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev` 调整。后端Origin白名单应与访问来源一致。

```bash
npm run format:check
npm run lint
npm run build
```

生产产物在dist，由自己的HTTPS站点提供，API保持同源。配置与迁移见[部署指南](../docs/部署指南.md)。

## 浏览器测试

先启动Vite，再运行 `npm run test:behavior`。默认使用系统Chrome；测试拦截API并使用合成数据，不替代真实后端和权限验收。其他交互回归可用 `npx playwright test tests/<name>.spec.ts` 单独运行。

真实服务测试只有显式设置相应`LIVE_*`开关才运行，需要独立账号和专用测试环境。不要把登录Cookie、真实录音、截图或Playwright trace提交到公开仓库。
