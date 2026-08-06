# 上机速查表（排到实例后照着做）

> 排到 Radeon Cloud 实例后打开的第一个文件。所有命令可**直接复制粘贴**。
> 目标：AMD Radeon PRO W7900 / 48GB / ROCm 7.2 / Ubuntu 22.04
> **时间预算**：环境确认 2 分钟 → 部署 40-60 分钟 → 测试 30 分钟 → 录屏 15 分钟

---

## 名词速查

| 你会看到 | 意思 |
|---|---|
| `$` 或 `#` 开头 | 提示符，**不要**复制它 |
| `~` | 家目录 = `/home/用户名` |
| `sudo` | 管理员权限 |
| `Ctrl + C` | 中止当前命令 |
| `tail -f xxx.log` | 实时看日志（Ctrl+C 退出，不影响服务） |

---

## 0. 确认环境（2 分钟）

```bash
# 看 GPU 型号
rocminfo | grep -E "Marketing Name|gfx" | head -6

# 看显存
rocm-smi --showmeminfo vram

# 看 ROCm 版本
cat /opt/rocm/.info/version 2>/dev/null || dpkg -l | grep rocm-core
```

**预期**：`W7900` + `gfx1100` + `48GB` + `ROCm 7.2`

> 不是 W7900？显存不足 30GB？→ 销毁实例重新排队。

---

## 1. 一键部署

```bash
# 拉代码
git clone https://github.com/bry9107795553/MyAgent.git && cd MyAgent

# 一键安装（自动下载 llama.cpp 预编译版 + GGUF 模型 + 构建前端）
bash install.sh

# 安装过程最慢的两步：
#   - 下载 llama.cpp 预编译包 (~127MB, 1-3 分钟)
#   - 下载 GGUF 模型 (~9GB, 5-30 分钟取决于网速)
```

---

## 2. 启动服务

```bash
bash start.sh
```

**预期**：
```
[0/4] 清理残留进程... ✓ 已清理
[1/4] 启动 llama.cpp...  ✓ llama-server 就绪 (42s)
[2/4] 启动 FastAPI 后端...  ✓ FastAPI 就绪 (3s)
[3/4] 启动 Nginx...  ✓ Nginx 就绪
[4/4] 外部访问隧道...  ✓ 公网: https://rc-xxxx.xxx
```

---

## 3. 健康检查

```bash
curl -s http://localhost:8000/v1/models     # llama-server
curl -s http://localhost:8080/api/health    # FastAPI
curl -s -o /dev/null -w "%{http_code}" http://localhost/  # Nginx → 200
```

三个都通才算成功。

---

## 4. 浏览器打开前端

`start.sh` 成功后会自动打印公网 URL（`https://rc-xxxx.xxx`）。在你自己电脑浏览器打开。

- 输入"你好" → 有回复
- 输入"开发一个待办事项" → 右侧流水线开始执行
- 右侧 GPU 监控：`watch -n 1 rocm-smi`

---

## 5. 故障排查

### 显存不足 OOM
```bash
bash stop.sh
pkill -f llama-server
sleep 3 && bash start.sh
```

### 模型文件损坏
```bash
# 验证 GGUF magic
head -c 4 ~/llama.cpp/models/qwen2.5-14b-instruct-q4_k_m.gguf
# 必须打印 GGUF 四个字母
```

### 端口被占
```bash
bash stop.sh
pkill -f llama-server; pkill -f uvicorn; sudo pkill nginx
sleep 3 && bash start.sh
```

### 日志在哪
| 日志 | 路径 |
|------|------|
| 部署 | `~/setup.log`（如果用 setup_amd_cloud.sh） |
| llama-server | `/tmp/llama.log` |
| 后端 | `/tmp/backend.log` |
| Nginx | `/var/log/nginx/error.log` |

---

## 6. 切换模型

部署默认使用 Qwen2.5-14B。如果用 Qwen3-30B-A3B：

```bash
# 编辑 backend/.env
LLAMA_MODEL=/path/to/Qwen3-30B-A3B.gguf
# 重启
bash stop.sh && bash start.sh
```

---

## 附：端口表

| 端口 | 服务 | 检查 |
|------|------|------|
| 80 | Nginx（前端 + 反向代理） | `curl http://localhost/` |
| 8080 | FastAPI 后端 | `curl http://localhost:8080/api/health` |
| 8000 | llama-server（推理） | `curl http://localhost:8000/v1/models` |
