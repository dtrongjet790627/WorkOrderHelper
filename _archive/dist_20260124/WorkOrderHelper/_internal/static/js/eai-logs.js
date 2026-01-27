/**
 * eai-logs.js - EAI接口日志模块
 * 设计：程远 | 2026-01-18
 * 包含：EAI日志查询、渲染、自动刷新
 * 加载动画：林曦 | 2026-01-23 - 日志滚动动画
 */

// ============================================
//   EAI日志加载动画生成函数
// ============================================

// 生成日志滚动加载动画
function generateLogScrollLoading(text) {
    return `<tr><td colspan="10">
        <div class="log-scroll-loading">
            <div class="log-scroll-container">
                <div class="log-scroll-track">
                    <div class="log-scroll-line"><div class="log-time"></div><div class="log-content"></div><div class="log-status"></div></div>
                    <div class="log-scroll-line"><div class="log-time"></div><div class="log-content"></div><div class="log-status"></div></div>
                    <div class="log-scroll-line"><div class="log-time"></div><div class="log-content"></div><div class="log-status"></div></div>
                    <div class="log-scroll-line"><div class="log-time"></div><div class="log-content"></div><div class="log-status"></div></div>
                    <div class="log-scroll-line"><div class="log-time"></div><div class="log-content"></div><div class="log-status"></div></div>
                    <div class="log-scroll-line"><div class="log-time"></div><div class="log-content"></div><div class="log-status"></div></div>
                    <div class="log-scroll-line"><div class="log-time"></div><div class="log-content"></div><div class="log-status"></div></div>
                    <div class="log-scroll-line"><div class="log-time"></div><div class="log-content"></div><div class="log-status"></div></div>
                </div>
            </div>
            <div class="log-loading-text">
                <i class="bi bi-arrow-clockwise"></i>
                <span>${text}</span>
            </div>
        </div>
    </td></tr>`;
}

// 生成日志行骨架屏（用于快速刷新时）
function generateLogLineSkeleton(count) {
    let html = '';
    for (let i = 0; i < count; i++) {
        html += `<tr><td colspan="10">
            <div class="log-line-loading">
                <div class="ll-indicator"></div>
                <div class="ll-time"></div>
                <div class="ll-level"></div>
                <div class="ll-content"></div>
            </div>
        </td></tr>`;
    }
    return html;
}

// ============================================
//   自动刷新相关变量
// ============================================
let eaiAutoRefreshTimer = null;
let eaiRefreshInterval = 10000; // 默认10秒刷新一次

// 切换自动刷新
function toggleEaiAutoRefresh() {
    const checkbox = document.getElementById('eaiAutoRefresh');
    const statusEl = document.getElementById('eaiRefreshStatus');
    const intervalSelect = document.getElementById('eaiRefreshInterval');

    if (checkbox.checked) {
        // 获取用户选择的刷新间隔
        eaiRefreshInterval = parseInt(intervalSelect.value) || 10000;
        const intervalText = getIntervalText(eaiRefreshInterval);

        // 开启自动刷新
        queryEaiLogs(); // 立即查询一次
        eaiAutoRefreshTimer = setInterval(() => {
            queryEaiLogs(true); // 静默刷新
        }, eaiRefreshInterval);
        statusEl.textContent = `(每${intervalText})`;
        log(`EAI日志自动刷新已开启，间隔${intervalText}`, 'info');
    } else {
        // 关闭自动刷新
        if (eaiAutoRefreshTimer) {
            clearInterval(eaiAutoRefreshTimer);
            eaiAutoRefreshTimer = null;
        }
        statusEl.textContent = '';
        log('EAI日志自动刷新已关闭', 'info');
    }
}

// 更新EAI刷新间隔
function updateEaiRefreshInterval() {
    const checkbox = document.getElementById('eaiAutoRefresh');
    if (checkbox.checked) {
        // 如果正在自动刷新，重新启动以应用新间隔
        toggleEaiAutoRefresh();  // 先关闭
        checkbox.checked = true;
        toggleEaiAutoRefresh();  // 再开启
    }
}

