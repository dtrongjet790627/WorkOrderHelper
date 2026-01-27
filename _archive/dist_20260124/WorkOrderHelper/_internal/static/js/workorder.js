/**
 * workorder.js - 工单数据查询与处理
 * 设计：程远 | 2026-01-18
 * 包含：工单查询、ERP对比、未加入产品、未打包产品、打包操作
 */

// ============================================
//   工单查询
// ============================================

// 重置所有页面数据（工单数据 + HULU工单 + ERP详情）
function resetAllViews() {
    // 清空输入框
    document.getElementById('wonoInput').value = '';

    // 1. 重置工单数据页面
    resetWorkorderView();

    // 2. 重置HULU工单页面
    if (typeof resetHuluValues === 'function') {
        resetHuluValues();
    }
    if (typeof resetHuluListState === 'function') {
        resetHuluListState();
    }

    // 3. 重置ERP详情页面
    if (typeof resetErpDetail === 'function') {
        resetErpDetail();
    }

    // 4. 重置明细查询页面
    if (typeof resetDetailQuery === 'function') {
        resetDetailQuery();
    }

    // 重置数据变量
    currentWono = '';
    currentErpData = [];
    uploadedErpData = [];
    missingProductsData = [];
    selectedProducts.clear();
    updateSelectedCount();
    unpackedProductsData = [];
    selectedUnpackedProducts.clear();
    updateUnpackedSelectedCount();
    packBatchesData = { target_batches: [], reference_batch: null };
    packDataCache = [];
    compareDataCache = [];
    currentWorkorderLine = '';
    productStatusCache = {};
    huluDataCache = null;
    huluDataLoaded = false;
    erpDetailLoaded = false;

    // 重置操作日志视图
    const logWrapper = document.getElementById('logContentWrapper');
    if (logWrapper) logWrapper.innerHTML = '<div class="log-empty"><i class="bi bi-journal-text"></i><span>点击"刷新"加载日志</span></div>';

    // 切换回工单数据视图
    switchView('workorder');
}

// 重置工单数据页面到初始状态
function resetWorkorderView() {
    // 重置为空状态显示
    document.getElementById('missingProductsResult').style.display = 'none';
    document.getElementById('missingProductsInitial').style.display = 'block';
    document.getElementById('unpackedResult').style.display = 'none';
    document.getElementById('unpackedInitial').style.display = 'block';

    // 清空表格内容
    const unpackedTbody = document.getElementById('unpackedTable')?.getElementsByTagName('tbody')[0];
    if (unpackedTbody) unpackedTbody.innerHTML = '';
    const missingTbody = document.getElementById('missingProductsTable')?.getElementsByTagName('tbody')[0];
    if (missingTbody) missingTbody.innerHTML = '';

    // 重置"疑似未加入工单产品"区域
    const missingWoCount = document.getElementById('missingWoProductCount');
    if (missingWoCount) missingWoCount.textContent = '0';
    const missingFirstPass = document.getElementById('missingFirstPassCount');
    if (missingFirstPass) missingFirstPass.textContent = '0';
    const missingNotInWo = document.getElementById('missingNotInWoCount');
    if (missingNotInWo) missingNotInWo.textContent = '0';
    const missingPartno = document.getElementById('missingPartno');
    if (missingPartno) missingPartno.textContent = '-';
    const missingFirstOp = document.getElementById('missingFirstOp');
    if (missingFirstOp) missingFirstOp.textContent = '-';
    const missingTimeRange = document.getElementById('missingTimeRange');
    if (missingTimeRange) missingTimeRange.textContent = '-';
    const missingPageInfo = document.getElementById('missingProductsPageInfo');
    if (missingPageInfo) missingPageInfo.textContent = '共 0 条';

    // 重置"疑似未打包产品"区域
    const unpackedTotal = document.getElementById('unpackedTotalCount');
    if (unpackedTotal) unpackedTotal.textContent = '0';
    const generatedBatch = document.getElementById('generatedBatchId');
    if (generatedBatch) generatedBatch.textContent = '-';
    const unpackedPageInfo = document.getElementById('unpackedPageInfo');
    if (unpackedPageInfo) unpackedPageInfo.textContent = '共 0 条';
    // 重置合并的打包+ERP区域
    document.getElementById('packErpRefreshBtn').style.display = 'none';
    // 重置工单信息
    document.getElementById('totalCount').textContent = '-';
    document.getElementById('completedCount').textContent = '-';
    document.getElementById('incompleteCount').textContent = '-';
    document.getElementById('completionRate').textContent = '-';
    document.getElementById('headerWono').textContent = '-';
    document.getElementById('headerPartno').textContent = '-';
    document.getElementById('headerLine').textContent = '-';
    // 重置打包&ERP区域
    document.getElementById('packCount').textContent = '-';
    document.getElementById('packTotal').textContent = '-';
    document.getElementById('packInfoSum').textContent = '-';
    document.getElementById('erpTotalSum').textContent = '-';
    document.getElementById('erpBatchCount').textContent = '-';
    document.getElementById('diffTotalSum').textContent = '-';
    document.getElementById('packSealedCount').textContent = '-';
    document.getElementById('compareStatus').innerHTML = '<span class="text-muted">等待查询</span>';
    // 重置健康指标
    resetHealthIndicators();
    document.getElementById('headerWonoLabel').style.display = 'none';
}

// 兼容旧调用（保留clearResults函数名）
function clearResults() {
    resetAllViews();
}

