/**
 * erp-detail.js - ERP详情页面模块
 * 设计：程远 | 2026-01-18
 * 包含：ERP详情页面刷新、批次明细渲染
 * 加载动画：林曦 | 2026-01-23 - 骨架屏效果
 */

// ============================================
//   ERP详情页面功能
// ============================================

// 生成ERP表格骨架屏行
function generateErpSkeletonRows(count) {
    let html = '';
    for (let i = 0; i < count; i++) {
        const delay = i * 0.1;
        html += `<tr class="skeleton-row-tr" style="animation-delay: ${delay}s;">
            <td class="text-center"><div class="skeleton-cell cell-sm" style="animation-delay: ${delay}s;"></div></td>
            <td><div class="skeleton-cell cell-lg" style="animation-delay: ${delay + 0.05}s;"></div></td>
            <td class="text-center"><div class="skeleton-cell cell-md" style="animation-delay: ${delay + 0.1}s;"></div></td>
            <td class="text-center"><div class="skeleton-cell cell-md" style="animation-delay: ${delay + 0.15}s;"></div></td>
            <td class="text-center"><div class="skeleton-cell cell-md" style="animation-delay: ${delay + 0.2}s;"></div></td>
            <td class="text-center"><div class="skeleton-cell cell-sm" style="animation-delay: ${delay + 0.25}s;"></div></td>
            <td class="text-center"><div class="skeleton-cell cell-sm" style="animation-delay: ${delay + 0.3}s;"></div></td>
            <td class="text-center"><div class="skeleton-badge" style="animation-delay: ${delay + 0.35}s;"></div></td>
            <td class="text-center"><div class="skeleton-cell cell-md" style="animation-delay: ${delay + 0.4}s;"></div></td>
            <td><div class="skeleton-cell cell-lg" style="animation-delay: ${delay + 0.45}s;"></div></td>
            <td class="text-center"><div class="skeleton-cell cell-sm" style="animation-delay: ${delay + 0.5}s;"></div></td>
            <td class="text-center"><div class="skeleton-cell cell-sm" style="animation-delay: ${delay + 0.55}s;"></div></td>
            <td class="text-center"><div class="skeleton-cell cell-sm" style="animation-delay: ${delay + 0.6}s;"></div></td>
            <td class="text-center"><div class="skeleton-badge" style="animation-delay: ${delay + 0.65}s;"></div></td>
        </tr>`;
    }
    return html;
}

// 重置ERP详情页面到初始状态
function resetErpDetail() {
    // 重置加载标记
    erpDetailLoaded = false;

    // 安全的元素更新函数
    const safeSet = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    };

    // 重置汇总统计
    safeSet('erpDetailTotal', '-');
    safeSet('erpDetailBatchCount', '-');
    safeSet('erpDetailAccTotal', '-');
    safeSet('erpDetailDiff', '-');
    safeSet('erpDetailConsistency', '-');

    // 重置工单概述
    safeSet('erpMoBillNo', '-');
    safeSet('erpMaterialNo', '-');
    safeSet('erpPlanQty', '-');
    safeSet('erpInStockQty', '-');
    safeSet('erpCloseDate', '-');
    safeSet('erpBizStatus', '-');
    const statusEl = document.getElementById('erpBizStatus');
    if (statusEl) statusEl.className = 'badge bg-secondary';

    // 重置汇总行
    safeSet('erpSumPackQty', '-');
    safeSet('erpSumErpQty', '-');
    safeSet('erpSumStockInQty', '-');
    safeSet('erpSumAccQty', '-');
    safeSet('erpSumDiff', '-');

    // 重置批次列表
    const bodyEl = document.getElementById('erpDetailBody');
    if (bodyEl) bodyEl.innerHTML = `<tr><td colspan="14" class="empty-state-cell">
        <div class="empty-state-container">
            <div class="empty-state-mascot"><i class="bi bi-folder2-open"></i></div>
            <div class="empty-state-text">小管家准备就绪~</div>
            <div class="empty-state-hint">请先查询工单，然后点击刷新加载ERP数据</div>
        </div>
    </td></tr>`;
}