// 格式化间隔文本
function getIntervalText(ms) {
    if (ms >= 60000) return `${ms / 60000}分钟`;
    return `${ms / 1000}秒`;
}

// 页面切换时停止自动刷新
function stopEaiAutoRefresh() {
    const checkbox = document.getElementById('eaiAutoRefresh');
    if (checkbox && checkbox.checked) {
        checkbox.checked = false;
        if (eaiAutoRefreshTimer) {
            clearInterval(eaiAutoRefreshTimer);
            eaiAutoRefreshTimer = null;
        }
        document.getElementById('eaiRefreshStatus').textContent = '';
    }
}

// ============================================
//   EAI日志数据
// ============================================
let eaiLogsData = [];  // 缓存EAI日志数据
let eaiQueryInProgress = false;  // 防止重复请求

// 产线名称映射
const LINE_NAMES = {
    'dpepp1': '电控一线',
    'smt2': '电控二线',
    'dpeps1': '总成产线'
};

// 重置EAI查询按钮状态的辅助函数
function resetEaiQueryBtn() {
    const btn = document.getElementById('eaiQueryBtn');
    if (btn) {
        btn.innerHTML = '<i class="bi bi-search"></i> 查询';
        btn.disabled = false;
    }
    eaiQueryInProgress = false;
}

// ============================================
//   查询EAI日志
// ============================================
async function queryEaiLogs(silent = false) {
    const btn = document.getElementById('eaiQueryBtn');

    // 如果已有请求正在进行且是非静默模式，跳过
    if (eaiQueryInProgress && !silent) {
        return;
    }

    // 标记请求开始
    if (!silent) {
        eaiQueryInProgress = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        btn.disabled = true;
        // 显示日志滚动加载动画
        showEaiLogLoading();
    }

    const lineFilter = document.getElementById('eaiLineFilter').value;
    const levelFilter = document.getElementById('eaiLevelFilter').value;

    if (!silent) {
        log('查询EAI接口日志...', 'info');
    }

    try {
        const response = await fetch('/api/eai_logs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                // wono参数已移除，EAI日志独立于工单查询，始终显示最新日志
                line_key: lineFilter,
                level: levelFilter,
                limit: 500
            })
        });

        const data = await response.json();
        if (data.error) {
            log('EAI日志查询失败: ' + data.error, 'error');
            renderEaiLogsEmpty('查询失败: ' + data.error);
            // 不再使用return，让finally块执行
        } else {
            eaiLogsData = data.logs || [];

            // 更新统计
            const summary = data.summary || {};
            document.getElementById('eaiLogTotal').textContent = summary.total || 0;
            document.getElementById('eaiLogSuccess').textContent = summary.success || 0;
            document.getElementById('eaiLogFailed').textContent = summary.failed || 0;
            document.getElementById('eaiLogWarn').textContent = summary.warn || 0;

            // 更新查询信息（EAI日志独立显示，不按工单过滤）
            const queryInfo = data.query_info || {};
            let infoText = `最新日志 | ${queryInfo.line_key || '全部产线'}`;
            if (queryInfo.level_filter && queryInfo.level_filter !== '全部') {
                infoText += ` | 级别: ${queryInfo.level_filter}`;
            }
            document.getElementById('eaiQueryInfo').textContent = infoText;

            // 渲染日志列表
            renderEaiLogs();

            if (!silent) {
                log(`EAI日志查询完成: 共${summary.total}条, 成功${summary.success}, 失败${summary.failed}`,
                    summary.failed > 0 ? 'warning' : 'success');
            }
        }

    } catch (e) {
        log('EAI日志查询异常: ' + e.message, 'error');
        renderEaiLogsEmpty('网络异常: ' + e.message);
    } finally {
        // 确保在任何情况下都重置按钮状态
        if (!silent) {
            resetEaiQueryBtn();
        }
    }
}