async function queryWorkorder() {
    const wono = document.getElementById('wonoInput').value.trim();
    if (!wono) { alert('请输入工单号'); return; }

    // ==================== 查询前重置列表区域 ====================
    // 重置"疑似未加入工单产品"区域到待检测状态
    missingProductsData = [];
    selectedProducts.clear();
    productStatusCache = {};
    const missingTbody = document.getElementById('missingProductsTable')?.getElementsByTagName('tbody')[0];
    if (missingTbody) missingTbody.innerHTML = '';
    document.getElementById('missingProductsResult').style.display = 'none';
    document.getElementById('missingProductsInitial').style.display = 'block';
    document.getElementById('missingWoProductCount').textContent = '-';
    document.getElementById('missingFirstPassCount').textContent = '-';
    document.getElementById('missingNotInWoCount').textContent = '-';
    document.getElementById('missingPartno').textContent = '-';
    document.getElementById('missingFirstOp').textContent = '-';
    document.getElementById('missingTimeRange').textContent = '-';
    document.getElementById('missingProductsPageInfo').textContent = '共 0 条';
    // 重置"检测"按钮文字
    const missingQueryBtn = document.getElementById('missingQueryBtn');
    if (missingQueryBtn) missingQueryBtn.innerHTML = '<i class="bi bi-search"></i> 检测';
    updateSelectedCount();

    // 重置"疑似未打包产品"区域到待检测状态
    unpackedProductsData = [];
    selectedUnpackedProducts.clear();
    const unpackedTbody = document.getElementById('unpackedTable')?.getElementsByTagName('tbody')[0];
    if (unpackedTbody) unpackedTbody.innerHTML = '';
    document.getElementById('unpackedResult').style.display = 'none';
    document.getElementById('unpackedInitial').style.display = 'block';
    document.getElementById('unpackedTotalCount').textContent = '-';
    document.getElementById('generatedBatchId').textContent = '-';
    document.getElementById('unpackedPageInfo').textContent = '共 0 条';
    updateUnpackedSelectedCount();

    showLoading();
    try {
        // 获取当前操作人（从permission.js的currentUser）
        const operator = (typeof currentUser !== 'undefined' && currentUser.username) ? currentUser.username : '';
        const response = await fetch('/api/query_workorder', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ wono: wono, operator: operator })
        });

        const data = await response.json();
        if (data.error) { alert(data.error); return; }

        currentWono = wono;
        currentErpData = data.erp;

        // 保存到搜索历史
        saveSearchHistory(wono);

        const wo = data.workorder;
        document.getElementById('totalCount').textContent = wo.total;
        document.getElementById('completedCount').textContent = wo.completed;
        document.getElementById('incompleteCount').textContent = wo.incomplete;
        document.getElementById('completionRate').textContent = wo.completion_rate + '%';
        // 更新顶部标签
        document.getElementById('headerWono').textContent = wo.wono;
        document.getElementById('headerPartno').textContent = wo.partno;
        document.getElementById('headerLine').textContent = `${wo.line} (${wo.line_name})`;
        document.getElementById('headerWonoLabel').style.display = 'inline';

        document.getElementById('workorderInfo').style.display = 'block';

        // 缓存工单产线
        currentWorkorderLine = wo.line || '';

        // 打包数据缓存和概述卡片
        packDataCache = data.packs || [];
        let actualSum = 0, infoSum = 0, sealedCount = 0;
        packDataCache.forEach(p => {
            actualSum += p.actual_qty || 0;
            infoSum += p.info_qty || 0;
            if (p.status === '已封包') sealedCount++;
        });

        // 更新合并窗体的概述卡片
        document.getElementById('packCount').textContent = packDataCache.length;
        document.getElementById('packTotal').textContent = actualSum;
        document.getElementById('packSealedCount').textContent = sealedCount;
        document.getElementById('packCount').textContent = packDataCache.length;
        document.getElementById('packInfoSum').textContent = infoSum;
        document.getElementById('accTotalSum').textContent = actualSum;
        document.getElementById('erpTotalSum').textContent = '-';
        document.getElementById('erpBatchCount').textContent = '-';
        document.getElementById('diffTotalSum').textContent = '-';
        document.getElementById('compareStatus').innerHTML = '<i class="bi bi-hourglass-split"></i> 加载中...';

        // 检测其它工单产品
        updateOtherWoIndicator(packDataCache);

        // 显示刷新按钮
        document.getElementById('packErpRefreshBtn').style.display = 'inline-block';

        // 自动查询ERP对比
        compareAccErp();

        // ==================== 重置明细查询模块（新工单需要重新加载） ====================
        if (typeof resetDetailQuery === 'function') {
            resetDetailQuery();
        }
        // 注意：不自动加载明细查询数据，需要用户主动点击加载按钮

        // ==================== 未加入工单产品：显示待检测状态 ====================
        missingProductsData = [];
        selectedProducts.clear();

        const woInfo = data.workorder || {};
        const firstStation = data.first_station || {};
        const missingSummary = data.missing_summary || {};

        document.getElementById('missingPartno').textContent = woInfo.partno || '-';
        document.getElementById('missingFirstOp').textContent = firstStation.op || '-';
        document.getElementById('missingTimeRange').textContent = '点击检测后显示';

        document.getElementById('missingWoProductCount').textContent = missingSummary.wo_count || 0;
        document.getElementById('missingFirstPassCount').textContent = '-';
        document.getElementById('missingNotInWoCount').textContent = '-';

        // 显示待检测提示，不自动查询（耗时操作）
        document.getElementById('missingProductsResult').style.display = 'none';
        document.getElementById('missingProductsInitial').style.display = 'block';

        // ==================== 渲染未打包产品 ====================
        unpackedProductsData = data.unpacked_products || [];
        selectedUnpackedProducts.clear();

        document.getElementById('unpackedTotalCount').textContent = unpackedProductsData.length;
        renderUnpackedProducts();
        updateHealthIndicators(); // 先更新健康指标（不含HULU）
        fetchHuluDataSilent(); // 异步获取HULU数据，获取后会再次更新健康率

        // 异步预加载ERP详情数据，减少切换页面时的等待时间
        if (typeof refreshErpDetail === 'function') {
            setTimeout(() => {
                refreshErpDetail();
                erpDetailLoaded = true;
            }, 100);
        }

        // 异步预加载明细查询数据（包装列表、完工明细、在制明细）
        setTimeout(() => {
            if (typeof loadDetailPackList === 'function') {
                loadDetailPackList();
            }
            if (typeof loadFinishedProducts === 'function') {
                loadFinishedProducts();
            }
            if (typeof loadWipProducts === 'function') {
                loadWipProducts();
            }
        }, 200);

        document.getElementById('unpackedResult').style.display = 'flex';
        document.getElementById('unpackedInitial').style.display = 'none';

        updateSelectedCount();
        updateUnpackedSelectedCount();

        log(`查询工单 ${wono} 成功: 总数${wo.total}, 完工${wo.completed}, 疑似未打包${unpackedProductsData.length}件`, 'success');
        if (unpackedProductsData.length > 0) {
            log(`发现${unpackedProductsData.length}个疑似未打包产品，请处理`, 'warning');
        }

        // 注意：EAI日志模块独立，工单查询不影响EAI日志
        // autoQueryEaiLogsForWorkorder(); // 已移除，EAI日志始终显示最新记录

    } catch (e) {
        alert('查询失败: ' + e.message);
        log('查询失败: ' + e.message, 'error');
    } finally {
        hideLoading();
    }
}

