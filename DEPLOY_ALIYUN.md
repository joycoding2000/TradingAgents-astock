# 阿里云 ECS 部署指南（纯 IP + Streamlit 登录页）

面向运维者：在阿里云服务器上部署 TradingAgents-Astock，最终用户只需浏览器访问 `http://<公网IP>:8080` 输访问口令即可使用，**零安装零配置**。

> 适用于：服务器已有 nginx 在 80 端口跑其他 web app（如 TradeDoctor），TradingAgents 走**新端口 8080**，互不干扰。

---

## 架构

```
用户浏览器 ──http://公网IP:8080──▶ 阿里云安全组(开放8080)
                                     │
                            宿主机 nginx (listen 8080) 反代 -> Streamlit 登录页
                                     │ proxy_pass + WebSocket
                            127.0.0.1:8501  ← 仅本机，公网扫不到
                                     │
                            web 容器(streamlit) ──▶ .env统一API Key ──▶ 远程LLM
```

**安全要点**：容器端口绑 `127.0.0.1:8501:8501`（不是 `8501:8501`），公网扫描 8501 访问不到，**必须经 8080 的 Streamlit 登录页认证**（口令由 `.env` 的 `ACCESS_TOKEN` 控制）。

---

## 服务器环境要求

- 阿里云 ECS，Alibaba Cloud Linux 3 / CentOS 7+ / Ubuntu 均可
- 已装 nginx（宿主机直装，非容器）
- 2 核 4G 起（调远程 LLM，无需 GPU）；1–3 人用足够
- 安全组开放 **8080**（80 已开就别动）

---

## 部署步骤

### 1. 安装 Docker（Alibaba Cloud Linux 3）

```bash
# 用阿里云镜像源装 docker-ce（国内快）
dnf install -y dnf-plugins-core
dnf config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
sed -i 's/$releasever/8/g' /etc/yum.repos.d/docker-ce.repo   # Alibaba Cloud Linux 3 兼容 RHEL 8
dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker
docker --version && docker compose version
```

> **务必配置镜像加速器**：国内服务器访问 Docker Hub 会超时，build 时拉 `python:3.12-slim` 会失败。装完 Docker 后立即执行：
> ```bash
> mkdir -p /etc/docker
> cat > /etc/docker/daemon.json <<'EOF'
> {
>   "registry-mirrors": [
>     "https://docker.1panel.live",
>     "https://docker.m.daocloud.io",
>     "https://hub-mirror.c.163.com",
>     "https://docker.mirrors.ustc.edu.cn"
>   ]
> }
> EOF
> systemctl restart docker
> ```
> 若以上公共加速器均失效（2026 年部分已关停），登录阿里云控制台 -> 容器镜像服务 -> 镜像加速器，领取账号专属的 `https://<id>.mirror.aliyuncs.com` 地址替换上方。

### 2. 拉取项目代码

```bash
cd /opt
git clone https://github.com/joycoding2000/TradingAgents-astock
cd TradingAgents-astock
```

> 若 GitHub 访问慢，可用 gitee 镜像或本地 rsync 上传。

### 3. 配置 API Key（服务器统一配，所有用户共用）

```bash
cp .env.example .env
vi .env
# 填一个供应商的 Key，例如：
# DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

推荐国内直连：DeepSeek / MiniMax / 通义 / 智谱（任选一）。用户在 Web UI 侧边栏选对应供应商即可，无需各自填 Key。

**设置访问口令**（防止陌生人盗用 API Key）：在同一 `.env` 文件里设 `ACCESS_TOKEN`，例如：
```
ACCESS_TOKEN=mySecretPass2026
```
设了非空值后，Web UI 会显示美观登录页，用户需输此口令才能进入；不设则无登录页（仅本地开发用）。

### 4. 放置 nginx 配置

```bash
# 放配置文件（已去掉 Basic Auth，认证由 Streamlit 登录页处理）
sudo cp nginx/tradingagents.conf /etc/nginx/conf.d/

# 校验并生效（nginx -t 失败不会影响线上 80 端口）
sudo nginx -t && sudo systemctl reload nginx
```

> 认证说明：访问控制由 Streamlit 应用内登录页处理（读 `ACCESS_TOKEN` 环境变量），nginx 仅做反向代理 + WebSocket 透传，不再做 Basic Auth。务必先在 `.env` 设好 `ACCESS_TOKEN` 再对外开放 8080，否则 Web UI 将无认证暴露。

### 5. 启动 TradingAgents 容器

```bash
docker compose -f docker-compose.cloud.yml up -d --build
# 首次构建约 5–10 分钟（下载依赖），后续启动几秒
```

### 6. 阿里云安全组开放 8080

阿里云控制台 -> ECS -> 安全组 -> 入方向规则 -> 添加：
- 端口范围：`8080/8080`
- 授权对象：`0.0.0.0/0`（或限你的 IP）

### 7. 访问

浏览器打开 `http://<公网IP>:8080`，输入访问口令 -> 进 Streamlit UI -> 选股票 + 模型 -> 「开始分析」。

---

## 运维命令