// 刷新ERP详情页面
async function refreshErpDetail() {
    if (!currentWono) {
        alert('请先查询工单');
        return;
    }

    // 设置加载状态（汇总统计）
    const setLoading = (id, text = '...') => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    };
    setLoading('erpDetailTotal');
    setLoading('erpDetailBatchCount');
    setLoading('erpDetailAccTotal');
    setLoading('erpDetailDiff');
    setLoading('erpDetailConsistency');
    // 设置加载状态（工单概述）
    setLoading('erpMoBillNo');
    setLoading('erpMaterialNo');
    setLoading('erpPlanQty');
    setLoading('erpInStockQty');
    setLoading('erpCloseDate');
    setLoading('erpBizStatus');
    const statusEl = document.getElementById('erpBizStatus');
    if (statusEl) statusEl.className = 'badge bg-secondary';
    // 批次列表（使用骨架屏效果，保持高度避免合计行上移）
    document.getElementById('erpDetailBody').innerHTML = generateErpSkeletonRows(5);
    // 重置汇总行
    setLoading('erpSumPackQty', '-');
    setLoading('erpSumErpQty', '-');
    setLoading('erpSumStockInQty', '-');
    setLoading('erpSumAccQty', '-');
    setLoading('erpSumDiff', '-');

    try {
        // 并行请求：对比数据 + 工单概述
        const [compareResponse, summaryResponse] = await Promise.all([
            fetch('/api/compare_acc_erp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ wono: currentWono })
            }),
            fetch('/api/erp_order_summary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ wono: currentWono })
            })
        ]);

        const data = await compareResponse.json();
        const summaryData = await summaryResponse.json();

        // 更新工单概述 - 使用安全的元素更新函数
        const safeSetText = (id, text) => {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        };
        const safeSetClass = (id, className) => {
            const el = document.getElementById(id);
            if (el) el.className = className;
        };

        if (summaryData.success) {
            safeSetText('erpMoBillNo', summaryData.mo_bill_no || currentWono);
            // 物料号和物料名称合并显示
            const materialNo = summaryData.material_no || '-';
            const materialName = summaryData.material_name && summaryData.material_name !== '-' ? ' (' + summaryData.material_name + ')' : '';
            const fullMaterialText = materialNo + materialName;
            safeSetText('erpMaterialNo', fullMaterialText);
            // 设置title属性，悬停显示完整物料信息
            const materialEl = document.getElementById('erpMaterialNo');
            if (materialEl) materialEl.title = fullMaterialText;
            safeSetText('erpPlanQty', summaryData.plan_qty || 0);
            safeSetText('erpInStockQty', summaryData.in_stock_qty || 0);
            safeSetText('erpCloseDate', summaryData.close_date || '-');

            // 业务状态徽章样式（金蝶ERP业务状态）
            safeSetText('erpBizStatus', summaryData.biz_status_text || '-');
            const statusColorMap = {
                '1': 'bg-secondary',    // 计划确认 - 灰色
                '2': 'bg-secondary',    // 计划下达 - 灰色
                '3': 'bg-info',         // 下达 - 蓝色
                '4': 'bg-primary',      // 开工 - 深蓝色
                '5': 'bg-warning',      // 完工 - 黄色
                '6': 'bg-info',         // 入库中 - 蓝色
                '7': 'bg-success'       // 结案 - 绿色
            };
            safeSetClass('erpBizStatus', 'badge ' + (statusColorMap[String(summaryData.biz_status)] || 'bg-secondary'));
        } else {
            // 工单概述加载失败，显示默认值
            safeSetText('erpMoBillNo', currentWono);
            safeSetText('erpMaterialNo', '-');
            safeSetText('erpPlanQty', '-');
            safeSetText('erpInStockQty', '-');
            safeSetText('erpCloseDate', '-');
            safeSetText('erpBizStatus', '-');
            safeSetClass('erpBizStatus', 'badge bg-secondary');
        }

        if (data.error) {
            document.getElementById('erpDetailTotal').textContent = '-';
            document.getElementById('erpDetailBatchCount').textContent = '-';
            document.getElementById('erpDetailAccTotal').textContent = '-';
            document.getElementById('erpDetailDiff').textContent = '-';
            document.getElementById('erpDetailConsistency').textContent = '-';
            document.getElementById('erpDetailBody').innerHTML = `<tr><td colspan="14" class="text-center text-danger" class="py-4"><i class="bi bi-exclamation-triangle"></i> ${data.error}</td></tr>`;
            log('ERP详情加载失败: ' + data.error, 'error');
            return;
        }

        // 更新汇总统计
        document.getElementById('erpDetailTotal').textContent = data.erp_total || 0;
        document.getElementById('erpDetailBatchCount').textContent = data.erp_batch_count || 0;
        document.getElementById('erpDetailAccTotal').textContent = data.acc_total || 0;

        const diffTotal = data.diff_total || 0;
        const diffEl = document.getElementById('erpDetailDiff');
        diffEl.textContent = diffTotal > 0 ? '+' + diffTotal : diffTotal;
        diffEl.parentElement.style.background = diffTotal === 0
            ? 'linear-gradient(135deg, #198754 0%, #20c997 100%)'
            : 'linear-gradient(135deg, #f7971e 0%, #ffd200 100%)';

        // 计算一致性
        const accTotal = data.acc_total || 0;
        const consistency = accTotal > 0 ? Math.round((1 - Math.abs(diffTotal) / accTotal) * 100) : (diffTotal === 0 ? 100 : 0);
        document.getElementById('erpDetailConsistency').textContent = consistency + '%';

        // 渲染批次明细列表
        const tbody = document.getElementById('erpDetailBody');
        // 用于累加入库数量（在if块外定义，避免作用域问题）
        let stockInQtySum = 0;
        if (data.comparison && data.comparison.length > 0) {
            let html = '';
            data.comparison.forEach((item, index) => {
                // 判断是否为续行（同批次的后续收货记录）
                const isContinuation = item.status === 'continuation';

                // 根据warning_type设置行样式和提示
                let rowClass = '';
                let statusBadge = '';
                // ACC工单数量：使用按汇报单号匹配的CNT值
                // 优先级：
                // 1. 如果ACC_ERP_REPORT_SUCCESS表中有此汇报单号，显示acc_cnt_for_bill
                // 2. 如果使用PACK_HISTORY数据（use_pack_history=true），显示acc_cnt_for_bill
                // 3. 其他情况显示0或空
                let accQtyHtml = '-';
                if (item.use_pack_history === true) {
                    // 使用PACK_HISTORY数据，显示包装数量
                    accQtyHtml = item.acc_cnt_for_bill || 0;
                } else if (item.has_acc_report_for_bill === false) {
                    // ACC表中无此汇报单号且不使用PACK_HISTORY，显示0
                    accQtyHtml = '0';
                } else if (item.acc_cnt_for_bill !== null && item.acc_cnt_for_bill !== undefined) {
                    // ACC表中有此汇报单号，显示ACC的CNT值
                    accQtyHtml = item.acc_cnt_for_bill;
                } else if (item.acc_qty !== null) {
                    // 兼容：如果没有acc_cnt_for_bill，使用acc_qty
                    accQtyHtml = item.acc_qty;
                }

                // 状态判断（简化版，与后端逻辑一致）
                switch(item.warning_type) {
                    case 'unsealed':
                        // 未封包：蓝色背景
                        accQtyHtml = item.acc_qty || 0;
                        statusBadge = '<span class="badge bg-info">包装中</span>';
                        rowClass = 'style="background-color: #e3f2fd;"';
                        break;

                    case 'duplicate_report':
                        // 重复报工：橙色背景（同一批次第2次及之后的报工）
                        accQtyHtml = '0';
                        rowClass = 'style="background-color: #ff9800;"';
                        statusBadge = `<span class="badge bg-danger">重复报工</span> <i class="bi bi-exclamation-triangle-fill text-danger erp-status-indicator" data-tip-type="error" data-tip-title="重复报工" data-tip-reasons="此批次已有其他汇报单号报工|当前为重复报工" data-tip-result="重复报工" style="cursor:pointer;"></i>`;
                        break;

                    case 'report_error':
                        // 报工异常：ERP有+ACC无+创建人=系统（浅黄色背景）
                        accQtyHtml = item.acc_cnt_for_bill || 0;
                        rowClass = 'style="background-color: #fff3cd;"';
                        statusBadge = `<span class="badge bg-danger">报工异常</span> <i class="bi bi-exclamation-circle-fill text-warning erp-status-indicator" data-tip-type="error" data-tip-title="报工异常" data-tip-reasons="创建人为系统报工|ACC无此汇报单号" data-tip-result="报工异常，需排查" style="cursor:pointer;"></i>`;
                        break;

                    case 'manual_receipt':
                        // 人为收货：ERP有+ACC无+创建人≠系统（浅黄色背景）
                        accQtyHtml = item.acc_cnt_for_bill || 0;
                        rowClass = 'style="background-color: #fff3cd;"';
                        statusBadge = `<span class="badge bg-secondary">人为收货</span> <i class="bi bi-exclamation-circle-fill text-warning erp-status-indicator" data-tip-type="warning" data-tip-title="人为收货" data-tip-reasons="创建人非系统报工|ACC无此汇报单号" data-tip-result="人为收货" style="cursor:pointer;"></i>`;
                        break;

                    case 'erp_deleted':
                        // ERP人为删除：ACC有+ERP无（紫色背景）
                        accQtyHtml = item.acc_cnt_for_bill || item.acc_qty || 0;
                        rowClass = 'style="background-color: #ce93d8;"';
                        statusBadge = `<span class="badge bg-warning text-dark">ERP人为删除</span> <i class="bi bi-exclamation-circle-fill text-danger erp-status-indicator" data-tip-type="warning" data-tip-title="人为删除" data-tip-reasons="ACC存在此汇报单号|ERP中无此汇报单号" data-tip-result="ERP人为删除" style="cursor:pointer;"></i>`;
                        break;

                    case 'pending_report':
                        // 待报工：已封包但ACC无报工记录（蓝色背景）
                        accQtyHtml = item.acc_cnt_for_bill || item.acc_qty || 0;
                        rowClass = 'style="background-color: #e3f2fd;"';
                        statusBadge = '<span class="badge bg-info">待报工</span>';
                        break;

                    default:
                        // 正常或续行
                        accQtyHtml = item.acc_cnt_for_bill || 0;
                        if (item.status === 'continuation') {
                            // 续行
                            statusBadge = '<span class="text-muted">-</span>';
                            rowClass = 'class="table-secondary"';
                        } else if (item.status === 'packing') {
                            // 包装中（ERP无记录、ACC无报工成功记录但有打包数据）
                            statusBadge = '<span class="badge bg-info">包装中</span>';
                            rowClass = 'style="background-color: #e3f2fd;"';
                        } else if (item.has_acc_report_for_bill && item.diff_for_bill === 0) {
                            // 正常：ERP有+ACC有+差异为0
                            statusBadge = '<span class="badge bg-success">正常</span>';
                        } else if (item.has_acc_report_for_bill && item.diff_for_bill !== 0) {
                            // 数量差异
                            rowClass = 'style="background-color: #f8d7da;"';
                            statusBadge = `<span class="badge bg-danger">数量差异</span> <i class="bi bi-exclamation-circle-fill text-danger erp-status-indicator" data-tip-type="error" data-tip-title="数量差异" data-tip-reasons="ERP报工数量：${item.erp_qty}|ACC报工数量：${item.acc_cnt_for_bill}" data-tip-result="数量不一致，需核对" style="cursor:pointer;"></i>`;
                        } else {
                            statusBadge = '<span class="badge bg-success">正常</span>';
                        }
                }

                // 差异显示：使用按汇报单号匹配的差异值 diff_for_bill
                // 未封包/待报工显示"-"带提示图标，重复报工显示差异值但带图标说明不计入统计
                let diffHtml = '';
                if (item.warning_type === 'unsealed') {
                    diffHtml = `<span class="text-info">- <i class="bi bi-box-seam erp-diff-indicator" data-diff-type="unsealed" data-packid="${item.packid}" style="cursor:pointer;"></i></span>`;
                } else if (item.warning_type === 'pending_report') {
                    diffHtml = `<span class="text-info">- <i class="bi bi-clock erp-diff-indicator" data-diff-type="pending_report" data-packid="${item.packid}" style="cursor:pointer;"></i></span>`;
                } else if (item.warning_type === 'duplicate_report') {
                    // 重复报工：显示差异值（通常是负数，因为ERP重复报了但ACC没有对应数量）
                    // 带图标说明此差异不计入统计
                    const diff = item.diff_for_bill !== null && item.diff_for_bill !== undefined ? item.diff_for_bill : item.diff;
                    let diffText = diff > 0 ? `+${diff}` : diff;
                    diffHtml = `<span class="text-warning">${diffText} <i class="bi bi-arrow-repeat erp-diff-indicator" data-diff-type="duplicate_report" data-packid="${item.packid}" data-erp-qty="${item.erp_qty || 0}" style="cursor:pointer;"></i></span>`;
                } else {
                    // 使用按汇报单号计算的差异值
                    const diff = item.diff_for_bill !== null && item.diff_for_bill !== undefined ? item.diff_for_bill : item.diff;
                    if (diff > 0) {
                        diffHtml = `<span class="text-danger">+${diff}</span>`;
                    } else if (diff < 0) {
                        diffHtml = `<span class="text-success">${diff}</span>`;
                    } else {
                        diffHtml = '<span class="text-success">0</span>';
                    }
                }

                // 单据状态样式
                let docStatusBadge = '';
                // 判断是否为ACC数据源（需要在此处提前判断）
                // 注意：未封包批次（warning_type === 'unsealed' 或 status === 'packing'）不是ACC数据源，不显示"已删除"
                const isUnsealed = item.warning_type === 'unsealed' || item.status === 'packing';
                const isAccDataForDocStatus = !isUnsealed && (item.is_acc_data === true || item.status === 'acc_only' || item.warning_type === 'acc_success_no_erp' || item.warning_type === 'acc_only');
                if (isUnsealed) {
                    // 未封包批次：单据状态显示"-"
                    docStatusBadge = '-';
                } else if (isAccDataForDocStatus) {
                    // ACC有记录但ERP无记录：显示"已删除"并带提示图标
                    const deleteLog3 = item.delete_log || {};
                    const hasDeleteLog = deleteLog3.delete_user || deleteLog3.delete_time;
                    let deleteReasons3;
                    if (hasDeleteLog) {
                        // 有删除日志，显示详细信息
                        // superman映射为系统管理员
                        let deleteUser3 = deleteLog3.delete_user || '-';
                        if (deleteUser3.toLowerCase() === 'superman') {
                            deleteUser3 = '系统管理员';
                        }
                        const deleteTime3 = deleteLog3.delete_time || '-';
                        let deleteIp3 = deleteLog3.ip_address || '-';
                        // 将IP和MAC分开显示
                        let macAddr = '';
                        if (deleteIp3.includes('(MAC:')) {
                            const macMatch = deleteIp3.match(/\(MAC:([^)]+)\)/);
                            if (macMatch) {
                                macAddr = macMatch[1];
                                deleteIp3 = deleteIp3.replace(/\(MAC:[^)]+\)/, '').trim();
                            }
                        }
                        deleteReasons3 = '操作人：' + deleteUser3 + '|操作时间：' + deleteTime3 + '|操作IP：' + deleteIp3;
                        if (macAddr) {
                            deleteReasons3 += '|MAC：' + macAddr;
                        }
                    } else {
                        // 无删除日志，显示简化信息
                        deleteReasons3 = 'ACC报工成功但ERP中无此单据|ERP操作日志中无删除记录';
                    }
                    docStatusBadge = `<span class="badge bg-danger" style="font-size:0.85em;">已删除</span> <i class="bi bi-exclamation-circle-fill text-danger erp-status-indicator" data-tip-type="warning" data-tip-title="人为删除" data-tip-reasons="${deleteReasons3}" data-tip-result="ERP人为删除" style="cursor:pointer;font-size:0.85em;"></i>`;
                } else if (item.doc_status) {
                    const statusClass = item.doc_status === '已审核' ? 'bg-success' : 'bg-secondary';
                    docStatusBadge = `<span class="badge ${statusClass}" style="font-size:0.85em;">${item.doc_status}</span>`;
                } else {
                    docStatusBadge = '-';
                }

                // 包装数量（pack_total_qty）- 检测混装情况
                let packQtyHtml = '';
                const packQty = item.pack_total_qty !== null && item.pack_total_qty !== undefined ? item.pack_total_qty : 0;
                const accQty = item.acc_qty !== null && item.acc_qty !== undefined ? item.acc_qty : 0;

                // 未封包批次：直接显示包装数量
                // 如果ACC表中无此汇报单号且未使用PACK_HISTORY数据且不是未封包批次，包装数量显示为0
                if (item.warning_type === 'unsealed' || item.status === 'packing') {
                    // 未封包批次直接显示实际包装数量
                    packQtyHtml = packQty > 0 ? packQty : (accQty > 0 ? accQty : '-');
                } else if (item.has_acc_report_for_bill === false && item.use_pack_history !== true) {
                    packQtyHtml = '0';
                } else {
                    // 检测混装：包装数量 != 工单数量 且 有多个工单（且mixedDetail有数据）
                    const mixedDetail = item.mixed_detail || [];
                    const isMixed = packQty !== accQty && mixedDetail.length > 1;

                    if (isMixed && !isContinuation && mixedDetail.length > 0) {
                        // 构建混装提示内容
                        const mixedTipId = `mixed-tip-${index}`;
                        let tipContent = mixedDetail.map(wo => `${wo.wono}: ${wo.qty}个`).join('\\n');
                        packQtyHtml = `${packQty} <i class="bi bi-exclamation-triangle-fill text-warning erp-mixed-indicator"
                            data-mixed-packid="${item.packid}"
                            data-mixed-detail='${JSON.stringify(mixedDetail).replace(/'/g, "&#39;")}'
                            style="cursor:pointer;"></i>`;
                    } else {
                        packQtyHtml = packQty > 0 ? packQty : '-';
                    }
                }

                // 保底逻辑已移至后端处理，前端只根据warning_type显示
                // 后端已确保warning_type正确设置为：report_error 或 manual_receipt

                // 当rowClass有值时（异常状态），所有td都设置背景透明，让tr背景色生效
                const hasRowBg = rowClass !== '';
                // 对于异常行，所有td都使用透明背景；正常行使用区分色
                const erpBg = hasRowBg ? 'background:transparent !important;' : 'background:#f8f5ff;';
                const accBg = hasRowBg ? 'background:transparent !important;' : 'background:#f0fff4;';
                // 通用列背景：异常行透明，正常行无设置
                const commonBg = hasRowBg ? 'background:transparent !important;' : '';

                // 判断是否为ACC数据源（acc_only类型，即ACC有记录但ERP无记录）
                const isAccData = item.is_acc_data === true || item.status === 'acc_only' || item.warning_type === 'acc_success_no_erp';
                // ACC数据使用紫色字体
                const accDataColor = isAccData ? 'color:#4a148c;' : '';

                // 创建人：如果是"系统"则显示为"系统报工"，ACC数据也显示"系统报工"
                let creatorDisplay = item.creator_name || '-';
                if (item.creator_name === '系统') {
                    creatorDisplay = '系统报工';
                } else if (item.creator_name === 'ACC系统' || isAccData) {
                    creatorDisplay = '<span style="color:#4a148c;">系统报工</span>';
                }

                // ACC数据源的特殊显示处理
                let billNoDisplay = item.bill_no || '-';
                let createDateDisplay = item.create_date || '-';
                let erpQtyDisplay = item.erp_qty || 0;
                let stockInQtyDisplay = item.stock_in_qty || 0;
                let approverDisplay = item.approver_name || '-';
                let approveDateDisplay = item.approve_date || '-';

                // 累加入库数量（排除ACC数据源，因为ACC数据源的入库数量显示为0）
                if (!isAccData) {
                    stockInQtySum += parseInt(item.stock_in_qty) || 0;
                }

                if (isAccData) {
                    // ACC数据源使用深紫色字体标识
                    if (item.bill_no) {
                        billNoDisplay = `<span style="color:#4a148c;">${item.bill_no}</span>`;
                    }
                    if (item.create_date) {
                        createDateDisplay = `<span style="color:#4a148c;">${item.create_date}</span>`;
                    }
                    // 报工数量：显示ACC的cnt值（acc_cnt_for_bill或erp_qty）
                    const accReportQty = item.acc_cnt_for_bill || item.erp_qty || 0;
                    erpQtyDisplay = `<span style="color:#4a148c;">${accReportQty}</span>`;
                    // 入库数量显示0（ERP无记录）
                    stockInQtyDisplay = `<span style="color:#4a148c;">0</span>`;
                    // 审核人显示"-"
                    approverDisplay = `<span style="color:#4a148c;">-</span>`;
                    // 审核日期显示"-"
                    approveDateDisplay = `<span style="color:#4a148c;">-</span>`;
                }

                html += `<tr ${rowClass}>
                    <td class="text-center" style="font-size:0.9rem; ${commonBg} overflow:hidden;">${index + 1}</td>
                    <td class="text-center" style="${erpBg} overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><code class="font-monospace" style="font-size:0.85rem; ${accDataColor}">${billNoDisplay}</code></td>
                    <td class="text-center" style="font-size:0.9rem; ${erpBg} ${accDataColor} overflow:hidden;">${creatorDisplay}</td>
                    <td class="text-center" style="font-size:0.85rem; ${erpBg} ${accDataColor} overflow:hidden;">${createDateDisplay}</td>
                    <td class="text-center" style="font-size:0.85rem; ${erpBg} ${accDataColor} overflow:hidden;">${approveDateDisplay}</td>
                    <td class="text-center" style="font-size:0.9rem; ${erpBg} ${accDataColor} overflow:hidden;">${erpQtyDisplay}</td>
                    <td class="text-center" style="font-size:0.9rem; ${erpBg} ${accDataColor} overflow:hidden;">${stockInQtyDisplay}</td>
                    <td class="text-center" style="${erpBg} overflow:hidden;">${docStatusBadge}</td>
                    <td class="text-center" style="font-size:0.9rem; ${erpBg} ${accDataColor} overflow:hidden;">${approverDisplay}</td>
                    <td class="text-center" style="${erpBg} overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><code class="font-monospace" style="font-size:0.85rem;">${item.packid || '-'}</code></td>
                    <td class="text-center" style="font-size:0.9rem; ${accBg} overflow:hidden;">${packQtyHtml}</td>
                    <td class="text-center" style="font-size:0.9rem; ${accBg} overflow:hidden;">${accQtyHtml}</td>
                    <td class="text-center" style="font-size:0.9rem; ${commonBg} overflow:hidden;">${diffHtml}</td>
                    <td class="text-center" style="${commonBg} overflow:hidden;">${statusBadge}</td>
                </tr>`;
            });
            tbody.innerHTML = html;

            // 绑定混装提示框事件
            bindErpMixedIndicators();

            // 绑定差异提示图标事件（使用CustomTip实现美观提示）
            bindErpDiffIndicators();

            // 绑定状态提示图标事件（使用CustomTip实现美观的分层提示）
            bindErpStatusIndicators();
        } else {
            tbody.innerHTML = '<tr><td colspan="14" class="text-center text-muted" class="py-4"><i class="bi bi-inbox"></i> 暂无批次数据</td></tr>';
        }

        // 更新汇总行
        if (data.summary_row) {
            const sumPackQtyEl = document.getElementById('erpSumPackQty');
            const sumErpQtyEl = document.getElementById('erpSumErpQty');
            const sumStockInQtyEl = document.getElementById('erpSumStockInQty');
            const sumAccQtyEl = document.getElementById('erpSumAccQty');
            const diffSumEl = document.getElementById('erpSumDiff');
            if (sumPackQtyEl) sumPackQtyEl.textContent = data.summary_row.pack_total_qty_sum || 0;
            if (sumErpQtyEl) sumErpQtyEl.textContent = data.summary_row.erp_qty_sum || 0;
            if (sumStockInQtyEl) sumStockInQtyEl.textContent = stockInQtySum;
            if (sumAccQtyEl) sumAccQtyEl.textContent = data.summary_row.acc_qty_sum || 0;
            const diffSum = data.summary_row.diff_sum || 0;
            if (diffSumEl) {
                if (diffSum > 0) {
                    diffSumEl.innerHTML = `<span class="text-danger">+${diffSum}</span>`;
                } else if (diffSum < 0) {
                    diffSumEl.innerHTML = `<span class="text-success">${diffSum}</span>`;
                } else {
                    diffSumEl.innerHTML = '<span class="text-success">0</span>';
                }
            }
        }

        // 标记ERP详情已加载，避免页面切换回来时重复刷新
        erpDetailLoaded = true;
        log('ERP详情加载成功', 'success');
    } catch (e) {
        // 安全的元素更新函数
        const safeSet = (id, text) => {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        };
        // 重置汇总统计
        safeSet('erpDetailTotal', '-');
        safeSet('erpDetailBatchCount', '-');
        safeSet('erpDetailAccTotal', '-');
        safeSet('erpDetailDiff', '-');
        safeSet('erpDetailConsistency', '-');
        // 重置工单概述
        safeSet('erpMoBillNo', currentWono || '-');
        safeSet('erpMaterialNo', '-');
        safeSet('erpPlanQty', '-');
        safeSet('erpInStockQty', '-');
        safeSet('erpCloseDate', '-');
        safeSet('erpBizStatus', '-');
        const statusEl = document.getElementById('erpBizStatus');
        if (statusEl) statusEl.className = 'badge bg-secondary';
        // 重置汇总行
        safeSet('erpSumPackQty', '-');
        safeSet('erpSumErpQty', '-');
        safeSet('erpSumStockInQty', '-');
        safeSet('erpSumAccQty', '-');
        safeSet('erpSumDiff', '-');
        // 批次列表错误提示
        const bodyEl = document.getElementById('erpDetailBody');
        if (bodyEl) bodyEl.innerHTML = `<tr><td colspan="14" class="text-center text-danger py-4"><i class="bi bi-exclamation-triangle"></i> 网络错误: ${e.message}</td></tr>`;
        log('ERP详情加载异常: ' + e.message, 'error');
    }
}