// 静默刷新工单统计信息（不影响未加入产品区域）
async function refreshWorkorderStats() {
    if (!currentWono) return;

    try {
        const response = await fetch('/api/query_workorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wono: currentWono })
        });

        const data = await response.json();
        if (data.error) return;

        const wo = data.workorder;
        // 只更新工单统计数字
        document.getElementById('totalCount').textContent = wo.total;
        document.getElementById('completedCount').textContent = wo.completed;
        document.getElementById('incompleteCount').textContent = wo.incomplete;
        document.getElementById('completionRate').textContent = wo.completion_rate + '%';

        // 更新打包数据
        packDataCache = data.packs || [];
        let actualSum = 0, sealedCount = 0;
        packDataCache.forEach(p => {
            actualSum += p.actual_qty || 0;
            if (p.status === '已封包') sealedCount++;
        });
        document.getElementById('packCount').textContent = packDataCache.length;
        document.getElementById('packTotal').textContent = actualSum;
        document.getElementById('packSealedCount').textContent = sealedCount;
        document.getElementById('accTotalSum').textContent = actualSum;

        // 更新未打包产品（同时更新上方卡片和下方区域）
        unpackedProductsData = data.unpacked_products || [];
        document.getElementById('unpackedCount').textContent = unpackedProductsData.length;  // 上方卡片
        document.getElementById('unpackedTotalCount').textContent = unpackedProductsData.length;  // 下方区域
        renderUnpackedProducts();

        // 更新健康度
        if (typeof updateHealthScore === 'function') {
            updateHealthScore();
        }

        log('工单统计已刷新', 'info');
    } catch (e) {
        console.log('静默刷新失败: ' + e.message);
    }
}

// ============================================
//   ERP文件上传与对比
// ============================================
async function uploadErpFile() {
    const fileInput = document.getElementById('erpFile');
    if (!fileInput.files.length) { alert('请选择文件'); return; }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    showLoading();
    try {
        const response = await fetch('/api/upload_erp', { method: 'POST', body: formData });
        const data = await response.json();
        if (data.error) { alert(data.error); return; }

        uploadedErpData = data.batches;
        let excelTotal = data.batches.reduce((sum, b) => sum + b.qty, 0);
        let dbTotal = currentErpData.reduce((sum, e) => sum + e.qty, 0);
        log(`解析Excel成功: Excel总数${excelTotal}, ERP总数${dbTotal}, 差异${dbTotal - excelTotal}`, 'success');

    } catch (e) {
        alert('上传失败: ' + e.message);
    } finally {
        hideLoading();
    }
}

