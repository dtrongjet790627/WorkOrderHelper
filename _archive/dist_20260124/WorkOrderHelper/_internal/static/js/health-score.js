/**
 * health-score.js - 健康率计算模块
 * 设计：程远 | 2026-01-18
 * 包含：健康率V4.0算法、健康指标更新、其它工单指示器
 */

// ============================================
//   健康率考核方案 V4.0
//   核心机制：每个大项权重拆成50%基准分+50%差异分
//   有差异先扣50%权重，再按差异占比分档扣剩余50%
// ============================================

// 差异档位扣减比例计算函数
function getDiffDeductRate(diffRate) {
    if (diffRate <= 0) return 0;
    if (diffRate <= 0.05) return 0.20;  // >0%-5%
    if (diffRate <= 0.10) return 0.40;  // >5%-10%
    if (diffRate <= 0.15) return 0.60;  // >10%-15%
    if (diffRate <= 0.20) return 0.80;  // >15%-20%
    return 1.00;  // >20%
}

// 计算单项得分（返回该项对综合健康率的贡献百分比）
function calcItemScore(totalWeight, diffRate) {
    if (diffRate <= 0) return totalWeight;  // 无差异，满分
    const baseDeduct = totalWeight * 0.5;  // 有差异扣50%基准
    const diffDeductRate = getDiffDeductRate(diffRate);
    const diffDeduct = totalWeight * 0.5 * diffDeductRate;  // 剩余50%按档位扣
    return Math.max(0, totalWeight - baseDeduct - diffDeduct);
}