// 仅查询错误日志
async function queryEaiErrors() {
    document.getElementById('eaiLevelFilter').value = 'ERROR';
    await queryEaiLogs();
}

// 根据筛选条件重新过滤（前端过滤已加载的数据）
function filterEaiLogs() {
    // 重新查询API以获取最新数据
    queryEaiLogs();
}

// ============================================
//   EAI日志排序功能（已禁用）
//   原因：EAI日志使用rowspan分组，排序会破坏分组逻辑导致显示混乱
// ============================================

// ============================================
//   导出EAI日志到Excel/CSV
// ============================================
function exportEaiLogs() {
    if (!eaiLogsData || eaiLogsData.length === 0) {
        showToast('没有可导出的数据', 'warning');
        return;
    }

    // CSV表头
    const headers = ['时间', '级别', '产线', '工单号', '批次号', '型号', '数量', '汇报单号', '状态', '详情'];

    // 构建CSV内容
    let csvContent = '\ufeff';  // BOM for Excel UTF-8
    csvContent += headers.join(',') + '\n';

    eaiLogsData.forEach(logItem => {
        const lineName = LINE_NAMES[logItem.line_key] || logItem.line_key || '';
        let statusText = '';
        if (logItem.status === 'success') statusText = '成功';
        else if (logItem.status === 'failed') statusText = '失败';
        else if (logItem.status === 'pending') statusText = '待报工';

        // 清理详情中的HTML标签
        let detail = '';
        if (logItem.error_msg) detail = logItem.error_msg;
        else if (logItem.schb_no) detail = logItem.schb_no;

        // 转义CSV特殊字符
        const row = [
            logItem.time || '',
            logItem.level || '',
            lineName,
            logItem.wono || '',
            logItem.batch || '',
            logItem.partno || '',
            logItem.qty || '',
            logItem.schb_no || '',
            statusText,
            detail.replace(/"/g, '""')
        ].map(cell => `"${cell}"`).join(',');

        csvContent += row + '\n';
    });

    // 下载文件
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const now = new Date();
    const timestamp = now.toISOString().slice(0, 10).replace(/-/g, '');
    link.href = URL.createObjectURL(blob);
    link.download = `EAI日志_${timestamp}.csv`;
    link.click();

    log('EAI日志已导出', 'success');
    showToast('导出成功', 'success');
}

// ============================================
//   渲染EAI日志表格
// ============================================
function renderEaiLogs() {
    const tbody = document.getElementById('eaiLogTable').getElementsByTagName('tbody')[0];
    tbody.innerHTML = '';

    if (eaiLogsData.length === 0) {
        renderEaiLogsEmpty('没有找到符合条件的日志');
        return;
    }

    // 第一步：计算每个组的大小和状态（用于rowspan和背景色）
    // 只有明确设置了group_id的日志才会分组，其他日志各自独立
    const groupSizes = {};
    const groupStatus = {};  // 记录每个组的状态（用于背景色）
    eaiLogsData.forEach((logItem, index) => {
        const groupId = logItem.group_id || ('single_' + index);
        if (!groupSizes[groupId]) {
            groupSizes[groupId] = 0;
            // 记录组的状态（以首行的状态为准）
            if (logItem.status === 'pending') groupStatus[groupId] = 'pending';
            else if (logItem.status === 'failed' || logItem.level === 'ERROR') groupStatus[groupId] = 'error';
            else if (logItem.status === 'success') groupStatus[groupId] = 'success';
            else groupStatus[groupId] = 'default';
        }
        groupSizes[groupId]++;
    });

    // 第二步：跟踪已渲染的组（用于判断是否是组内第一行）
    const renderedGroups = {};

    eaiLogsData.forEach((logItem, index) => {
        const row = tbody.insertRow();
        const groupId = logItem.group_id || ('single_' + index);
        const groupSize = groupSizes[groupId] || 1;
        const isGroupFirst = !renderedGroups[groupId];
        const groupType = groupStatus[groupId] || 'default';

        if (isGroupFirst) {
            renderedGroups[groupId] = true;
        }

        // 行样式 - 根据分组和状态设置
        let rowClass = 'eai-log-row';
        if (groupSize > 1) {
            // 分组记录
            if (isGroupFirst) {
                rowClass += ' group-first';
            } else {
                rowClass += ' group-continuation';
            }
            // 添加状态指示类（用于左侧色条）
            rowClass += ` status-${groupType}`;
        } else {
            // 单条记录：使用原有的行样式
            if (logItem.level === 'ERROR' || logItem.status === 'failed') rowClass += ' log-error';
            else if (logItem.level === 'WARN') rowClass += ' log-warn';
            else if (logItem.level === 'SUCCESS' || logItem.status === 'success') rowClass += ' log-success';
        }
        row.className = rowClass;

        // 级别标签
        let levelClass = 'level-info';
        let levelText = 'INFO';
        if (logItem.level === 'ERROR') { levelClass = 'level-error'; levelText = '错误'; }
        else if (logItem.level === 'WARN') { levelClass = 'level-warn'; levelText = '警告'; }
        else if (logItem.level === 'SUCCESS') { levelClass = 'level-success'; levelText = '成功'; }

        // 状态
        let statusHtml = '-';
        if (logItem.status === 'success') {
            statusHtml = '<span class="badge bg-success">成功</span>';
        } else if (logItem.status === 'failed') {
            statusHtml = '<span class="badge bg-danger">失败</span>';
        } else if (logItem.status === 'pending') {
            statusHtml = '<span class="badge bg-warning text-dark">待报工</span>';
        }

        // 详情（直接使用后端生成的HTML）
        let detailHtml = '';
        if (logItem.raw) {
            detailHtml = `<div class="eai-log-raw">${logItem.raw}</div>`;
        } else if (logItem.schb_no) {
            detailHtml = `<code class="text-success">${logItem.schb_no}</code>`;
        } else if (logItem.error_msg) {
            detailHtml = `<span class="text-danger">${escapeHtml(logItem.error_msg)}</span>`;
        } else {
            detailHtml = '-';
        }

        // 产线名称
        const lineName = LINE_NAMES[logItem.line_key] || logItem.line_key || '-';

        // 汇报单号
        let schbHtml = '-';
        if (logItem.schb_no) {
            schbHtml = `<code class="text-primary">${logItem.schb_no}</code>`;
        }

        // 构建行HTML
        let rowHtml = '';

        // 合并单元格样式（垂直居中）
        const mergedCellStyle = 'vertical-align: middle; text-align: center;';

        if (isGroupFirst && groupSize > 1) {
            // 组内第一行：需要合并的列使用rowspan
            rowHtml = `
                <td class="eai-log-time" rowspan="${groupSize}" style="${mergedCellStyle}">${logItem.time || '-'}</td>
                <td rowspan="${groupSize}" style="${mergedCellStyle}"><span class="eai-log-level ${levelClass}">${levelText}</span></td>
                <td rowspan="${groupSize}" style="${mergedCellStyle}"><span class="line-badge">${lineName}</span></td>
                <td class="eai-log-wono">${logItem.wono || '-'}</td>
                <td>${logItem.batch || '-'}</td>
                <td><small>${logItem.partno || '-'}</small></td>
                <td>${logItem.qty || '-'}</td>
                <td>${schbHtml}</td>
                <td rowspan="${groupSize}" style="${mergedCellStyle}">${statusHtml}</td>
                <td rowspan="${groupSize}" style="vertical-align: middle;">${detailHtml}</td>
            `;
        } else if (!isGroupFirst && groupSize > 1) {
            // 组内非首行：跳过已合并的列（时间、级别、产线、状态、详情）
            rowHtml = `
                <td class="eai-log-wono">${logItem.wono || '-'}</td>
                <td>${logItem.batch || '-'}</td>
                <td><small>${logItem.partno || '-'}</small></td>
                <td>${logItem.qty || '-'}</td>
                <td>${schbHtml}</td>
            `;
        } else {
            // 单条记录（无分组）：正常渲染所有列
            rowHtml = `
                <td class="eai-log-time">${logItem.time || '-'}</td>
                <td><span class="eai-log-level ${levelClass}">${levelText}</span></td>
                <td><span class="line-badge">${lineName}</span></td>
                <td class="eai-log-wono">${logItem.wono || '-'}</td>
                <td>${logItem.batch || '-'}</td>
                <td><small>${logItem.partno || '-'}</small></td>
                <td>${logItem.qty || '-'}</td>
                <td>${schbHtml}</td>
                <td>${statusHtml}</td>
                <td>${detailHtml}</td>
            `;
        }

        row.innerHTML = rowHtml;
    });
}

// 渲染空状态
function renderEaiLogsEmpty(message) {
    const tbody = document.getElementById('eaiLogTable').getElementsByTagName('tbody')[0];
    tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted py-4"><i class="bi bi-inbox"></i> ${message}</td></tr>`;
}

// 显示EAI日志加载动画
function showEaiLogLoading() {
    const tbody = document.getElementById('eaiLogTable').getElementsByTagName('tbody')[0];
    tbody.innerHTML = generateLogScrollLoading('正在获取接口日志...');
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
//   废弃函数（保留以防止引用报错）
// ============================================
// [废弃] 此函数已不再使用 - EAI日志模块现在独立于工单查询
// 保留函数定义以防止可能的引用报错
// 修改日期: 2026-01-14
// 修改原因: 用户需求 - EAI日志应始终显示最新记录，不按工单过滤
function autoQueryEaiLogsForWorkorder() {
    // 已废弃：不再自动按工单过滤EAI日志
    console.log('[废弃函数] autoQueryEaiLogsForWorkorder 已不再使用，EAI日志独立于工单查询');
}

// 前端识别产线（与后端逻辑一致）
function identifyLineKey(wono) {
    if (!wono) return '';
    const upper = wono.toUpperCase();
    if (upper.includes('-2') && upper.substring(4, 6) === '22') return 'smt2';
    if (upper.startsWith('EPS') || upper.startsWith('IPA')) return 'dpeps1';
    if (upper.startsWith('SMT') || upper.startsWith('MID') || upper.startsWith('EPP')) return 'dpepp1';
    return 'dpepp1';
}

// ============================================
//   下达工单日志模块（ERP→MES）- 新版
//   日志文件: FLOW_ERP发送到MES接口.log
// ============================================
let issueLogsData = [];  // 缓存下达工单日志数据
let issueQueryInProgress = false;  // 防止重复请求
let issueAutoRefreshTimer = null;  // 自动刷新定时器
let issueRefreshInterval = 10000;  // 默认10秒刷新

// 切换下达工单日志自动刷新
function toggleIssueAutoRefresh() {
    const checkbox = document.getElementById('issueAutoRefresh');
    const statusEl = document.getElementById('issueRefreshStatus');
    const intervalSelect = document.getElementById('issueRefreshInterval');

    if (checkbox.checked) {
        // 获取用户选择的刷新间隔
        issueRefreshInterval = parseInt(intervalSelect.value) || 10000;
        const intervalText = getIntervalText(issueRefreshInterval);

        // 开启自动刷新
        queryIssueLogs(); // 立即查询一次
        issueAutoRefreshTimer = setInterval(() => {
            queryIssueLogs(true); // 静默刷新
        }, issueRefreshInterval);
        statusEl.textContent = `(每${intervalText})`;
        log(`下达工单日志自动刷新已开启，间隔${intervalText}`, 'info');
    } else {
        // 关闭自动刷新
        if (issueAutoRefreshTimer) {
            clearInterval(issueAutoRefreshTimer);
            issueAutoRefreshTimer = null;
        }
        statusEl.textContent = '';
        log('下达工单日志自动刷新已关闭', 'info');
    }
}

// 更新下达工单日志刷新间隔
function updateIssueRefreshInterval() {
    const checkbox = document.getElementById('issueAutoRefresh');
    if (checkbox.checked) {
        // 如果正在自动刷新，重新启动以应用新间隔
        toggleIssueAutoRefresh();  // 先关闭
        checkbox.checked = true;
        toggleIssueAutoRefresh();  // 再开启
    }
}

// 页面切换时停止下达工单日志自动刷新
function stopIssueAutoRefresh() {
    const checkbox = document.getElementById('issueAutoRefresh');
    if (checkbox && checkbox.checked) {
        checkbox.checked = false;
        if (issueAutoRefreshTimer) {
            clearInterval(issueAutoRefreshTimer);
            issueAutoRefreshTimer = null;
        }
        const statusEl = document.getElementById('issueRefreshStatus');
        if (statusEl) statusEl.textContent = '';
    }
}

// 重置下达工单日志查询按钮状态
function resetIssueQueryBtn() {
    const btn = document.getElementById('issueQueryBtn');
    if (btn) {
        btn.innerHTML = '<i class="bi bi-search"></i> 查询';
        btn.disabled = false;
    }
    issueQueryInProgress = false;
}

// 查询下达工单日志（使用新版API）
async function queryIssueLogs(silent = false) {
    const btn = document.getElementById('issueQueryBtn');

    // 如果已有请求正在进行且是非静默模式，跳过
    if (issueQueryInProgress && !silent) {
        return;
    }

    // 标记请求开始
    if (!silent) {
        issueQueryInProgress = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        btn.disabled = true;
        // 显示日志滚动加载动画
        showIssueLogLoading();
    }

    const prolineFilter = document.getElementById('issueLineFilter').value;
    const levelFilter = document.getElementById('issueLevelFilter').value;

    if (!silent) {
        log('查询下达工单日志...', 'info');
    }

    try {
        // 使用新版API: /api/erp_to_mes_logs
        const response = await fetch('/api/erp_to_mes_logs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                proline: prolineFilter,
                level: levelFilter,
                limit: 500
            })
        });

        const data = await response.json();
        if (data.error) {
            log('下达工单日志查询失败: ' + data.error, 'error');
            renderIssueLogsEmpty('查询失败: ' + data.error);
        } else {
            issueLogsData = data.logs || [];

            // 更新统计
            const summary = data.summary || {};
            document.getElementById('issueLogTotal').textContent = summary.total || 0;
            document.getElementById('issueLogSuccess').textContent = summary.success || 0;
            document.getElementById('issueLogFailed').textContent = summary.failed || 0;
            document.getElementById('issueLogPending').textContent = summary.pending || 0;

            // 更新查询信息
            const queryInfo = data.query_info || {};
            let infoText = `最新日志 | ${queryInfo.proline || '全部产线'}`;
            if (queryInfo.level_filter && queryInfo.level_filter !== '全部') {
                infoText += ` | 状态: ${queryInfo.level_filter}`;
            }
            document.getElementById('issueQueryInfo').textContent = infoText;

            // 渲染日志列表
            renderIssueLogs();

            if (!silent) {
                log(`下达工单日志查询完成: 共${summary.total}条, 成功${summary.success}, 失败${summary.failed}`,
                    summary.failed > 0 ? 'warning' : 'success');
            }
        }

    } catch (e) {
        log('下达工单日志查询异常: ' + e.message, 'error');
        renderIssueLogsEmpty('网络异常: ' + e.message);
    } finally {
        // 确保在任何情况下都重置按钮状态
        if (!silent) {
            resetIssueQueryBtn();
        }
    }
}