async function compareAccErp() {
    if (!currentWono) { alert('请先查询工单'); return; }

    document.getElementById('compareStatus').innerHTML = '<span class="text-primary"><span class="spinner-border spinner-border-sm"></span> 查询ERP中...</span>';
    document.getElementById('erpTotalSum').textContent = '...';
    document.getElementById('erpBatchCount').textContent = '...';
    document.getElementById('diffTotalSum').textContent = '...';

    try {
        const response = await fetch('/api/compare_acc_erp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wono: currentWono })
        });
        const data = await response.json();
        if (data.error) {
            // API返回错误（如数据库连接失败）
            document.getElementById('compareStatus').innerHTML = `<span class="text-warning" title="${data.error}"><i class="bi bi-exclamation-triangle"></i> ERP暂不可用</span>`;
            document.getElementById('erpTotalSum').textContent = '-';
            document.getElementById('erpBatchCount').textContent = '-';
            document.getElementById('diffTotalSum').textContent = '-';
            log('ERP查询失败: ' + data.error, 'error');
            return;
        }

                        // 缓存对比数据
        compareDataCache = data.comparison || [];

        // === 分区数据：已封包 vs 打包中 ===
        const sealedData = data.sealed_comparison || compareDataCache;
        const packingData = data.packing_comparison || [];

        // 渲染单行的辅助函数
        function renderCompareRow(c, isPacking) {
            const isContinuation = c.status === 'continuation';
            const accQtyText = c.acc_qty !== null ? c.acc_qty : '';

            let diffClass = 'text-muted';
            let diffText = '-';
            // 打包中批次不显示差异
            if (!isPacking && c.diff !== null) {
                diffText = c.diff;
                if (c.diff > 0) { diffClass = 'text-success fw-bold'; diffText = '+' + c.diff; }
                else if (c.diff < 0) { diffClass = 'text-danger fw-bold'; }
            }

            let rowClass = isPacking ? 'table-secondary' : '';
            if (!isPacking) {
                if (isContinuation) { rowClass = 'table-light'; }
                else if (c.status !== 'match') { rowClass = 'table-warning'; }
            }

            const packidText = isContinuation ? `<span class="text-muted ps-2">↳ ${c.packid}</span>` : c.packid;
            const billNoText = c.bill_no || '';
            const packingBadge = isPacking ? ' <span class="badge bg-info text-dark">打包中</span>' : '';

            return `
                <td class="${rowClass}">${packidText}${packingBadge}</td>
                <td class="text-end ${rowClass}">${accQtyText}</td>
                <td class="text-end ${rowClass}">${c.erp_qty || '-'}</td>
                <td class="${rowClass}"><small>${billNoText}</small></td>
                <td class="text-end ${isPacking ? 'text-muted' : diffClass}">${diffText}</td>
            `;
        }

        // 渲染对比表格（用于模态框）
        const compareTable = document.getElementById('compareTable').getElementsByTagName('tbody')[0];
        compareTable.innerHTML = '';

        // 先渲染已封包批次
        sealedData.forEach(c => {
            compareTable.insertRow().innerHTML = renderCompareRow(c, false);
        });

        // 再渲染打包中批次（如果有）
        if (packingData.length > 0) {
            // 添加分隔行
            const separatorRow = compareTable.insertRow();
            separatorRow.innerHTML = '<td colspan="5" class="bg-light text-muted py-1 small"><i class="bi bi-hourglass-split"></i> 以下为打包中批次（不计入差异）</td>';

            packingData.forEach(c => {
                compareTable.insertRow().innerHTML = renderCompareRow(c, true);
            });
        }

        // 更新概述卡片
        document.getElementById('accTotalSum').textContent = data.acc_total;
        document.getElementById('erpTotalSum').textContent = data.erp_total;
        document.getElementById('erpBatchCount').textContent = data.erp_batch_count || '-';
        // 使用封包批次的差异值（打包中的批次不计入差异）
        const actualDiffTotal = data.sealed_diff_total !== undefined ? data.sealed_diff_total : data.diff_total;
        let diffTotalClass = actualDiffTotal > 0 ? 'text-success' : (actualDiffTotal < 0 ? 'text-danger' : '');
        let diffTotalText = actualDiffTotal > 0 ? '+' + actualDiffTotal : actualDiffTotal;
        // 只显示差异数量，批次信息已在后面的状态中显示
        document.getElementById('diffTotalSum').innerHTML = `<span class="${diffTotalClass}">${diffTotalText}</span>`;

        // 更新模态框汇总
        document.getElementById('modalAccTotalSum').textContent = data.acc_total;
        document.getElementById('modalErpTotalSum').textContent = data.erp_total;
        document.getElementById('modalDiffTotalSum').innerHTML = `<span class="${diffTotalClass}">${diffTotalText}</span>`;

        // 更新状态（简化显示）
        let statusHtml = '';
        const mismatchCount = data.summary.mismatch_count || 0;
        const duplicateCount = data.summary.duplicate_count || 0;

        if (mismatchCount === 0 && duplicateCount === 0) {
            statusHtml = `<span class="text-success"><i class="bi bi-check-circle"></i> 一致</span>`;
        } else {
            let parts = [];
            if (mismatchCount > 0) {
                parts.push(`${mismatchCount}批不匹配`);
            }
            if (duplicateCount > 0) {
                parts.push(`${duplicateCount}批重复报工`);
            }
            statusHtml = `<span class="text-warning"><i class="bi bi-exclamation-triangle"></i> ${parts.join('，')}</span>`;
        }
        document.getElementById('compareStatus').innerHTML = statusHtml;

        // 显示刷新按钮
        document.getElementById('packErpRefreshBtn').style.display = 'inline-block';

        const sealedDiff = data.sealed_diff_total !== undefined ? data.sealed_diff_total : data.diff_total;
        log(`ACC-ERP对比完成: ACC=${data.acc_total}, ERP=${data.erp_total}, 封包差异=${sealedDiff}`,
            sealedDiff === 0 ? 'success' : 'warning');
        updateHealthIndicators(); // 更新健康指标

    } catch (e) {
        // 网络错误或其他异常
        document.getElementById('compareStatus').innerHTML = `<span class="text-warning" title="${e.message}"><i class="bi bi-exclamation-triangle"></i> 网络异常</span>`;
        document.getElementById('erpTotalSum').textContent = '-';
        document.getElementById('erpBatchCount').textContent = '-';
        document.getElementById('diffTotalSum').textContent = '-';
        log('ERP对比查询异常: ' + e.message, 'error');
    }
}

// ============================================
//   未加入工单产品相关
// ============================================
async function queryMissingProducts() {
    if (!currentWono) { alert('请先查询工单'); return; }

    const btn = document.getElementById('missingQueryBtn');
    const originalBtnHtml = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 检测中...';
    btn.disabled = true;

    showLoading();
    log(`开始检测工单 ${currentWono} 未加入产品（耗时操作）...`, 'warning');

    try {
        const response = await fetch('/api/query_missing_products', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wono: currentWono })
        });

        const data = await response.json();
        if (data.error) { alert('查询失败: ' + data.error); log(data.error, 'error'); return; }

        missingProductsData = data.missing_products || [];
        selectedProducts.clear();

        const woInfo = data.workorder_info || {};
        const firstStation = data.first_station || {};
        const summary = data.summary || {};

        document.getElementById('missingTimeRange').textContent = `${woInfo.start_time || '-'} 至 ${woInfo.end_time || '-'}`;
        document.getElementById('missingPartno').textContent = woInfo.partno || '-';
        document.getElementById('missingFirstOp').textContent = firstStation.op || '-';

        document.getElementById('missingWoProductCount').textContent = summary.wo_count || 0;
        document.getElementById('missingFirstPassCount').textContent = summary.first_station_count || 0;
        document.getElementById('missingNotInWoCount').textContent = summary.missing_count || 0;

        renderMissingProducts();
        updateSelectedCount();
        updateHealthIndicators(); // 更新健康指标

        document.getElementById('missingProductsInitial').style.display = 'none';
        document.getElementById('missingProductsResult').style.display = 'flex';

        // 更新按钮为刷新状态
        btn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> 重新检测';

        log(`检测完成: 工单内${summary.wo_count}件, 首站PASS${summary.first_station_count}件, 疑似未加入${summary.missing_count}件`, 'success');

    } catch (e) {
        alert('查询失败: ' + e.message);
        log('查询异常: ' + e.message, 'error');
        btn.innerHTML = originalBtnHtml;
    } finally {
        btn.disabled = false;
        hideLoading();
    }
}

