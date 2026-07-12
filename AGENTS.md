# QuakeRelay 协作指南

## 项目定位

QuakeRelay 是面向单家庭、自部署场景的中国大陆地震信息查看与通知服务。它不是官方预警系统，不承诺秒级送达或必达。任何功能和文案都必须保留这一安全边界。

## 目录结构

- `backend/quakerelay/`：FastAPI、SQLAlchemy、Wolfx 采集、多源融合、烈度估算与通知队列。
- `backend/alembic/`：SQLite 数据库迁移；模型变更必须同时提供迁移。
- `backend/tests/`：后端测试。
- `frontend/src/`：React、TypeScript、Ant Design 页面与展示辅助函数。
- `compose.yaml`、`Dockerfile`：生产部署入口。

## 开发约束

- 面向用户的界面文案使用中文；稳定的接口值和数据库枚举保持英文，通过 `frontend/src/presentation.ts` 映射展示。
- 数据源名称采用“中文主名称（技术标识）”，例如“中国地震台网预警（cenc_eew）”。
- `wolfx_ws` 是 `all_eew` 聚合连接通道，不是地震数据源，不得计入数据源数量。
- 长期只维持一条 `all_eew` 聚合连接。启动快照通过各数据源的独立 WebSocket 端点获取，HTTP 每分钟补偿。
- 气象排行每 5 分钟轮询，以北京时间小时为唯一快照；地震与气象通知必须遵守渠道各自的订阅开关。
- 时间在后端按 UTC 保存和传输，前端统一显示北京时间。
- 坐标在数据库中保存为 WGS-84，高德地图输入和展示边界使用 GCJ-02。
- 不要在日志、API、测试夹具或提交中暴露 Fernet 密钥、Telegram Bot Token、Webhook 密钥或用户的 `.env`。
- 保持单 Uvicorn worker 和 SQLite WAL；不要在未重新设计并发模型前增加 worker。
- 修改事件融合、通知条件或烈度模型时，必须补充测试并说明对漏报/重复通知的影响。

## 验证命令

```bash
pytest
ruff check backend
mypy backend/quakerelay
cd frontend
npm test
npm run lint
npm run build
```

提交前至少运行与改动相关的检查。涉及采集器时，还应确认 `/api/v1/health` 和 `/api/v1/sources` 正常，但测试不得向真实推送渠道发送消息。

## 数据库与部署

- 新增或修改持久化字段时，在 `backend/alembic/versions/` 创建可升级、可降级的迁移。
- 不提交 `.env`、SQLite 文件、`data/`、备份、`node_modules/` 或前端构建产物。
- 部署升级前先备份 `/data/quakerelay.db`，再执行 `docker compose up -d --build`；应用启动时自动运行 Alembic 迁移。
