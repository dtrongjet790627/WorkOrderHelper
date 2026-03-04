#!/usr/bin/env bash
# =============================================================================
# deploy.sh - 工单小管家部署脚本
# 用途：将本地代码同步到165/168服务器并重启服务
# 运行环境：Git Bash (Windows)
# 用法：
#   ./deploy.sh         # 部署到所有服务器（默认）
#   ./deploy.sh all     # 部署到所有服务器
#   ./deploy.sh 165     # 仅部署到165服务器
#   ./deploy.sh 168     # 仅部署到168服务器
#
# 注意：脚本依赖SSH免密登录，确保本机 ~/.ssh/id_rsa 已配置到目标服务器
#       如SSH需要密码，可使用 ssh-copy-id 或参考 .claude/servers.md
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 服务器配置
# ---------------------------------------------------------------------------

# 165服务器（acc-common）- Python版工单小管家（端口5003，原exe已停用保留）
HOST_165="172.17.10.165"
USER_165="administrator"
REMOTE_DIR_165="D:/CustomApps/WorkOrderHelper_py/"
SERVICE_165="DT.TechTeam_WorkOrderHelper_py"

# 168服务器（acc-dx2）- 工单小管家
HOST_168="172.17.10.168"
USER_168="administrator"
REMOTE_DIR_168="D:/CustomApps/WorkOrderHelper/"
SERVICE_168="DT.TechTeam_WorkOrderHelper"

# ---------------------------------------------------------------------------
# 本地源码目录（脚本所在目录即为项目根目录）
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR"

# 需要同步的文件/目录
SYNC_ITEMS=(
    "app.py"
    "config"
    "models"
    "routes"
    "utils"
    "templates"
    "static"
)

# rsync排除规则
RSYNC_EXCLUDES=(
    "--exclude=__pycache__/"
    "--exclude=*.pyc"
    "--exclude=*.pyo"
    "--exclude=license.dat"
    "--exclude=license.lic"
    "--exclude=.env"
    "--exclude=*.env"
    "--exclude=.env.*"
    "--exclude=logs/"
    "--exclude=*.log"
    "--exclude=server.log"
)

# ---------------------------------------------------------------------------
# 颜色输出工具
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*"; }
log_section() { echo -e "\n${BLUE}=== $* ===${NC}"; }

# ---------------------------------------------------------------------------
# 核心函数
# ---------------------------------------------------------------------------

# 将 Windows路径（D:/foo/bar/）转换为 rsync 可用的远程路径
# 在 Git Bash 中访问 Windows SSH目标时用 /d/foo/bar/ 形式
# 同步代码到指定服务器（使用scp，不依赖rsync）
sync_to_server() {
    local host="$1"
    local user="$2"
    local remote_dir="$3"

    log_section "同步代码到 $user@$host:$remote_dir"

    # 检查SSH连通性
    log_info "检查SSH连通性..."
    if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "$user@$host" "exit" 2>/dev/null; then
        log_error "无法连接到 $host，请检查SSH配置（免密登录/网络）"
        return 1
    fi
    log_ok "SSH连接正常"

    # 逐项同步（scp -r 复制目录，scp 复制文件）
    local sync_ok=true
    for item in "${SYNC_ITEMS[@]}"; do
        local local_path="$SRC_DIR/$item"
        if [[ ! -e "$local_path" ]]; then
            log_warn "本地不存在，跳过: $item"
            continue
        fi

        log_info "同步: $item"
        if scp -r "$local_path" "$user@$host:$remote_dir" 2>&1; then
            log_ok "同步完成: $item"
        else
            log_error "同步失败: $item"
            sync_ok=false
        fi
    done

    if $sync_ok; then
        log_ok "全部文件同步完成 -> $host"
    else
        log_warn "部分文件同步失败，请检查上方错误信息"
        return 1
    fi
}