function toggleProductSelect(sn, checkbox) {
    const row = checkbox.closest('tr');
    if (checkbox.checked) {
        selectedProducts.add(sn);
        row.classList.add('selected');
    } else {
        selectedProducts.delete(sn);
        row.classList.remove('selected');
    }
    updateSelectedCount();
}

function toggleSelectAll(checkbox) {
    document.querySelectorAll('.product-checkbox').forEach(cb => {
        cb.checked = checkbox.checked;
        const sn = cb.dataset.sn;
        const row = cb.closest('tr');
        if (checkbox.checked) {
            selectedProducts.add(sn);
            row.classList.add('selected');
        } else {
            selectedProducts.delete(sn);
            row.classList.remove('selected');
        }
    });
    updateSelectedCount();
}

function selectAllProducts() {
    document.getElementById('selectAllCheckbox').checked = true;
    toggleSelectAll(document.getElementById('selectAllCheckbox'));
}

function deselectAllProducts() {
    document.getElementById('selectAllCheckbox').checked = false;
    toggleSelectAll(document.getElementById('selectAllCheckbox'));
}

function updateSelectedCount() {
    document.getElementById('selectedCount').textContent = selectedProducts.size;
}

async function addSelectedToWorkorder() {
    if (selectedProducts.size === 0) {
        alert('请先选择要加入的产品');
        return;
    }

    // 数量验证：检查是否超出工单计划数量
    showLoading();
    log(`正在验证工单数量限制... 工单号=${currentWono}, 选中数量=${selectedProducts.size}`);

    try {
        const validateResponse = await fetch('/api/validate_add_quantity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                wono: currentWono,
                add_count: selectedProducts.size
            })
        });

        const validateData = await validateResponse.json();
        hideLoading();

        // 打印完整的验证返回数据，便于调试
        console.log('[数量验证] 接口返回:', validateData);

        if (validateData.error) {
            alert('数量验证失败: ' + validateData.error);
            log('数量验证失败: ' + validateData.error, 'error');
            return;
        }

        // 如果有警告但允许继续（如无法获取计划数量）
        if (validateData.warning) {
            log('数量验证警告: ' + validateData.warning, 'warning');
            console.warn('[数量验证] 警告:', validateData.warning);
        }

        // 验证不通过，显示超出提示
        if (!validateData.valid) {
            const detail = validateData.detail;
            showQuantityExceedModal(detail);
            log(`数量验证不通过: 计划${detail.plan_quantity}, 当前${detail.current_count}, 本次${detail.add_count}, 超出${detail.exceed_count}`, 'warning');
            return;
        }

        // 验证通过，显示确认弹窗
        document.getElementById('modalSelectedCount').textContent = selectedProducts.size;
        document.getElementById('modalWono').textContent = currentWono;

        // 如果有计划数量信息，显示在确认弹窗中
        const quantityInfoEl = document.getElementById('modalQuantityInfo');
        if (quantityInfoEl && validateData.detail && validateData.detail.plan_quantity !== null) {
            const d = validateData.detail;
            quantityInfoEl.innerHTML = `
                <div class="alert alert-info small mb-2">
                    <i class="bi bi-info-circle"></i>
                    计划数量: ${d.plan_quantity} | 当前已加入: ${d.current_count} | 本次加入: ${d.add_count} | 剩余额度: ${d.remaining}
                </div>
            `;
            quantityInfoEl.style.display = 'block';
        } else if (quantityInfoEl) {
            quantityInfoEl.style.display = 'none';
        }

        new bootstrap.Modal(document.getElementById('addToWoModal')).show();
        if (validateData.detail) {
            log(`数量验证通过: 计划=${validateData.detail.plan_quantity}, 当前=${validateData.detail.current_count}, 本次=${validateData.detail.add_count}`, 'success');
        } else {
            log('数量验证通过', 'success');
        }

    } catch (e) {
        hideLoading();
        alert('数量验证异常: ' + e.message);
        log('数量验证异常: ' + e.message, 'error');
    }
}

// 显示数量超出提示弹窗
function showQuantityExceedModal(detail) {
    const content = `
        <div class="text-center mb-3">
            <i class="bi bi-exclamation-triangle-fill text-warning" style="font-size: 3rem;"></i>
        </div>
        <table class="table table-bordered table-sm">
            <tr>
                <th class="text-end" style="width: 50%;">工单计划数量</th>
                <td><strong>${detail.plan_quantity}</strong></td>
            </tr>
            <tr>
                <th class="text-end">当前已加入</th>
                <td>${detail.current_count}</td>
            </tr>
            <tr>
                <th class="text-end">本次选择</th>
                <td>${detail.add_count}</td>
            </tr>
            <tr class="table-warning">
                <th class="text-end">合计</th>
                <td><strong>${detail.total_after_add}</strong></td>
            </tr>
            <tr class="table-danger">
                <th class="text-end">超出</th>
                <td><strong class="text-danger">${detail.exceed_count}</strong></td>
            </tr>
        </table>
        <div class="alert alert-warning small mb-0">
            <i class="bi bi-info-circle"></i> 请取消部分产品后重试，或联系管理员调整工单计划数量。
        </div>
    `;
    showResultModal('warning', '超出工单计划数量', content);
}