| 操作 | 命令 |
|------|------|
| 查看日志 | `docker compose -f docker-compose.cloud.yml logs -f web` |
| 重建容器（改 .env 后） | `docker compose -f docker-compose.cloud.yml up -d` |
| 停止 | `docker compose -f docker-compose.cloud.yml down` |
| 改访问口令 | 改 `.env` 的 `ACCESS_TOKEN` 后 `docker compose -f docker-compose.cloud.yml up -d` |

### 一键更新脚本（推荐）

`scripts/update-server.sh` 封装了"同步代码 + 重启容器 + 打印日志"全流程。改完代码在**项目根目录**执行：

```bash
# 首次使用前设置服务器地址（写入 ~/.bashrc 永久生效）
export TA_SERVER=root@你的服务器IP

bash scripts/update-server.sh          # 改了 Python 代码 -> restart web
bash scripts/update-server.sh --env    # 改了 .env         -> up -d 重建容器
bash scripts/update-server.sh --build  # 改了依赖          -> up -d --build 重建镜像
```

**关键区别**（记性不好重点记这条）：
- **代码变了** → 默认（`restart web`，快，几秒）
- **.env 变了** → `--env`（必须 `up -d`，`restart` 不重读 env_file 是常见坑）
- **依赖变了** → `--build`（`up -d --build`，重建镜像几分钟）

脚本不硬编码服务器地址（避免泄露到公开 repo），从 `TA_SERVER` 环境变量读，未设会报错退出。rsync 优先（增量），Windows 无 rsync 时自动回退 tar 全量打包。改了 nginx 配置仍需手动（见第 4 步）。

---

## 东财 push2 代理配置（云部署重要）

**问题**：阿里云等 IDC 服务器的 IP 会被东方财富 push2 行情接口封禁（`push2.eastmoney.com` / `push2his.eastmoney.com`，建连后 `RemoteDisconnected`），导致：
- 游资追踪师"个股主力资金净流入"缺失（`get_fund_flow`）
- 基本面/游资"行业横向对比"失败（`get_industry_comparison`）

`datacenter-web`（龙虎榜/股东/解禁）、mootdx/新浪（K 线）、腾讯（PE/PB）等非 push2 源不受影响。本地开发无此问题（IP 非 IDC）。

**解决**：在服务器 `.env` 设 `EM_HTTP_PROXY` 让东财请求走代理出口绕过：

```bash
cd /opt/TradingAgents-astock
vi .env
# 加一行（替换为你的代理地址）：
EM_HTTP_PROXY=http://user:pass@proxy.example.com:8080
```

部署（`.env` 变了必须 `--env` 重建容器重读）：

```bash
bash scripts/update-server.sh --env
```

**代理要求**：
- 国内**住宅/移动 IP** 代理最佳（IDC IP 可能也被东财封）
- HTTP/HTTPS 代理均可，支持账号密码认证
- 代理需自备（如快代理、芝麻代理、阶云等付费住宅代理）

**验证**：进容器实测资金流接口应返回数据：

```bash
docker exec tradingagents-astock-web-1 python -c "
from tradingagents.dataflows import a_stock
print(a_stock.get_fund_flow('601689','2026-07-15')[:200])
"
```

未配代理时，资金流/行业对比仍缺失，但门控矛盾修正与 prompt 假缺失消除（v0.2.22）独立生效，不再出现"C vs A 矛盾"和龙虎榜误标。

## 常见问题

**Q: 访问 8080 一直转圈 / 显示 "Please wait"？**
检查 nginx 是否透传了 WebSocket 头（`Upgrade` / `Connection`）。`tradingagents.conf` 已配。若仍不行，看容器日志：`docker compose -f docker-compose.cloud.yml logs web`。

**Q: 访问 8080 报 502 Bad Gateway？**
web 容器没起来或还没就绪。`docker compose -f docker-compose.cloud.yml ps` 看状态，`curl http://127.0.0.1:8501` 本机测试。

**Q: 改了 .env 不生效？**
.env 在容器**创建**时读入环境变量。改完必须用 `up -d` 重建容器（`restart` 只重启进程、**不重读 .env**，这是常见坑）：`docker compose -f docker-compose.cloud.yml up -d`。

**Q: 端口 8080 被占？**
改 `nginx/tradingagents.conf` 的 `listen 8080` 为其他端口（如 8088），同步改阿里云安全组。compose 不用改（固定 127.0.0.1:8501）。

**Q: 导出 PDF 报"未找到中文字体"？**
v0.2.12 起 Dockerfile 已内置中文字体。重新构建：`docker compose -f docker-compose.cloud.yml build web`。

**Q: 会影响服务器上现有的 web app 吗？**
不会。TradingAgents 只新增一个 `listen 8080` 的 server 块，不动现有 `tja.conf` 的 80 端口。nginx reload 前 `nginx -t` 校验，失败不生效。

---

## 风险提示

- **纯 HTTP：口令明文传输**。Streamlit 登录页本身不加密，如需更安全，后续加域名 + Let's Encrypt HTTPS。
- **API Key 所有用户共享**你的额度费用，注意监控用量。
- Streamlit 单进程：多人同时分析会串行排队。

---

## 进阶

- 本地开发/部署见根目录 `README.md` 与 `DEPLOY_WINDOWS.md`
- 仅供学习研究，不构成投资建议