// 仅查询错误日志
async function queryIssueErrors() {
    document.getElementById('issueLevelFilter').value = 'ERROR';
    await queryIssueLogs();
}

// 根据筛选条件重新过滤
function filterIssueLogs() {
    queryIssueLogs();
}

// 渲染下达工单日志表格（新版字段）
function renderIssueLogs() {
    const tbody = document.getElementById('issueLogTable').getElementsByTagName('tbody')[0];
    tbody.innerHTML = '';

    if (issueLogsData.length === 0) {
        renderIssueLogsEmpty('没有找到符合条件的日志');
        return;
    }

    issueLogsData.forEach((logItem) => {
        const row = tbody.insertRow();

        // 行样式
        let rowClass = 'eai-log-row';
        if (logItem.level === 'ERROR' || logItem.status === 'failed') rowClass += ' log-error';
        else if (logItem.level === 'WARN') rowClass += ' log-warn';
        else if (logItem.level === 'SUCCESS' || logItem.status === 'success') rowClass += ' log-success';
        row.className = rowClass;

        // 级别标签
        let levelClass = 'level-info';
        let levelText = 'INFO';
        if (logItem.level === 'ERROR') { levelClass = 'level-error'; levelText = '错误'; }
        else if (logItem.level === 'WARN') { levelClass = 'level-warn'; levelText = '警告'; }
        else if (logItem.level === 'SUCCESS') { levelClass = 'level-success'; levelText = '成功'; }

        // 状态
        let statusHtml = '-';
        if (logItem.status === 'success') {
            statusHtml = '<span class="badge bg-success">成功</span>';
        } else if (logItem.status === 'failed') {
            statusHtml = '<span class="badge bg-danger">失败</span>';
        } else if (logItem.status === 'pending') {
            statusHtml = '<span class="badge bg-warning text-dark">处理中</span>';
        }

        // 工单类型标签
        let billTypeHtml = '-';
        if (logItem.bill_type) {
            let badgeClass = 'bg-secondary';
            if (logItem.bill_type.includes('量产')) badgeClass = 'bg-primary';
            else if (logItem.bill_type.includes('返工')) badgeClass = 'bg-warning text-dark';
            billTypeHtml = `<span class="badge ${badgeClass}">${logItem.bill_type}</span>`;
        }

        // 产线显示
        let prolineHtml = logItem.proline || '-';
        if (prolineHtml !== '-') {
            prolineHtml = `<span class="line-badge">${prolineHtml}</span>`;
        }

        // 详情/耗时
        let detailText = '';  // 纯文本用于tooltip
        let detailHtml = '-';
        if (logItem.error_msg) {
            detailText = logItem.error_msg;
            detailHtml = `<span class="text-danger">${escapeHtml(logItem.error_msg)}</span>`;
        } else if (logItem.raw) {
            // raw可能包含HTML标签，提取纯文本用于tooltip
            detailText = logItem.raw.replace(/<[^>]*>/g, '');
            detailHtml = `<div class="eai-log-raw">${logItem.raw}</div>`;
        }
        // 添加耗时信息
        if (logItem.cost_ms && !logItem.raw) {
            detailText = `耗时: ${logItem.cost_ms}ms`;
            detailHtml = `耗时: ${logItem.cost_ms}ms`;
        }

        // 详情列添加title属性显示完整内容
        const detailTitle = detailText ? escapeHtml(detailText).replace(/"/g, '&quot;') : '';

        row.innerHTML = `
            <td class="eai-log-time">${logItem.time || '-'}</td>
            <td><span class="eai-log-level ${levelClass}">${levelText}</span></td>
            <td>${prolineHtml}</td>
            <td class="eai-log-wono">${logItem.wono || '-'}</td>
            <td>${billTypeHtml}</td>
            <td><small title="${logItem.material_name || ''}">${logItem.material_id || '-'}</small></td>
            <td>${logItem.qty || '-'}</td>
            <td>${statusHtml}</td>
            <td title="${detailTitle}">${detailHtml}</td>
        `;
    });
}

// 渲染空状态
function renderIssueLogsEmpty(message) {
    const tbody = document.getElementById('issueLogTable').getElementsByTagName('tbody')[0];
    tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted py-4"><i class="bi bi-inbox"></i> ${message}</td></tr>`;
}

// 显示下达工单日志加载动画
function showIssueLogLoading() {
    const tbody = document.getElementById('issueLogTable').getElementsByTagName('tbody')[0];
    tbody.innerHTML = generateLogScrollLoading('正在获取下达工单日志...');
}

// ============================================
//   导出下达工单日志到Excel/CSV
// ============================================
function exportIssueLogs() {
    if (!issueLogsData || issueLogsData.length === 0) {
        showToast('没有可导出的数据', 'warning');
        return;
    }

    // CSV表头
    const headers = ['时间', '级别', '产线', '工单号', '工单类型', '型号', '数量', '状态', '详情'];

    // 构建CSV内容
    let csvContent = '\ufeff';  // BOM for Excel UTF-8
    csvContent += headers.join(',') + '\n';

    issueLogsData.forEach(logItem => {
        let statusText = '';
        if (logItem.status === 'success') statusText = '成功';
        else if (logItem.status === 'failed') statusText = '失败';
        else if (logItem.status === 'pending') statusText = '处理中';

        // 清理详情
        let detail = '';
        if (logItem.error_msg) detail = logItem.error_msg;
        else if (logItem.cost_ms) detail = `耗时: ${logItem.cost_ms}ms`;

        // 转义CSV特殊字符
        const row = [
            logItem.time || '',
            logItem.level || '',
            logItem.proline || '',
            logItem.wono || '',
            logItem.bill_type || '',
            logItem.material_id || '',
            logItem.qty || '',
            statusText,
            detail.replace(/"/g, '""')
        ].map(cell => `"${cell}"`).join(',');

        csvContent += row + '\n';
    });

    // 下载文件
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const now = new Date();
    const timestamp = now.toISOString().slice(0, 10).replace(/-/g, '');
    link.href = URL.createObjectURL(blob);
    link.download = `下达工单日志_${timestamp}.csv`;
    link.click();

    log('下达工单日志已导出', 'success');
    showToast('导出成功', 'success');
}

// ============================================
//   日志表格行点击高亮功能
// ============================================
function initLogTableRowHighlight() {
    // 报工日志表格
    const eaiTable = document.getElementById('eaiLogTable');
    if (eaiTable) {
        const tbody = eaiTable.getElementsByTagName('tbody')[0];
        if (tbody) {
            tbody.addEventListener('click', (e) => {
                handleLogRowClick(e, tbody);
            });
        }
    }

    // 下达工单日志表格
    const issueTable = document.getElementById('issueLogTable');
    if (issueTable) {
        const tbody = issueTable.getElementsByTagName('tbody')[0];
        if (tbody) {
            tbody.addEventListener('click', (e) => {
                handleLogRowClick(e, tbody);
            });
        }
    }
}

function handleLogRowClick(e, tbody) {
    // 找到被点击的行
    const row = e.target.closest('tr');
    if (!row || row.querySelector('td[colspan]')) {
        // 忽略空状态行和加载行
        return;
    }

    // 切换选中状态
    if (row.classList.contains('row-selected')) {
        row.classList.remove('row-selected');
    } else {
        // 移除同表格其他行的选中状态
        tbody.querySelectorAll('tr.row-selected').forEach(r => {
            r.classList.remove('row-selected');
        });
        row.classList.add('row-selected');
    }
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', () => {
    initLogTableRowHighlight();
});