async function confirmAddToWorkorder() {
    // 前置权限检查
    if (typeof checkOperationPermission === 'function' && !checkOperationPermission('加入工单')) {
        return;
    }

    bootstrap.Modal.getInstance(document.getElementById('addToWoModal')).hide();
    showLoading();
    log(`开始将 ${selectedProducts.size} 个产品加入工单 ${currentWono}...`);

    try {
        const response = await fetch('/api/add_missing_products', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                wono: currentWono,
                unitsn_list: Array.from(selectedProducts),
                operator_id: typeof getOperatorId === 'function' ? getOperatorId() : ''
            })
        });

        const data = await response.json();
        if (data.error) {
            // 处理权限错误
            if (data.permission_error) {
                showResultModal('error', '无操作权限', `原因: ${data.reason}`);
                log(`加入工单被拒绝: ${data.reason}`, 'error');
                return;
            }
            showResultModal('error', '操作失败', data.error);
            log('加入工单失败: ' + data.error, 'error');
            return;
        }

        let resultHtml = `<p>成功加入工单: <strong class="text-success">${data.inserted_count}</strong> 件产品</p>`;
        if (data.skipped_count > 0) {
            resultHtml += `<p>跳过(已存在): <strong class="text-warning">${data.skipped_count}</strong> 件</p>`;
        }
        resultHtml += '<hr><div class="small" style="max-height:200px;overflow-y:auto;">';
        data.results.forEach(r => {
            if (r.action === 'inserted') {
                resultHtml += `<div class="text-success"><i class="bi bi-check"></i> ${r.unitsn} - ${r.status_desc}</div>`;
            } else {
                resultHtml += `<div class="text-warning"><i class="bi bi-dash"></i> ${r.unitsn} - ${r.reason}</div>`;
            }
        });
        resultHtml += '</div>';

        showResultModal('success', '操作完成', resultHtml);
        log(`加入工单完成: 插入${data.inserted_count}件, 跳过${data.skipped_count}件`, 'success');

        // 获取成功插入的产品SN列表
        const insertedSns = new Set();
        data.results.forEach(r => {
            if (r.action === 'inserted') {
                insertedSns.add(r.unitsn);
            }
        });

        // 从当前显示的列表中移除已成功插入的产品
        if (insertedSns.size > 0) {
            missingProductsData = missingProductsData.filter(item => !insertedSns.has(item.unitsn));
            // 同时清理状态缓存中已插入的产品
            insertedSns.forEach(sn => {
                delete productStatusCache[sn];
            });
        }

        // 清空选中状态
        selectedProducts.clear();
        updateSelectedCount();

        // 重新渲染列表（不调用检测接口）
        renderMissingProducts();

        // 更新未加入数量显示（仅扣减，不清空）
        document.getElementById('missingNotInWoCount').textContent = missingProductsData.length;

        // 更新工单内产品数量（仅增加插入数量）
        const woProductCountEl = document.getElementById('missingWoProductCount');
        if (woProductCountEl && woProductCountEl.textContent !== '-') {
            const currentCount = parseInt(woProductCountEl.textContent) || 0;
            woProductCountEl.textContent = currentCount + data.inserted_count;
        }

        // 静默刷新工单统计信息（不影响未加入产品区域）
        refreshWorkorderStats();

    } catch (e) {
        showResultModal('error', '操作失败', e.message);
        log('操作异常: ' + e.message, 'error');
    } finally {
        hideLoading();
    }
}

// 点击SN显示产品状态详情（使用缓存数据）
function showProductStatusDetail(sn) {
    const cached = productStatusCache[sn];
    let content = '';

    if (cached) {
        const statusText = cached.unitstatus === 2 ?
            '<span class="badge bg-success">已下线(合格)</span>' :
            (cached.unitstatus ? `<span class="badge bg-warning">${cached.final_status_desc}</span>` : '<span class="badge bg-warning text-dark">无状态记录</span>');

        content = `
            <table class="table table-sm">
                <tr><th width="120">产品序列号</th><td><code>${sn}</code></td></tr>
                <tr><th>acc_unitstatus</th><td><strong>${cached.unitstatus !== null ? cached.unitstatus : '无记录'}</strong></td></tr>
                <tr><th>产线(line)</th><td>${cached.line || '-'}</td></tr>
                <tr><th>下线状态</th><td>${statusText}</td></tr>
            </table>
            <div class="alert alert-info small mb-0">
                <i class="bi bi-info-circle"></i> 判断规则：acc_unitstatus.status=2 即为成功下线（合格品）
            </div>
        `;
    } else {
        content = `<p>产品 <code>${sn}</code> 状态数据未加载，请等待查询完成或重新查询。</p>`;
    }

    showResultModal('info', '产品状态详情', content);
}

// 兼容旧函数名
function checkSingleProduct(sn) {
    showProductStatusDetail(sn);
}

function exportMissingProducts() {
    if (missingProductsData.length === 0) { alert('没有数据可导出'); return; }
    log(`导出未加入工单产品列表，共${missingProductsData.length}条`);

    let csvContent = '\ufeff序号,产品序列号(SN),首站过站时间\n';
    missingProductsData.forEach((item, index) => {
        csvContent += `${index + 1},${item.unitsn || ''},${item.createtime || ''}\n`;
    });

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `未加入工单产品_${currentWono}_${new Date().toISOString().slice(0,10)}.csv`;
    link.click();
    log('导出完成', 'success');
}

