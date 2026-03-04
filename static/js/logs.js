/**
 * logs.js - 日志查看器模块
 * 设计：程远 | 2026-01-23
 * 功能：系统日志查看、筛选、搜索
 */

// ============================================
//   日志查看器状态
// ============================================
let logAutoRefreshTimer = null;
let logAutoRefreshEnabled = false;
const LOG_AUTO_REFRESH_INTERVAL = 5000; // 5秒自动刷新

// ============================================
//   加载日志内容
// ============================================
async function loadLogContent() {
    const filename = 'user.log';
    const level = document.getElementById('logLevelFilter').value;
    const lines = document.getElementById('logLinesLimit').value;
    const search = document.getElementById('logSearchInput').value.trim();

    const wrapper = document.getElementById('logContentWrapper');

    // 显示加载状态
    wrapper.innerHTML = `
        <div class="log-loading">
            <div class="spinner-border text-secondary" role="status"></div>
            <span>加载日志中...</span>
        </div>
    `;

    try {
        // 构建查询参数
        const params = new URLSearchParams({
            filename: filename,
            lines: lines
        });
        if (level) params.append('level', level);
        if (search) params.append('search', search);

        const response = await fetch(`/api/logs/read?${params}`);
        const data = await response.json();

        if (data.error) {
            wrapper.innerHTML = `
                <div class="log-empty">
                    <i class="bi bi-exclamation-circle text-danger"></i>
                    <span>${data.error}</span>
                </div>
            `;
            return;
        }

        const logLines = data.lines || [];

        if (logLines.length === 0) {
            wrapper.innerHTML = `
                <div class="log-empty">
                    <i class="bi bi-journal-x"></i>
                    <span>没有找到匹配的日志记录</span>
                </div>
            `;
            updateLogStats(filename, '-', 0);
            return;
        }

        // 渲染日志行
        const html = logLines.map(line => {
            const levelClass = getLogLevelClass(line);
            const highlightedLine = search ? highlightSearchTerm(line, search) : escapeHtml(line);
            return `<div class="log-line ${levelClass}">${highlightedLine}</div>`;
        }).join('');

        wrapper.innerHTML = html;

        // 更新统计信息
        updateLogStats(filename, data.size_str || '-', logLines.length);

    } catch (error) {
        console.error('加载日志失败:', error);
        wrapper.innerHTML = `
            <div class="log-empty">
                <i class="bi bi-exclamation-triangle text-warning"></i>
                <span>加载日志失败: ${error.message}</span>
            </div>
        `;
    }
}

// ============================================
//   辅助函数
// ============================================

// 获取日志级别对应的CSS类
function getLogLevelClass(line) {
    if (line.includes('[ERROR]') || line.includes('"level": "ERROR"')) {
        return 'level-error';
    }
    if (line.includes('[WARNING]') || line.includes('"level": "WARNING"')) {
        return 'level-warning';
    }
    if (line.includes('[INFO]') || line.includes('"level": "INFO"')) {
        return 'level-info';
    }
    if (line.includes('[DEBUG]') || line.includes('"level": "DEBUG"')) {
        return 'level-debug';
    }
    if (line.includes('[CRITICAL]') || line.includes('"level": "CRITICAL"')) {
        return 'level-critical';
    }
    return 'level-info';
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 高亮搜索关键词
function highlightSearchTerm(line, search) {
    const escaped = escapeHtml(line);
    if (!search) return escaped;

    const regex = new RegExp(`(${escapeRegExp(search)})`, 'gi');
    return escaped.replace(regex, '<span class="log-highlight">$1</span>');
}

// 转义正则表达式特殊字符
function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// 更新日志统计信息
function updateLogStats(filename, size, lineCount) {
    document.getElementById('logFileName').textContent = filename;
    document.getElementById('logFileSize').textContent = size;
    document.getElementById('logLineCount').textContent = lineCount;
    document.getElementById('logLastUpdate').textContent = new Date().toLocaleTimeString('zh-CN');
}

// ============================================
//   刷新与自动刷新
// ============================================

// 刷新日志查看器
function refreshLogViewer() {
    loadLogContent();
}

// 切换自动刷新
function toggleLogAutoRefresh() {
    logAutoRefreshEnabled = !logAutoRefreshEnabled;

    const indicator = document.getElementById('logAutoRefreshIndicator');
    const btnText = document.getElementById('autoRefreshBtnText');

    if (logAutoRefreshEnabled) {
        indicator.style.display = 'inline-flex';
        btnText.textContent = '停止刷新';
        startLogAutoRefresh();
    } else {
        indicator.style.display = 'none';
        btnText.textContent = '自动刷新';
        stopLogAutoRefresh();
    }
}

// 启动自动刷新
function startLogAutoRefresh() {
    stopLogAutoRefresh(); // 先停止已有的
    logAutoRefreshTimer = setInterval(() => {
        loadLogContent();
    }, LOG_AUTO_REFRESH_INTERVAL);
}

// 停止自动刷新
function stopLogAutoRefresh() {
    if (logAutoRefreshTimer) {
        clearInterval(logAutoRefreshTimer);
        logAutoRefreshTimer = null;
    }
}

// ============================================
//   搜索回车触发
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('logSearchInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                loadLogContent();
            }
        });
    }
});

// ============================================
//   视图切换时的处理
// ============================================
// 当离开日志视图时停止自动刷新（在sidebar.js中调用）
function stopLogViewerAutoRefresh() {
    if (logAutoRefreshEnabled) {
        logAutoRefreshEnabled = false;
        const indicator = document.getElementById('logAutoRefreshIndicator');
        const btnText = document.getElementById('autoRefreshBtnText');
        if (indicator) indicator.style.display = 'none';
        if (btnText) btnText.textContent = '自动刷新';
        stopLogAutoRefresh();
    }
}