// ============================================
//   差异提示框（未封包/待报工）
// ============================================

// 绑定ERP详情页面的差异提示图标事件
function bindErpDiffIndicators() {
    const indicators = document.querySelectorAll('.erp-diff-indicator');

    indicators.forEach(indicator => {
        // 检查是否已绑定，避免重复
        if (indicator._diffTipBound) return;

        const enterHandler = (e) => {
            e.preventDefault();
            e.stopPropagation();

            const diffType = indicator.dataset.diffType;
            const packid = indicator.dataset.packid;

            let title, content;
            if (diffType === 'unsealed') {
                title = '未封包批次';
                content = `<div style="color:#666;">批次号: ${packid}</div>`;
                content += `<div style="color:#17a2b8;margin-top:6px;">此批次尚未封包，不计入差异统计</div>`;
            } else if (diffType === 'pending_report') {
                title = '待报工批次';
                content = `<div style="color:#666;">批次号: ${packid}</div>`;
                content += `<div style="color:#17a2b8;margin-top:6px;">此批次已封包但尚未报工，不计入差异统计</div>`;
            } else if (diffType === 'duplicate_report') {
                const erpQty = indicator.dataset.erpQty || 0;
                title = '重复报工';
                content = `<div style="color:#666;">批次号: ${packid}</div>`;
                content += `<div style="color:#666;">ERP报工数量: ${erpQty}</div>`;
                content += `<div style="color:#ff9800;margin-top:6px;font-weight:600;">此批次为重复报工，差异不计入统计</div>`;
                content += `<div style="color:#999;font-size:0.9em;margin-top:4px;">同一批次已有其他汇报单号报工</div>`;
            }

            CustomTip.show(indicator, title, content);
        };

        const leaveHandler = () => {
            CustomTip.scheduleHide();
        };

        indicator.addEventListener('mouseenter', enterHandler);
        indicator.addEventListener('mouseleave', leaveHandler);

        indicator._diffEnterHandler = enterHandler;
        indicator._diffLeaveHandler = leaveHandler;
        indicator._diffTipBound = true;
    });
}