// 渲染未加入工单产品列表
function renderMissingProducts() {
    const tbody = document.getElementById('missingProductsTable').getElementsByTagName('tbody')[0];
    tbody.innerHTML = '';

    if (missingProductsData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-success py-4"><i class="bi bi-check-circle"></i> 没有发现疑似未加入工单的产品</td></tr>';
    } else {
        missingProductsData.forEach((item, index) => {
            const sn = item.unitsn || '';
            const row = tbody.insertRow();
            row.className = 'product-row';
            row.dataset.sn = sn;
            // 点击SN显示状态详情，取消单独的操作按钮
            row.innerHTML = `
                <td><input type="checkbox" class="product-checkbox" data-sn="${sn}" onchange="toggleProductSelect('${sn}', this)"></td>
                <td>${index + 1}</td>
                <td><code class="sn-clickable" style="cursor:pointer;" onclick="showProductStatusDetail('${sn}')">${sn}</code></td>
                <td id="status-${sn.replace(/[^a-zA-Z0-9]/g, '_')}"><span class="status-badge" style="background:#e9ecef;color:#666;"><i class="bi bi-hourglass-split"></i> 检测中</span></td>
            `;
        });
        // 批量查询产品状态
        fetchMissingProductsStatus();
    }

    document.getElementById('missingProductsPageInfo').textContent = `共 ${missingProductsData.length} 条`;
    document.getElementById('selectAllCheckbox').checked = false;

    // 确保结果区域显示，初始提示隐藏
    document.getElementById('missingProductsInitial').style.display = 'none';
    document.getElementById('missingProductsResult').style.display = 'flex';
}

// 存储产品状态数据，供点击查看详情使用
let productStatusCache = {};

// 批量查询未加入工单产品的下线状态
async function fetchMissingProductsStatus() {
    if (missingProductsData.length === 0 || !currentWono) return;

    const snList = missingProductsData.map(item => item.unitsn);
    log(`正在查询${snList.length}个产品的下线状态...`);

    try {
        const response = await fetch('/api/check_product_status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wono: currentWono, unitsn_list: snList })
        });
        const data = await response.json();
        if (data.error) {
            log('状态查询失败: ' + data.error, 'error');
            snList.forEach(sn => {
                const statusCell = document.getElementById('status-' + sn.replace(/[^a-zA-Z0-9]/g, '_'));
                if (statusCell) {
                    statusCell.innerHTML = '<span class="status-badge" style="background:#f8d7da;color:#842029;">查询失败</span>';
                }
            });
            return;
        }

        // 缓存状态数据
        const products = data.products || [];
        products.forEach(p => {
            productStatusCache[p.unitsn] = p;
            const statusCell = document.getElementById('status-' + p.unitsn.replace(/[^a-zA-Z0-9]/g, '_'));
            if (statusCell) {
                // 简化逻辑：只要unitstatus=2就是已下线(合格)
                if (p.unitstatus === 2) {
                    statusCell.innerHTML = '<span class="status-badge" style="background:#d1e7dd;color:#0f5132;"><i class="bi bi-check-circle"></i> 已下线(合格)</span>';
                } else if (p.unitstatus !== null && p.unitstatus !== undefined) {
                    statusCell.innerHTML = `<span class="status-badge" style="background:#fff3cd;color:#856404;"><i class="bi bi-exclamation-circle"></i> ${p.final_status_desc}</span>`;
                } else {
                    statusCell.innerHTML = '<span class="status-badge" style="background:#f8d7da;color:#842029;"><i class="bi bi-x-circle"></i> 无状态记录</span>';
                }
            }
        });

        log(`产品状态查询完成`, 'success');

    } catch (e) {
        log('状态查询异常: ' + e.message, 'error');
        snList.forEach(sn => {
            const statusCell = document.getElementById('status-' + sn.replace(/[^a-zA-Z0-9]/g, '_'));
            if (statusCell) {
                statusCell.innerHTML = '<span class="status-badge" style="background:#f8d7da;color:#842029;">查询失败</span>';
            }
        });
    }
}

// ============================================
//   未打包产品相关
// ============================================
function renderUnpackedProducts() {
    const tbody = document.getElementById('unpackedTable').getElementsByTagName('tbody')[0];
    tbody.innerHTML = '';

    if (unpackedProductsData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-success py-4"><i class="bi bi-check-circle"></i> 没有发现疑似未打包的产品</td></tr>';
    } else {
        unpackedProductsData.forEach((item, index) => {
            const sn = item.unitsn || '';
            const row = tbody.insertRow();
            row.className = 'product-row';
            row.dataset.sn = sn;
            row.innerHTML = `
                <td><input type="checkbox" class="unpacked-checkbox" data-sn="${sn}" onchange="toggleUnpackedSelect('${sn}', this)"></td>
                <td>${index + 1}</td>
                <td><code>${sn}</code></td>
                <td><span class="status-badge status-complete">完成</span></td>
            `;
        });
    }

    document.getElementById('unpackedPageInfo').textContent = `共 ${unpackedProductsData.length} 条`;
    document.getElementById('selectAllUnpackedCheckbox').checked = false;
}

async function queryUnpackedProducts() {
    if (!currentWono) { alert('请先查询工单'); return; }

    showLoading();
    log(`刷新工单 ${currentWono} 未打包产品...`);

    try {
        const response = await fetch('/api/query_unpacked_products', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wono: currentWono })
        });

        const data = await response.json();
        if (data.error) { alert('查询失败: ' + data.error); log(data.error, 'error'); return; }

        unpackedProductsData = data.unpacked_products || [];
        selectedUnpackedProducts.clear();

        document.getElementById('unpackedTotalCount').textContent = unpackedProductsData.length;
        renderUnpackedProducts();
        updateUnpackedSelectedCount();

        document.getElementById('unpackedInitial').style.display = 'none';
        document.getElementById('unpackedResult').style.display = 'flex';

        log(`刷新完成: 发现${unpackedProductsData.length}个疑似未打包产品`, 'success');

    } catch (e) {
        alert('查询失败: ' + e.message);
        log('查询异常: ' + e.message, 'error');
    } finally {
        hideLoading();
    }
}

function toggleUnpackedSelect(sn, checkbox) {
    const row = checkbox.closest('tr');
    if (checkbox.checked) {
        selectedUnpackedProducts.add(sn);
        row.classList.add('selected');
    } else {
        selectedUnpackedProducts.delete(sn);
        row.classList.remove('selected');
    }
    updateUnpackedSelectedCount();
}

