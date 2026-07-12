# QuakeRelay

个人自部署的中国大陆地震信息查看与提醒服务。QuakeRelay 从 Wolfx 获取中国地震台网及四川、福建、重庆等预警源的数据，合并为统一事件，为多个关注地点估算烈度，并将可能有感的事件推送到 Telegram 或通用 Webhook。

> **安全提示：** Wolfx 是第三方数据服务，QuakeRelay 的烈度结果也是模型估算。本项目不是官方预警渠道，不承诺秒级送达或必达，不能作为唯一的生命安全保障手段。请始终以官方发布为准。

## 功能

- Wolfx `all_eew` WebSocket 聚合接收、心跳检测、自动重连及 HTTP 定时补偿。
- 中国大陆多源报告合并，完整保留原始报文、来源和事件版本。
- 独立数据源状态页，区分聚合连接、逻辑实时源和 HTTP 补偿源，可展开查看最近一次原始 JSON。
- Wolfx 全国高温、降雨和风速 Top 10 实况排行，小时快照长期保存并可按日期查询。
- 多个关注地点及高德地图地址搜索、选点和事件展示。
- 中国东、西部分区烈度衰减估算，采用偏向少漏报的保守策略。
- Telegram 机器人和固定 JSON Webhook，多端点、加密凭据、测试推送、幂等键和持久化重试。
- 长期事件查询、来源状态、通知记录和 SQLite 在线备份。
- 单家庭实例，无内置账号体系，由反向代理、VPN 或内网负责访问控制。

## 快速部署

要求：Docker Engine、Docker Compose，以及一个可用的高德地图 JS API Key 和安全密钥。

官方容器镜像由 GitHub Actions 自动构建，支持 `linux/amd64` 和 `linux/arm64`：

```bash
docker pull ghcr.io/yetianxingshi/quakerelay:latest
```

```bash
cp .env.example .env
```

生成 Webhook 请求头加密密钥：

```bash
docker run --rm python:3.12-slim sh -c "pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
```

将结果写入 `.env` 的 `QUAKERELAY_SECRET_KEY`，再配置：

- `QUAKERELAY_AMAP_JS_KEY`：高德地图 JS API Key。
- `QUAKERELAY_AMAP_SECURITY_CODE`：高德安全密钥。
- `QUAKERELAY_PUBLIC_BASE_URL`：外部访问地址。

直接使用 GHCR 镜像启动：

```bash
docker compose pull
docker compose up -d
```

如果希望所有环境变量都直接写在 Compose 文件中，使用 `compose.online.yaml`，先替换其中的密钥、高德 Key 和公网地址，然后执行：

```bash
mkdir -p data
docker compose -f compose.online.yaml pull
docker compose -f compose.online.yaml up -d
```

该部署文件使用 `./data:/data` 目录映射，SQLite 数据库和备份会保存在执行命令目录下的 `data/` 中。

也可以从当前源码本地构建：

```bash
docker compose up -d --build
```

可通过 `.env` 的 `QUAKERELAY_IMAGE` 选择固定版本，例如：

```dotenv
QUAKERELAY_IMAGE=ghcr.io/yetianxingshi/quakerelay:v1.0.0
```

推送到 `main` 时发布 `latest` 和 `sha-*` 标签；推送 `v*` Git 标签时同时发布对应版本标签。

默认只监听宿主机 `127.0.0.1:8080`。请在前面配置带身份认证和 TLS 的反向代理，或仅通过 VPN/内网访问。应用自身没有登录保护。

- Web 页面：`http://127.0.0.1:8080`
- OpenAPI：`http://127.0.0.1:8080/docs`
- 健康检查：`http://127.0.0.1:8080/api/v1/health`

## 运行机制

后端以单 Uvicorn worker 运行。它长期连接 `wss://ws-api.wolfx.jp/all_eew`，接收 `cenc_eew`、`sc_eew`、`fj_eew`、`cq_eew` 和 `cenc_eqlist`，处理 Wolfx 每分钟发送的 heartbeat，并自动重连。启动时通过各数据源的独立 WebSocket 地址依次取得最近快照；HTTP 快照每分钟核对一次，用于断线恢复和漏报补偿。

“Wolfx WebSocket 连接”仅表示底层聚合连接和心跳状态，不计入数据源数量。数据源状态页会分别保存 WebSocket 与 HTTP 通道最近一次收到的原始 JSON。

所有坐标在数据库中统一保存为 WGS-84；高德地图的 GCJ-02 坐标只在输入和展示边界转换。烈度估算结果会记录模型版本，便于未来模型升级后复核历史结果。

SQLite 必须放在本机 Docker 卷中，不要将数据库文件放在 NFS 或 SMB 网络文件系统。应用固定使用 WAL 模式和单 worker。

