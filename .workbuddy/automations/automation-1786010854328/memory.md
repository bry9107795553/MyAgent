# MyAgent Hackathon automation — 2026-08-06 18:08 运行

## 执行摘要

云端实例 u-3004-abffcef6 公网可达，流水线恢复运行。

## 本轮修复 (12 commits)

1. **coach 超时**: dispatcher_config.json 120→180s
2. **前端构建崩溃**: 修复 4 个被缓存掩盖的 SFC 编译 bug (unicode/iframe/textarea/preview-body)
3. **工具调用去重**: 32次重复 → 1次 (_dedup_tool_calls + 同路径file_write去重)
4. **工作组列表页**: 新建 WorkgroupView.vue
5. **模型名适配**: App.vue → /api/system
6. **分类器补全**: 6 类任务路由修复 (修改/长写作/总结/分析/创意/文件阅读)

## 当前状态

- 云端公网: `rc-8aa32ba6c92df381` (每次 start.sh 会变)
- P0 待办: S7测速, 录视频, 提交
- 截止: 2026-08-06 23:59