function updateHealthIndicators() {
    const issues = [];

    // 四大项权重
    const weights = {
        dataIntegrity: 30,   // 数据完整性 30%
        packComplete: 25,    // 打包完成度 25%
        erpConsist: 25,      // ERP一致性 25%
        huluConsist: 20      // HULU一致性 20%
    };

    // 更新未入单数量
    document.getElementById('missingCount').textContent = missingProductsData.length;
    // 更新未打包数量
    document.getElementById('unpackedCount').textContent = unpackedProductsData.length;

    // 获取基础数据
    const totalProducts = parseInt(document.getElementById('totalCount')?.textContent) || 0;
    const finishedProducts = parseInt(document.getElementById('completedCount')?.textContent) || 0;

    // 各项得分（百分比贡献）
    let dataIntegrityScore = weights.dataIntegrity;
    let packCompleteScore = weights.packComplete;
    let erpConsistScore = weights.erpConsist;
    let huluConsistScore = weights.huluConsist;
    let huluAvailable = true;

    // === 1. 数据完整性（30%）===
    // 差异占比 = 未入单数 / 工单总数量
    if (totalProducts > 0 && missingProductsData.length > 0) {
        const diffRate = missingProductsData.length / totalProducts;
        dataIntegrityScore = calcItemScore(weights.dataIntegrity, diffRate);
        issues.push({
            text: `${missingProductsData.length}个未入单(${(diffRate*100).toFixed(1)}%)`,
            level: diffRate > 0.10 ? 'error' : 'warn'
        });
    }

    // === 2. 打包完成度（25%）===
    // 差异占比 = 未打包数 / 已完工数
    if (finishedProducts > 0 && unpackedProductsData.length > 0) {
        const diffRate = unpackedProductsData.length / finishedProducts;
        packCompleteScore = calcItemScore(weights.packComplete, diffRate);
        issues.push({
            text: `${unpackedProductsData.length}个未打包(${(diffRate*100).toFixed(1)}%)`,
            level: diffRate > 0.10 ? 'error' : 'warn'
        });
    }

    // === 3. ERP一致性（25%）===
    // 五个子维度：批次数、批次号、总数量、批次数量、重复报工
    const erpDiffText = document.getElementById('diffTotalSum')?.textContent || '-';
    const compareStatusEl = document.getElementById('compareStatus');
    if (erpDiffText !== '-' && erpDiffText !== '...') {
        const statusText = compareStatusEl?.textContent || '';
        const mismatchMatch = statusText.match(/(\d+)批不匹配/);
        const mismatchCount = mismatchMatch ? parseInt(mismatchMatch[1]) : 0;
        // 解析重复报工数量
        const duplicateMatch = statusText.match(/(\d+)批重复报工/);
        const duplicateCount = duplicateMatch ? parseInt(duplicateMatch[1]) : 0;
        const diffMatch = erpDiffText.match(/-?\d+/);
        const absDiff = diffMatch ? Math.abs(parseInt(diffMatch[0])) : 0;
        const accTotal = parseInt(document.getElementById('accTotalSum')?.textContent) || 1;
        const accBatchCount = parseInt(document.getElementById('packCount')?.textContent) || 1;
        const erpBatchCount = parseInt(document.getElementById('erpBatchCount')?.textContent) || accBatchCount;

        if (mismatchCount > 0 || absDiff > 0 || duplicateCount > 0) {
            // 计算五个子维度的差异占比
            const batchCountDiff = Math.abs(accBatchCount - erpBatchCount) / accBatchCount;  // 批次数差异
            const batchIdDiff = mismatchCount / accBatchCount;  // 批次号差异（用不匹配数近似）
            const totalQtyDiff = absDiff / accTotal;  // 总数量差异
            const batchQtyDiff = absDiff / accTotal;  // 批次数量差异（用总差异近似）
            const duplicateDiff = duplicateCount / accBatchCount;  // 重复报工差异

            // 综合差异占比 = 五项加权平均
            const erpDiffRate = (batchCountDiff + batchIdDiff + totalQtyDiff + batchQtyDiff + duplicateDiff) / 5;
            erpConsistScore = calcItemScore(weights.erpConsist, erpDiffRate);

            // 构建问题描述
            let issueText = '';
            const issueParts = [];
            if (absDiff > 0) issueParts.push(`${absDiff}个差异`);
            if (mismatchCount > 0) issueParts.push(`${mismatchCount}批不匹配`);
            if (duplicateCount > 0) issueParts.push(`${duplicateCount}批重复`);
            issueText = `ERP: ${issueParts.join('/')}(${(erpDiffRate*100).toFixed(1)}%)`;

            issues.push({
                text: issueText,
                level: erpDiffRate > 0.10 ? 'error' : 'warn'
            });
        }
    }

    // === 4. HULU一致性（20%）===
    // 三个子维度：完工数量50%、在制数量30%、状态一致20%
    if (huluDataCache) {
        const huluFinished = huluDataCache.production?.finished || 0;
        const huluWip = huluDataCache.production?.in_progress || 0;
        const huluStatus = huluDataCache.order_info?.status || '';
        const accFinished = finishedProducts;
        const accWip = parseInt(document.getElementById('incompleteCount')?.textContent) || 0;
        const accCompletionRate = parseInt(document.getElementById('completionRate')?.textContent) || 0;

        // 计算各子维度差异占比
        const finishedDiff = accFinished > 0 ? Math.abs(accFinished - huluFinished) / accFinished : 0;
        const wipDiff = totalProducts > 0 ? Math.abs(accWip - huluWip) / totalProducts : 0;

        // 综合差异占比 = 数量差异的平均值（去掉状态差异检查，只检查数量）
        // 修改说明：数量一致就应该满分，不再检查状态是否匹配
        const huluDiffRate = (finishedDiff + wipDiff) / 2;

        if (huluDiffRate > 0) {
            huluConsistScore = calcItemScore(weights.huluConsist, huluDiffRate);
            const finishedDiffNum = Math.abs(accFinished - huluFinished);
            const wipDiffNum = Math.abs(accWip - huluWip);
            issues.push({
                text: `HULU差异${finishedDiffNum + wipDiffNum}个(${(huluDiffRate*100).toFixed(1)}%)`,
                level: huluDiffRate > 0.10 ? 'error' : 'warn'
            });
        }
    } else {
        // HULU未查询时，该项不计入，重新分配权重
        huluAvailable = false;
        const totalOther = weights.dataIntegrity + weights.packComplete + weights.erpConsist;
        dataIntegrityScore = dataIntegrityScore / totalOther * 100 * weights.dataIntegrity / 100;
        packCompleteScore = packCompleteScore / totalOther * 100 * weights.packComplete / 100;
        erpConsistScore = erpConsistScore / totalOther * 100 * weights.erpConsist / 100;
        huluConsistScore = 0;
    }

    // === 计算综合健康率 ===
    let healthRate;
    if (huluAvailable) {
        healthRate = dataIntegrityScore + packCompleteScore + erpConsistScore + huluConsistScore;
    } else {
        // HULU不可用时，按比例重算
        const totalOther = weights.dataIntegrity + weights.packComplete + weights.erpConsist;
        healthRate = (dataIntegrityScore + packCompleteScore + erpConsistScore) / totalOther * 100;
    }
    healthRate = Math.round(healthRate);

    const rateEl = document.getElementById('healthRateValue');
    const section = document.getElementById('healthSection');

    // 判断是否有有效数据
    const hasData = totalProducts > 0 || finishedProducts > 0;

    rateEl.textContent = hasData ? healthRate + '%' : '-';
    section.className = 'health-section h-100';
    rateEl.className = 'health-rate-value';

    if (!hasData) {
        rateEl.className += ' text-muted';
    } else if (healthRate >= 95) {
        section.classList.add('status-excellent');
        rateEl.classList.add('excellent');
    } else if (healthRate >= 85) {
        section.classList.add('status-good');
        rateEl.classList.add('good');
    } else if (healthRate >= 70) {
        section.classList.add('status-warn');
        rateEl.classList.add('warn');
    } else {
        section.classList.add('status-error');
        rateEl.classList.add('error');
    }

    // 更新问题列表
    const issuesEl = document.getElementById('healthIssues');
    if (issues.length === 0 && hasData) {
        issuesEl.innerHTML = '<div class="health-issue-item issue-ok"><i class="bi bi-check-circle-fill"></i> 工单状态良好</div>';
    } else if (issues.length > 0) {
        issuesEl.innerHTML = issues.map(issue =>
            `<div class="health-issue-item issue-${issue.level}"><i class="bi bi-exclamation-circle-fill"></i> ${issue.text}</div>`
        ).join('');
    } else {
        issuesEl.innerHTML = '<div class="health-issue-item text-muted"><i class="bi bi-clock"></i> 等待检测</div>';
    }
}

