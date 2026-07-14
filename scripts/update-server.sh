#!/usr/bin/env bash
# 一键更新服务器代码（阿里云 ECS）
#
# 用法（在项目根目录执行）：
#   bash scripts/update-server.sh          # 改了 Python 代码 -> restart web
#   bash scripts/update-server.sh --env    # 改了 .env         -> up -d（重建容器重读 env）
#   bash scripts/update-server.sh --build  # 改了依赖          -> up -d --build（重建镜像）
#
# 改了 nginx 配置请手动操作，见 DEPLOY_ALIYUN.md 第4步。
# 原理：代码已挂载进容器（- .:/home/appuser/app），改代码 restart 即生效，无需 rebuild。

set -e

# 服务器地址从环境变量读，避免硬编码 IP 泄露到公开仓库
# 用法：export TA_SERVER=root@你的服务器IP （建议用专用 deploy 用户代替 root）
# 写入 ~/.bashrc 可永久生效。
SERVER="${TA_SERVER:-}"
if [ -z "$SERVER" ]; then
  echo "错误：未设置 TA_SERVER 环境变量。" >&2
  echo "请执行: export TA_SERVER=root@你的服务器IP" >&2
  exit 1
fi
REMOTE_DIR="/opt/TradingAgents-astock"
COMPOSE="docker compose -f $REMOTE_DIR/docker-compose.cloud.yml"

# 切到项目根目录（本脚本位于 scripts/ 下）
cd "$(dirname "$0")/.."

# 同步时排除的路径（rsync 与 tar 共用同一语法）
EXCLUDES=(
  --exclude='.git' --exclude='.venv' --exclude='__pycache__'
  --exclude='*.pyc' --exclude='.env' --exclude='results'
  --exclude='eval_results' --exclude='.claude' --exclude='node_modules'
  --exclude='.pytest_cache' --exclude='.mypy_cache' --exclude='.dockerignore'
)

# 根据参数决定容器重启方式
ACTION="restart web"
case "$1" in
  --env)   ACTION="up -d"          ;;  # .env 改了，需重建容器重新注入环境变量
  --build) ACTION="up -d --build"  ;;  # Dockerfile/pyproject 依赖改了，需重新构建镜像
esac

echo "============ 同步代码到 $SERVER:$REMOTE_DIR ============"
if command -v rsync >/dev/null 2>&1; then
  # rsync 增量同步（只传变化的文件），--delete 保持与本地完全一致
  # .env 被 exclude，--delete 不会删除服务器上已配的 .env
  rsync -avz --delete "${EXCLUDES[@]}" ./ "$SERVER:$REMOTE_DIR/"
else
  # Windows git bash 可能没装 rsync，回退到 tar 全量打包
  echo "(rsync 不可用，改用 tar 方式)"
  TARBALL="/tmp/ta-sync-$$.tar.gz"
  tar czf "$TARBALL" "${EXCLUDES[@]}" .
  scp "$TARBALL" "$SERVER:/tmp/"
  ssh "$SERVER" "cd $REMOTE_DIR && tar xzf /tmp/$(basename "$TARBALL") && rm -f /tmp/$(basename "$TARBALL")"
  rm -f "$TARBALL"
fi

echo ""
echo "============ $COMPOSE $ACTION ============"
ssh "$SERVER" "$COMPOSE $ACTION"

echo ""
echo "等待 streamlit 启动..."
sleep 6

echo ""
echo "============ 容器日志（最后15行）============"
ssh "$SERVER" "$COMPOSE logs --tail 15 web"

echo ""
echo "============ ✅ 更新完成 ============"
echo "访问: http://${SERVER#*@}:8080"
echo "改 .env 用: bash scripts/update-server.sh --env"
echo "改依赖用:  bash scripts/update-server.sh --build"