function toggleSelectAllUnpacked(checkbox) {
    document.querySelectorAll('.unpacked-checkbox').forEach(cb => {
        cb.checked = checkbox.checked;
        const sn = cb.dataset.sn;
        const row = cb.closest('tr');
        if (checkbox.checked) {
            selectedUnpackedProducts.add(sn);
            row.classList.add('selected');
        } else {
            selectedUnpackedProducts.delete(sn);
            row.classList.remove('selected');
        }
    });
    updateUnpackedSelectedCount();
}

function selectAllUnpacked() {
    document.getElementById('selectAllUnpackedCheckbox').checked = true;
    toggleSelectAllUnpacked(document.getElementById('selectAllUnpackedCheckbox'));
}

function deselectAllUnpacked() {
    document.getElementById('selectAllUnpackedCheckbox').checked = false;
    toggleSelectAllUnpacked(document.getElementById('selectAllUnpackedCheckbox'));
}

function updateUnpackedSelectedCount() {
    document.getElementById('unpackedSelectedCount').textContent = selectedUnpackedProducts.size;
}

// ============================================
//   打包操作
// ============================================
async function getPackBatches() {
    if (!currentWono) { alert('请先查询工单'); return; }

    showLoading();
    log('获取可用打包批次...');

    try {
        const response = await fetch('/api/get_pack_batches', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wono: currentWono })
        });

        const data = await response.json();
        if (data.error) { alert('获取失败: ' + data.error); log(data.error, 'error'); return; }

        packBatchesData = data;

        // 更新下拉框
        const select = document.getElementById('targetBatchSelect');
        select.innerHTML = '<option value="">-- 选择目标批次 --</option>';

        if (data.target_batches && data.target_batches.length > 0) {
            data.target_batches.forEach(batch => {
                const option = document.createElement('option');
                option.value = batch.packid;
                option.textContent = `${batch.packid} (规格:${batch.packsize}, 当前:${batch.currquantity})`;
                select.appendChild(option);
            });
            log(`获取到${data.target_batches.length}个可用批次`, 'success');
        } else {
            select.innerHTML = '<option value="">-- 无可用批次(currquantity=0) --</option>';
            log('没有找到currquantity=0的批次', 'warning');
        }

        if (data.reference_batch) {
            log(`参考批次: ${data.reference_batch.packid}`, 'info');
        }

    } catch (e) {
        alert('获取失败: ' + e.message);
        log('获取异常: ' + e.message, 'error');
    } finally {
        hideLoading();
    }
}

async function executePackingAction() {
    if (selectedUnpackedProducts.size === 0) {
        alert('请先选择要打包的产品');
        return;
    }

    showLoading();
    log('正在自动生成批次号...');

    try {
        // 自动生成批次号
        const genResponse = await fetch('/api/generate_pack_id', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wono: currentWono })
        });

        const genData = await genResponse.json();
        if (genData.error) {
            hideLoading();
            alert('生成批次号失败: ' + genData.error);
            log('生成批次号失败: ' + genData.error, 'error');
            return;
        }

        const targetBatch = genData.pack_id;
        document.getElementById('generatedBatchId').textContent = targetBatch;
        log('已生成批次号: ' + targetBatch, 'success');

        hideLoading();
        document.getElementById('packingModalCount').textContent = selectedUnpackedProducts.size;
        document.getElementById('packingModalBatch').textContent = targetBatch;
        // 存储生成的批次号供confirmPacking使用
        window.generatedPackId = targetBatch;
        new bootstrap.Modal(document.getElementById('packingModal')).show();
    } catch (e) {
        hideLoading();
        alert('生成批次号失败: ' + e.message);
        log('生成批次号异常: ' + e.message, 'error');
    }
}

async function confirmPacking() {
    // 前置权限检查
    if (typeof checkOperationPermission === 'function' && !checkOperationPermission('执行打包')) {
        return;
    }

    bootstrap.Modal.getInstance(document.getElementById('packingModal')).hide();
    showLoading();

    const targetBatch = window.generatedPackId;
    log(`开始补打包: ${selectedUnpackedProducts.size}个产品 → 批次${targetBatch}...`);

    try {
        const response = await fetch('/api/execute_packing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                wono: currentWono,
                target_packid: targetBatch,
                unitsn_list: Array.from(selectedUnpackedProducts),
                operator_id: typeof getOperatorId === 'function' ? getOperatorId() : ''
            })
        });

        const data = await response.json();
        if (data.error) {
            // 处理权限错误
            if (data.permission_error) {
                showResultModal('error', '无操作权限', `原因: ${data.reason}`);
                log(`打包被拒绝: ${data.reason}`, 'error');
                return;
            }
            showResultModal('error', '打包失败', data.error);
            log('打包失败: ' + data.error, 'error');
            return;
        }

        let resultHtml = `<p>成功打包: <strong class="text-success">${data.packed_count}</strong> 件</p>`;
        resultHtml += `<p>目标批次: <code>${targetBatch}</code></p>`;
        if (data.updated_currquantity !== undefined) {
            resultHtml += `<p>批次当前数量: ${data.updated_currquantity}</p>`;
        }

        showResultModal('success', '打包完成', resultHtml);
        log(`打包完成: 成功${data.packed_count}件`, 'success');

        // 刷新数据（不影响未加入工单产品区域）
        selectedUnpackedProducts.clear();
        updateUnpackedSelectedCount();
        refreshWorkorderStats(); // 静默刷新工单统计和未打包产品

    } catch (e) {
        showResultModal('error', '操作失败', e.message);
        log('操作异常: ' + e.message, 'error');
    } finally {
        hideLoading();
    }
}

// ============================================
//   回车键查询
// ============================================
document.getElementById('wonoInput').addEventListener('keypress', e => {
    if (e.key === 'Enter') queryWorkorder();
});
