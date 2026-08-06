# 提交文件清单

> 评审 clone 后，以下文件最重要。其余为开发过程产物，不影响运行。

---

## 🔴 必读（评委第一眼）

| 文件 | 内容 |
|------|------|
| `README.md` | 项目介绍 + 一句话 QuickStart |
| `PROJECT_SPEC.md` | 技术规格说明 |
| `QUICKSTART_CLOUD.md` | 云端部署速查表（上机照做） |
| `docs/项目说明文档.md` | 中文项目说明书 |
| `docs/PROJECT_DOCUMENTATION.md` | 英文技术文档 |

## 🔵 辅助材料

| 文件 | 内容 |
|------|------|
| `docs/提交指南.md` | 提交前自检清单 |
| `docs/演示视频分镜.md` | 录屏脚本 |
| `ppt_competition/` | 路演 PPT |
| `reports/test-plan.md` | 测试方案 |
| `reports/role-audit.md` | 19 角色审计 |

## 🟢 运行必需

```
backend/  frontend/  data/
install.sh  start.sh  stop.sh  switch_model.sh
nginx.conf  backend/requirements.txt  backend/.env.template
```

## ⚪ 内部文档（不需提交给评委）

| 文件 | 说明 |
|------|------|
| `HANDOFF.md` | 团队内部移交摘要 |
| `reports/storage-audit.md` | 存储链路审计 |
| `reports/architecture-audit.md` | 架构审计 |
| `reports/backend-chain-analysis.md` | 调用链分析 |
| `reports/retrieval-upgrade.md` | 未来优化建议 |
| `designs/chat-v2.html` | UI 设计草稿 |
| `.workbuddy/` | 本地开发工具 |
| `tests/` | 开发者测试 |