## 推送渠道

每个渠道可分别开启“地震”和“气象”通知。新建渠道和升级前已存在的渠道默认仅开启地震通知，气象通知需要手动开启。

### Telegram 机器人

在“推送渠道”页面选择“添加 Telegram”，填写：

- Bot Token：通过 [@BotFather](https://t.me/BotFather) 创建机器人后获得。
- Chat ID：私聊通常为正整数，群组通常以 `-100` 开头，公开频道也可使用 `@username`。
- Topic ID：仅发送到论坛群组的指定 Topic 时填写。
- 静默发送：启用后 Telegram 不播放通知声音。

Bot Token 使用 Fernet 加密保存在 SQLite 中，API 和页面都不会将 Token 返回。Telegram 发送复用现有持久化队列、10 次重试、发送记录和测试功能。实现使用官方 [`sendMessage`](https://core.telegram.org/bots/api#sendmessage) 接口。

### 通用 Webhook

每个端点使用 `POST application/json`。可配置自定义请求头、超时和启用状态；请求头在数据库中使用 `QUAKERELAY_SECRET_KEY` 加密。投递附带 `Idempotency-Key`，失败最多重试 10 次，之后可在页面手动重发。

地震通知载荷概要：

```json
{
  "schema_version": "1.0",
  "notification_id": "uuid",
  "kind": "earthquake.initial",
  "sent_at": "2026-07-12T12:00:03Z",
  "delayed": false,
  "event": {
    "event_id": "uuid",
    "revision": 1,
    "status": "preliminary",
    "origin_time": "2026-07-12T12:00:00Z",
    "hypocenter": "四川某地",
    "latitude": 30.1,
    "longitude": 103.2,
    "magnitude": 4.8,
    "depth_km": 10,
    "sources": ["cenc_eew", "sc_eew"]
  },
  "impacts": [
    {
      "location_id": "uuid",
      "name": "家",
      "distance_km": 82.4,
      "estimated_intensity": 3.2,
      "intensity_level": 4,
      "confidence": "high"
    }
  ],
  "changes": {}
}
```

`kind` 还可能为 `earthquake.update`、`earthquake.cancelled`、`system.source_down`、`system.source_recovered` 或 `system.test`。

## 备份与升级

通过 API 创建 SQLite 在线备份：

```bash
curl -X POST http://127.0.0.1:8080/api/v1/backups
```

备份位于 Docker 卷的 `/data/backups`。恢复前停止容器，将备份文件复制为 `/data/quakerelay.db`，再启动容器。升级时先备份，然后重新构建；应用启动时自动执行 Alembic 迁移。

## 本地开发

后端需要 Python 3.12+：

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
QUAKERELAY_ENABLE_COLLECTOR=false uvicorn quakerelay.main:app --app-dir backend --reload --port 8080
```

前端：

```bash
cd frontend
npm install
npm run dev
```

验证：

```bash
pytest
ruff check backend
mypy backend/quakerelay
cd frontend && npm test && npm run lint && npm run build
```

## 数据和模型说明

- 数据接口：[Wolfx Open API](https://wolfx.jp/apidoc_zh)
- WebSocket 调用说明：[Wolfx WebSocket API](https://wolfx.jp/wsapi_zh)
- 首版烈度实现位于 `backend/quakerelay/intensity.py`，模型版本为 `china-regional-attenuation-2000-v1`。
- 预计烈度达到Ⅱ度即触发；300 km 是重点范围而非硬边界，模型最大计算距离为 1,000 km。
- 模型输入不完整但事件可能影响 300 km 内关注点时，采用保守的“可能有感”通知。

## 气象排行说明

- 气象数据来自 Wolfx `weather_rank.json`，是全国实况 Top 10 排行，不是所有城市的完整天气。
- 系统每 5 分钟检查一次，将接口中尚未保存的最近小时快照入库；同一小时按内容哈希去重。
- 省级行政区相同，且排行站点名与关注地点的城市或区县名去除常见后缀后互相包含时，视为匹配。
- 只要已启用关注地点进入最新小时任一排行，就向已订阅气象的渠道发送通知；同一小时最多一条，次小时仍上榜可再次通知。
- 启动时仅对距当前时间不超过 2 小时的最新榜单补发，更旧数据只入库。
- 新关注地点会从高德选点结果保存省、市、区县。升级前已存在的地点没有结构化行政区，需删除后重新添加才能参与气象匹配。
- 删除关注地点是不可恢复的永久删除：该地点的所有历史地震影响记录会同时清除，已保存的地震通知载荷也会移除该地点。

## 许可与责任

部署者需要自行确认 Wolfx 和高德地图的服务条款、配额及 Key 使用限制。应用会长期保存第三方原始报文和关注地点，请将数据卷、备份与反向代理妥善保护。