// 重置健康指标
function resetHealthIndicators() {
    document.getElementById('missingCount').textContent = '-';
    document.getElementById('unpackedCount').textContent = '-';
    document.getElementById('healthRateValue').textContent = '-';
    document.getElementById('healthRateValue').className = 'health-rate-value text-muted';
    document.getElementById('healthSection').className = 'health-section h-100';
    document.getElementById('healthIssues').innerHTML = '<div class="health-issue-item text-muted"><i class="bi bi-clock"></i> 等待检测</div>';
    // 重置其它工单指示器
    const indicator = document.getElementById('otherWoIndicator');
    if (indicator) {
        indicator.style.display = 'none';
    }
}

// ============================================
//   其它工单产品指示器
// ============================================

// 检测其它工单产品（包装数量 > ACC数量时）
// 修改：使用CustomTip浅紫色样式（与主页面一致）
function updateOtherWoIndicator(packData) {
    const indicator = document.getElementById('otherWoIndicator');
    if (!indicator) return;

    // 找出包含混装的批次（info_qty > actual_qty表示有其它工单产品）
    const mixedBatches = packData.filter(p => {
        const infoQty = p.info_qty || 0;
        const actualQty = p.actual_qty || 0;
        return infoQty > actualQty;
    });

    if (mixedBatches.length === 0) {
        indicator.style.display = 'none';
        return;
    }

    // 构建提示内容 - 使用CustomTip样式
    let tipContent = '';
    mixedBatches.forEach((p, index) => {
        if (index > 0) tipContent += '<div style="border-top:1px dashed #c5cae9;margin:8px 0;"></div>';
        tipContent += `<div style="font-weight:600;color:#5c6bc0;">批次: ${p.packid}</div>`;

        const mixedDetail = p.mixed_detail || [];
        const otherWonos = p.other_wonos || [];

        if (mixedDetail.length > 0) {
            const totalQty = mixedDetail.reduce((sum, wo) => sum + (wo.qty || 0), 0);
            tipContent += `<div style="color:#666;">包装总数: ${totalQty}<span style="color:#999;font-size:0.9em;margin-left:2px;">Pcs</span></div>`;
            tipContent += `<div style="color:#ff9800;">包含${mixedDetail.length}张工单:</div>`;
            mixedDetail.forEach(wo => {
                tipContent += `<div style="padding-left:8px;">- ${wo.wono}: ${wo.qty}<span style="color:#999;font-size:0.9em;margin-left:2px;">Pcs</span></div>`;
            });
        } else if (otherWonos.length > 0) {
            const totalQty = (p.actual_qty || 0) + otherWonos.reduce((sum, wo) => sum + (wo.qty || 0), 0);
            tipContent += `<div style="color:#666;">包装总数: ${totalQty}<span style="color:#999;font-size:0.9em;margin-left:2px;">Pcs</span></div>`;
            tipContent += `<div style="color:#ff9800;">包含${otherWonos.length + 1}张工单:</div>`;
            tipContent += `<div style="padding-left:8px;">- 当前工单: ${p.actual_qty}<span style="color:#999;font-size:0.9em;margin-left:2px;">Pcs</span></div>`;
            otherWonos.forEach(wo => {
                tipContent += `<div style="padding-left:8px;">- ${wo.wono}: ${wo.qty}<span style="color:#999;font-size:0.9em;margin-left:2px;">Pcs</span></div>`;
            });
        } else {
            const totalQty = p.info_qty || 0;
            const otherQty = totalQty - (p.actual_qty || 0);
            tipContent += `<div style="color:#666;">包装总数: ${totalQty}<span style="color:#999;font-size:0.9em;margin-left:2px;">Pcs</span></div>`;
            tipContent += `<div style="padding-left:8px;">其它工单产品: ${otherQty}<span style="color:#999;font-size:0.9em;margin-left:2px;">Pcs</span></div>`;
        }
    });

    // 存储提示数据
    mainPageTipData.title = `混装批次 (${mixedBatches.length}个)`;
    mainPageTipData.content = tipContent;

    // 显示指示器并绑定自定义提示框事件
    indicator.style.display = 'inline';
    bindMainPageTip(indicator);
}