// ============================================
//   混装批次提示框
// ============================================

// 绑定ERP详情页面的混装提示图标事件
function bindErpMixedIndicators() {
    const indicators = document.querySelectorAll('.erp-mixed-indicator');

    indicators.forEach(indicator => {
        // 检查是否已绑定，避免重复
        if (indicator._mixedTipBound) return;

        // 移除默认title防止浏览器原生tooltip
        indicator.removeAttribute('title');
        indicator.removeAttribute('data-bs-toggle');

        const enterHandler = (e) => {
            e.preventDefault();
            e.stopPropagation();

            const packid = indicator.dataset.mixedPackid;
            let mixedDetail = [];
            try {
                mixedDetail = JSON.parse(indicator.dataset.mixedDetail || '[]');
            } catch(err) {
                console.log('解析混装详情失败:', err);
                return;
            }

            if (mixedDetail.length === 0) return;

            // 构建提示内容
            const title = `混装批次 (${mixedDetail.length}张工单)`;
            const totalQty = mixedDetail.reduce((sum, wo) => sum + (wo.qty || 0), 0);
            let content = `<div style="color:#666;">批次号: ${packid}</div>`;
            content += `<div style="color:#666;">包装总数: ${totalQty}<span style="color:#999;font-size:0.9em;margin-left:2px;">Pcs</span></div>`;
            content += `<div style="color:#ff9800;margin-top:4px;">各工单数量:</div>`;
            mixedDetail.forEach(wo => {
                // 高亮当前工单
                const isCurrentWo = wo.wono === currentWono;
                const style = isCurrentWo ? 'font-weight:600;color:#198754;' : '';
                const mark = isCurrentWo ? ' (当前)' : '';
                content += `<div style="padding-left:8px;${style}">- ${wo.wono}: ${wo.qty}<span style="color:#999;font-size:0.9em;margin-left:2px;">Pcs</span>${mark}</div>`;
            });

            CustomTip.show(indicator, title, content);
        };

        const leaveHandler = () => {
            CustomTip.scheduleHide();
        };

        indicator.addEventListener('mouseenter', enterHandler);
        indicator.addEventListener('mouseleave', leaveHandler);

        indicator._mixedEnterHandler = enterHandler;
        indicator._mixedLeaveHandler = leaveHandler;
        indicator._mixedTipBound = true;
    });
}