# 重启指定服务器上的Windows服务
restart_service() {
    local host="$1"
    local user="$2"
    local service="$3"

    log_section "重启服务 [$service] @ $host"

    # 检查服务是否存在
    log_info "检查服务是否存在: $service"
    local sc_query_result
    sc_query_result="$(ssh "$user@$host" "sc query \"$service\" 2>&1" || true)"

    if echo "$sc_query_result" | grep -qi "FAILED\|does not exist\|1060"; then
        log_warn "服务 [$service] 不存在或查询失败，跳过重启"
        log_warn "请通过以下命令手动确认服务名："
        log_warn "  ssh $user@$host \"sc query | findstr /i workorder\""
        return 1
    fi
    log_ok "服务存在: $service"

    # 停止服务
    log_info "停止服务: $service"
    local stop_result
    stop_result="$(ssh "$user@$host" "sc stop \"$service\" 2>&1" || true)"
    echo "  $stop_result"

    if echo "$stop_result" | grep -qi "STOP_PENDING\|STOPPED\|1062"; then
        log_ok "服务已停止（或已处于停止状态）"
    else
        log_warn "停止服务返回非预期结果，继续尝试启动..."
    fi

    # 等待服务完全停止
    log_info "等待服务完全停止（3秒）..."
    sleep 3

    # 启动服务
    log_info "启动服务: $service"
    local start_result
    start_result="$(ssh "$user@$host" "sc start \"$service\" 2>&1" || true)"
    echo "  $start_result"

    if echo "$start_result" | grep -qi "START_PENDING\|RUNNING"; then
        log_ok "服务启动成功: $service"
    else
        log_error "服务启动可能失败，请手动检查: ssh $user@$host \"sc query $service\""
        return 1
    fi
}

# 部署到165服务器
deploy_165() {
    log_section "开始部署 -> 165服务器 ($HOST_165)"
    local failed=0

    sync_to_server "$HOST_165" "$USER_165" "$REMOTE_DIR_165" || failed=1

    if [[ $failed -eq 0 ]]; then
        restart_service "$HOST_165" "$USER_165" "$SERVICE_165" || failed=1
    else
        log_warn "同步失败，跳过重启服务"
    fi

    if [[ $failed -eq 0 ]]; then
        log_ok "165服务器部署完成"
    else
        log_error "165服务器部署存在错误，请检查上方日志"
        return 1
    fi
}

# 部署到168服务器
deploy_168() {
    log_section "开始部署 -> 168服务器 ($HOST_168)"
    local failed=0

    sync_to_server "$HOST_168" "$USER_168" "$REMOTE_DIR_168" || failed=1

    if [[ $failed -eq 0 ]]; then
        restart_service "$HOST_168" "$USER_168" "$SERVICE_168" || failed=1
    else
        log_warn "同步失败，跳过重启服务"
    fi

    if [[ $failed -eq 0 ]]; then
        log_ok "168服务器部署完成"
    else
        log_error "168服务器部署存在错误，请检查上方日志"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# 入口：解析参数
# ---------------------------------------------------------------------------
TARGET="${1:-all}"

echo -e "${BLUE}"
echo "============================================"
echo "   工单小管家 - 部署脚本"
echo "   源码目录: $SRC_DIR"
echo "   目标: $TARGET"
echo "============================================"
echo -e "${NC}"

case "$TARGET" in
    165)
        deploy_165
        ;;
    168)
        deploy_168
        ;;
    all)
        deploy_165 || true
        deploy_168 || true
        ;;
    *)
        log_error "未知参数: $TARGET"
        echo ""
        echo "用法:"
        echo "  ./deploy.sh         # 部署到所有服务器（默认）"
        echo "  ./deploy.sh all     # 部署到所有服务器"
        echo "  ./deploy.sh 165     # 仅部署到165服务器"
        echo "  ./deploy.sh 168     # 仅部署到168服务器"
        exit 1
        ;;
esac

log_section "部署脚本执行完毕"
echo ""
echo -e "${YELLOW}提示：如遇到权限问题，可在 Git Bash 中执行：${NC}"
echo "  chmod +x deploy.sh"
echo ""
echo -e "${YELLOW}165服务名确认命令：${NC}"
echo "  ssh administrator@172.17.10.165 \"sc query | findstr /i workorder\""
echo ""
echo -e "${YELLOW}168服务名确认命令：${NC}"
echo "  ssh administrator@172.17.10.168 \"sc query | findstr /i workorder\""