// 绑定主页面提示框事件（优化版：避免重复克隆元素）
function bindMainPageTip(element) {
    // 检查是否已绑定，避免重复绑定
    if (element._mainTipBound) return;

    // 移除旧的事件监听器
    const oldEnter = element._mainEnterHandler;
    const oldLeave = element._mainLeaveHandler;
    if (oldEnter) element.removeEventListener('mouseenter', oldEnter);
    if (oldLeave) element.removeEventListener('mouseleave', oldLeave);

    // 移除title属性防止浏览器原生tooltip（只需执行一次）
    element.removeAttribute('title');
    element.removeAttribute('data-bs-toggle');
    element.removeAttribute('data-bs-original-title');
    element.querySelectorAll('[title]').forEach(el => el.removeAttribute('title'));
    element.querySelectorAll('[data-bs-toggle]').forEach(el => {
        el.removeAttribute('data-bs-toggle');
        el.removeAttribute('data-bs-original-title');
    });

    // 销毁可能存在的Bootstrap tooltip
    try {
        const existingTooltip = bootstrap.Tooltip.getInstance(element);
        if (existingTooltip) existingTooltip.dispose();
    } catch(e) {}

    // 创建新的事件处理函数
    const enterHandler = (e) => {
        e.preventDefault();
        e.stopPropagation();
        CustomTip.show(element, mainPageTipData.title, mainPageTipData.content);
    };

    const leaveHandler = () => {
        CustomTip.scheduleHide();
    };

    // 绑定事件
    element.addEventListener('mouseenter', enterHandler);
    element.addEventListener('mouseleave', leaveHandler);

    // 保存引用以便后续移除
    element._mainEnterHandler = enterHandler;
    element._mainLeaveHandler = leaveHandler;
    element._mainTipBound = true;
}