// ============================================
//   状态提示框（使用CustomTip实现美观分层效果）
// ============================================

// 绑定ERP详情页面的状态提示图标事件
function bindErpStatusIndicators() {
    const indicators = document.querySelectorAll('.erp-status-indicator');

    indicators.forEach(indicator => {
        // 检查是否已绑定，避免重复
        if (indicator._statusTipBound) return;

        const enterHandler = (e) => {
            e.preventDefault();
            e.stopPropagation();

            const tipType = indicator.dataset.tipType || 'warning'; // error 或 warning
            const tipTitle = indicator.dataset.tipTitle || '提示';
            const tipReasons = indicator.dataset.tipReasons || '';
            const tipResult = indicator.dataset.tipResult || '';

            // 黄色用于标签
            const labelColor = '#ff9800';

            let content = '';

            // 第一行：判定结果（黄色标签）
            content = `<div style="margin-bottom:8px;"><span style="color:${labelColor};font-weight:600;">判定结果：</span><span style="color:#333;font-weight:600;">${tipResult}</span></div>`;

            // 第二部分标签：人为删除用"详情如下："，其他用"判定原因："
            const secondLabel = tipTitle === '人为删除' ? '详情如下：' : '判定原因：';
            content += `<div style="border-top:1px solid #e0e0e0;padding-top:8px;">`;
            content += `<div style="color:${labelColor};font-weight:600;margin-bottom:4px;">${secondLabel}</div>`;

            // 原因/详情列表
            const reasons = tipReasons.split('|').filter(r => r.trim());
            reasons.forEach(reason => {
                content += `<div style="color:#333;padding-left:8px;">- ${reason}</div>`;
            });
            content += `</div>`;

            // 不传标题，取消顶部蓝色标题条
            CustomTip.show(indicator, '', content);
        };

        const leaveHandler = () => {
            CustomTip.scheduleHide();
        };

        indicator.addEventListener('mouseenter', enterHandler);
        indicator.addEventListener('mouseleave', leaveHandler);

        indicator._statusEnterHandler = enterHandler;
        indicator._statusLeaveHandler = leaveHandler;
        indicator._statusTipBound = true;
    });
}
