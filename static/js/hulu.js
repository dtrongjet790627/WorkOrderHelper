/**
 * hulu.js - HULU工单功能模块
 * 设计：程远 | 2026-01-18
 * 包含：HULU数据查询、渲染、差异检查、同步功能
 * 加载动画：林曦 | 2026-01-23 - 进度条动画
 */

// ============================================
//   HULU加载动画生成函数
// ============================================

// 生成HULU进度条加载动画
function generateHuluProgressLoading(text) {
    return `<div class="hulu-progress-loading">
        <div class="hulu-progress-bar">
            <div class="hulu-progress-fill"></div>
        </div>
        <div class="hulu-progress-text">
            <i class="bi bi-arrow-repeat"></i>
            <span>正在加载${text}...</span>
        </div>
    </div>`;
}

// 生成HULU数据块加载动画（用于表格内）
function generateHuluBlockLoading() {
    return `<tr><td colspan="2" class="text-center py-3">
        <div class="hulu-block-loading">
            <div class="hulu-block-dot"></div>
            <div class="hulu-block-dot"></div>
            <div class="hulu-block-dot"></div>
            <div class="hulu-block-dot"></div>
        </div>
        <div class="text-muted small mt-2">数据同步中</div>
    </td></tr>`;
}

// ============================================
//   HULU工单变量
// ============================================
let huluDataCache = null;
let huluDataLoaded = false;  // 标记HULU数据是否已加载过（用于避免页面切换时重复刷新）

// ERP详情页面加载标记
let erpDetailLoaded = false;  // 标记ERP详情数据是否已加载过（用于避免页面切换时重复刷新）

// HULU列表加载状态
let huluWipLoaded = false;       // 在制列表是否已加载
let huluFinishedLoaded = false;  // 成品列表是否已加载

// ============================================
//   重置函数
// ============================================

// 重置HULU所有数值为初始状态"-"（固定框架布局）
function resetHuluValues() {
    // 工单信息
    document.getElementById('huluWono').textContent = '-';
    document.getElementById('huluType').textContent = '-';
    document.getElementById('huluPlanQty').textContent = '-';
    document.getElementById('huluStatus').textContent = '-';
    document.getElementById('huluStatus').className = 'badge bg-secondary';
    document.getElementById('huluTime').textContent = '-';

    // 产量数据
    document.getElementById('huluFinishedQty').textContent = '-';
    document.getElementById('huluPlannedQty').textContent = '-';
    document.getElementById('huluWipQty').textContent = '-';
    document.getElementById('huluScrappedQty').textContent = '-';

    // 列表数量
    document.getElementById('huluWipCount').textContent = '-';
    document.getElementById('huluFinishedCount').textContent = '-';

    // 隐藏差异图标
    document.getElementById('huluFinishedDiffIcon').style.display = 'none';
    document.getElementById('huluWipDiffIcon').style.display = 'none';

    // 隐藏错误提示
    document.getElementById('huluError').style.display = 'none';
}

// 重置HULU列表状态（切换工单时调用）
function resetHuluListState() {
    huluWipLoaded = false;
    huluFinishedLoaded = false;

    // 清除差异检查相关状态
    if (huluDiffCheckTimer) {
        clearTimeout(huluDiffCheckTimer);
        huluDiffCheckTimer = null;
    }
    huluDiffCheckInProgress = false;

    // 重置UI状态 - 列表始终可见，只更新内容和状态文字
    document.getElementById('huluWipStatus').textContent = '等待数据';
    document.getElementById('huluFinishedStatus').textContent = '等待数据';
    document.getElementById('huluWipBody').innerHTML = `<tr><td colspan="2" class="empty-state-cell">
        <div class="empty-state-container">
            <div class="empty-state-mascot"><i class="bi bi-box-seam"></i></div>
            <div class="empty-state-text">小管家等待中~</div>
            <div class="empty-state-hint">请先查询工单查看完工产品</div>
        </div>
    </td></tr>`;
    document.getElementById('huluFinishedBody').innerHTML = `<tr><td colspan="2" class="empty-state-cell">
        <div class="empty-state-container">
            <div class="empty-state-mascot"><i class="bi bi-hourglass-split"></i></div>
            <div class="empty-state-text">小管家待命中~</div>
            <div class="empty-state-hint">请先查询工单查看在制产品</div>
        </div>
    </td></tr>`;
}

// ============================================
//   HULU数据查询
// ============================================

// 静默获取HULU数据（用于健康率计算，不更新UI状态）
async function fetchHuluDataSilent() {
    if (!currentWono) return;
    try {
        // 只获取汇总数据，不获取列表详情
        const response = await fetch(`/api/hulu_workorder?wono=${encodeURIComponent(currentWono)}&include_details=false`);
        const data = await response.json();
        if (data.success) {
            huluDataCache = data;
            updateHealthIndicators(); // 获取HULU数据后更新健康率
            log('HULU数据已同步用于健康率计算', 'info');
        }
    } catch (error) {
        // 静默失败，不影响主流程
        console.log('HULU数据获取失败（静默）:', error.message);
    }
}

// 查询HULU工单数据（只获取汇总，不加载列表详情）
// 固定框架布局：不改变整体结构，只更新数值
// 优化：分帧渲染，避免阻塞主线程
async function queryHuluData() {
    // 无工单时重置为初始状态（数值显示"-"）
    if (!currentWono) {
        resetHuluValues();
        resetHuluListState();
        return;
    }

    // 重置列表懒加载状态
    resetHuluListState();
    // 隐藏错误提示
    document.getElementById('huluError').style.display = 'none';

    try {
        // 只获取汇总数据，不获取列表详情（懒加载）
        const response = await fetch(`/api/hulu_workorder?wono=${encodeURIComponent(currentWono)}&include_details=false`);
        const data = await response.json();

        if (data.success) {
            huluDataCache = data;

            // 分帧渲染：先渲染汇总数据
            requestAnimationFrame(() => {
                renderHuluSummary(data);
                log('HULU工单汇总已加载', 'success');

                // 延迟加载列表数据，避免阻塞UI
                requestAnimationFrame(() => {
                    loadAndShowHuluLists();
                });
            });
        } else {
            throw new Error(data.message || '获取数据失败');
        }
    } catch (error) {
        // 显示错误提示（不改变整体布局）
        document.getElementById('huluError').style.display = 'block';
        document.getElementById('huluErrorMsg').textContent = error.message;
        log('HULU数据获取失败: ' + error.message, 'error');
    }
}

// ============================================
//   渲染函数
// ============================================

// 渲染HULU汇总数据（固定框架布局：只更新数值，不改变DOM结构）
function renderHuluSummary(data) {
    // 工单信息 - 只更新数值
    const orderInfo = data.order_info || {};
    document.getElementById('huluWono').textContent = orderInfo.work_order || '-';
    document.getElementById('huluType').textContent = orderInfo.type || '-';
    document.getElementById('huluPlanQty').textContent = orderInfo.plan_qty || '-';

    // 状态badge
    const statusEl = document.getElementById('huluStatus');
    statusEl.textContent = orderInfo.status || '-';
    statusEl.className = 'badge ' + (orderInfo.status === '进行中' ? 'bg-success' : 'bg-secondary');

    // 时间
    const startTime = orderInfo.start_time || '-';
    const endTime = orderInfo.end_time || '-';
    document.getElementById('huluTime').textContent = startTime + ' ~ ' + endTime;

    // 当前产量 - 只更新数值
    const production = data.production || {};
    document.getElementById('huluFinishedQty').textContent = production.finished || 0;
    document.getElementById('huluPlannedQty').textContent = production.planned || 0;
    document.getElementById('huluWipQty').textContent = production.in_progress || 0;
    document.getElementById('huluScrappedQty').textContent = production.scrapped || 0;

    // 更新列表数量显示（从汇总数据获取）
    document.getElementById('huluWipCount').textContent = production.in_progress || 0;
    document.getElementById('huluFinishedCount').textContent = production.finished || 0;

    // 异步检查差异并显示图标
    checkHuluDiff();
}

// ============================================
//   列表加载
// ============================================

// 加载并显示HULU列表（固定高度，自动加载数据）
// 优化：串行加载，避免同时触发多个渲染导致卡顿
async function loadAndShowHuluLists() {
    if (!currentWono) {
        log('loadAndShowHuluLists: 无工单号，跳过加载', 'warn');
        return;
    }

    log('loadAndShowHuluLists: 开始加载在制和成品列表', 'info');

    // 显示进度条加载动画
    document.getElementById('huluWipStatus').textContent = '加载中...';
    document.getElementById('huluFinishedStatus').textContent = '加载中...';
    document.getElementById('huluWipLoading').innerHTML = generateHuluProgressLoading('在制列表');
    document.getElementById('huluWipLoading').style.display = 'block';
    document.getElementById('huluFinishedLoading').innerHTML = generateHuluProgressLoading('成品列表');
    document.getElementById('huluFinishedLoading').style.display = 'block';

    // 串行加载：先加载成品列表（左侧），完成后再加载在制列表（右侧）
    // 避免同时触发两个渲染导致UI卡顿
    try {
        // 先加载成品列表（左侧显示）
        await loadHuluListData('finished');
        huluFinishedLoaded = true;
        document.getElementById('huluFinishedLoading').style.display = 'none';

        // 让UI有时间响应
        await new Promise(resolve => requestAnimationFrame(resolve));

        // 再加载在制列表（右侧显示）
        await loadHuluListData('wip');
        huluWipLoaded = true;
        document.getElementById('huluWipLoading').style.display = 'none';

        log('loadAndShowHuluLists: 列表加载完成', 'success');
    } catch (error) {
        log(`loadAndShowHuluLists: 加载失败 - ${error.message}`, 'error');
        // 隐藏加载状态
        document.getElementById('huluFinishedLoading').style.display = 'none';
        document.getElementById('huluWipLoading').style.display = 'none';
    }
}

// 加载HULU列表数据（懒加载）
async function loadHuluListData(type) {
    if (!currentWono) {
        log('loadHuluListData: 无工单号，跳过加载', 'warn');
        return;
    }

    log(`loadHuluListData: 开始加载${type === 'wip' ? '在制' : '成品'}列表`, 'info');
    const response = await fetch(`/api/hulu_workorder?wono=${encodeURIComponent(currentWono)}&list_type=${type}`);
    const data = await response.json();

    if (!data.success) {
        throw new Error(data.message || '获取数据失败');
    }

    if (type === 'wip') {
        const list = data.wip_list || [];
        log(`loadHuluListData: 在制列表获取到${list.length}条数据`, 'info');
        renderHuluWipList(list);
    } else {
        const list = data.finished_list || [];
        log(`loadHuluListData: 成品列表获取到${list.length}条数据`, 'info');
        renderHuluFinishedList(list);
    }
}

// 分批渲染配置
const BATCH_SIZE = 50;  // 每批渲染50条
const BATCH_DELAY = 0;   // 批次间延迟（使用requestAnimationFrame）

// 渲染在制列表（优化版：分批渲染，避免阻塞主线程）
function renderHuluWipList(wipList) {
    document.getElementById('huluWipCount').textContent = wipList.length;
    document.getElementById('huluWipStatus').textContent = `共 ${wipList.length} 条`;

    const tbody = document.getElementById('huluWipBody');

    if (wipList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="2" class="text-center text-muted py-3">暂无在制数据</td></tr>';
        return;
    }

    // 清空表格
    tbody.innerHTML = '';

    // 数据量小于阈值时直接渲染（使用纯DOM API）
    if (wipList.length <= BATCH_SIZE) {
        const fragment = document.createDocumentFragment();
        for (let i = 0; i < wipList.length; i++) {
            const item = wipList[i];
            const tr = document.createElement('tr');
            const td1 = document.createElement('td');
            td1.textContent = item.barcode || '-';
            const td2 = document.createElement('td');
            td2.textContent = item.station || '-';
            tr.appendChild(td1);
            tr.appendChild(td2);
            fragment.appendChild(tr);
        }
        tbody.appendChild(fragment);
        return;
    }

    // 分批渲染大数据量
    renderListInBatches(wipList, tbody);
}

// 渲染成品列表（优化版：分批渲染，避免阻塞主线程）
function renderHuluFinishedList(finishedList) {
    document.getElementById('huluFinishedCount').textContent = finishedList.length;
    document.getElementById('huluFinishedStatus').textContent = `共 ${finishedList.length} 条`;

    const tbody = document.getElementById('huluFinishedBody');

    if (finishedList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="2" class="text-center text-muted py-3">暂无成品数据</td></tr>';
        return;
    }

    // 清空表格
    tbody.innerHTML = '';

    // 数据量小于阈值时直接渲染（使用纯DOM API）
    if (finishedList.length <= BATCH_SIZE) {
        const fragment = document.createDocumentFragment();
        for (let i = 0; i < finishedList.length; i++) {
            const item = finishedList[i];
            const tr = document.createElement('tr');
            const td1 = document.createElement('td');
            td1.textContent = item.barcode || '-';
            const td2 = document.createElement('td');
            td2.textContent = item.station || '-';
            tr.appendChild(td1);
            tr.appendChild(td2);
            fragment.appendChild(tr);
        }
        tbody.appendChild(fragment);
        return;
    }

    // 分批渲染大数据量
    renderListInBatches(finishedList, tbody);
}

// 分批渲染列表数据（通用函数）
// 优化：使用纯DOM API创建元素，避免innerHTML解析开销
function renderListInBatches(list, tbody) {
    let currentIndex = 0;

    function renderBatch() {
        const fragment = document.createDocumentFragment();
        const endIndex = Math.min(currentIndex + BATCH_SIZE, list.length);

        for (let i = currentIndex; i < endIndex; i++) {
            const item = list[i];
            const tr = document.createElement('tr');

            // 使用纯DOM API创建，避免innerHTML解析
            const td1 = document.createElement('td');
            td1.textContent = item.barcode || '-';

            const td2 = document.createElement('td');
            td2.textContent = item.station || '-';

            tr.appendChild(td1);
            tr.appendChild(td2);
            fragment.appendChild(tr);
        }

        tbody.appendChild(fragment);
        currentIndex = endIndex;

        // 还有数据未渲染，继续下一批
        if (currentIndex < list.length) {
            requestAnimationFrame(renderBatch);
        }
    }

    // 开始第一批渲染
    requestAnimationFrame(renderBatch);
}

// 刷新HULU数据（重置缓存强制重新加载）
function refreshHuluData() {
    // 重置懒加载缓存，强制重新加载
    huluWipLoaded = false;
    huluFinishedLoaded = false;
    queryHuluData();
}

// ============================================
//   差异检查
// ============================================

// 存储HULU差异数据供提示框使用
let huluDiffData = { finished: null, wip: null };

// 差异检查防抖计时器
let huluDiffCheckTimer = null;
let huluDiffCheckInProgress = false;

// 检查HULU差异并显示图标（使用自定义可复制提示框 + 防抖）
async function checkHuluDiff() {
    // 防抖：清除之前的计时器
    if (huluDiffCheckTimer) {
        clearTimeout(huluDiffCheckTimer);
    }

    // 延迟200ms执行，避免频繁调用
    huluDiffCheckTimer = setTimeout(() => {
        _doCheckHuluDiff();
    }, 200);
}

// 实际执行差异检查
async function _doCheckHuluDiff() {
    // 无工单时直接返回
    if (!currentWono) return;

    // 防止并发请求
    if (huluDiffCheckInProgress) return;
    huluDiffCheckInProgress = true;

    try {
        // 并行请求成品和在制差异
        const [finishedRes, wipRes] = await Promise.all([
            fetch(`/api/hulu/diff_products?wono=${encodeURIComponent(currentWono)}&diff_type=finished`),
            fetch(`/api/hulu/diff_products?wono=${encodeURIComponent(currentWono)}&diff_type=wip`)
        ]);

        const finishedData = await finishedRes.json();
        const wipData = await wipRes.json();

        // 存储差异数据
        huluDiffData.finished = finishedData;
        huluDiffData.wip = wipData;

        // 处理成品差异图标
        const finishedIcon = document.getElementById('huluFinishedDiffIcon');
        if (finishedIcon) {
            if (finishedData.success && finishedData.diff_count > 0) {
                finishedIcon.style.display = 'inline';
                // 绑定自定义提示框事件
                bindHuluTip(finishedIcon, 'finished');
            } else {
                finishedIcon.style.display = 'none';
            }
        }

        // 处理在制差异图标
        const wipIcon = document.getElementById('huluWipDiffIcon');
        if (wipIcon) {
            if (wipData.success && wipData.diff_count > 0) {
                wipIcon.style.display = 'inline';
                // 绑定自定义提示框事件
                bindHuluTip(wipIcon, 'wip');
            } else {
                wipIcon.style.display = 'none';
            }
        }

    } catch (error) {
        console.log('差异检查失败:', error.message);
    } finally {
        // 重置进行中标志
        huluDiffCheckInProgress = false;
    }
}

// 绑定HULU差异提示框（优化版：避免重复克隆元素）
function bindHuluTip(element, type) {
    // 检查是否已绑定，避免重复绑定
    if (element._huluTipBound === type) return;

    // 移除旧的事件监听器
    const oldEnter = element._huluEnterHandler;
    const oldLeave = element._huluLeaveHandler;
    if (oldEnter) element.removeEventListener('mouseenter', oldEnter);
    if (oldLeave) element.removeEventListener('mouseleave', oldLeave);

    // 创建新的事件处理函数
    const enterHandler = () => {
        const data = type === 'finished' ? huluDiffData.finished : huluDiffData.wip;
        if (!data || !data.diff_products) return;

        const diffProducts = data.diff_products;
        const displayCount = Math.min(diffProducts.length, 10);
        const title = type === 'finished'
            ? `ACC有但HULU无的成品 (${data.diff_count}<span style="color:#999;font-size:0.9em;margin-left:2px;">Pcs</span>)`
            : `ACC有但HULU无的在制品 (${data.diff_count}<span style="color:#999;font-size:0.9em;margin-left:2px;">Pcs</span>)`;

        let content = diffProducts.slice(0, displayCount).map(sn => `- ${sn}`).join('<br>');
        if (diffProducts.length > displayCount) {
            content += `<br><span style="color:#888;font-style:italic;">...还有${diffProducts.length - displayCount}<span style="color:#aaa;font-size:0.9em;margin-left:2px;">Pcs</span></span>`;
        }

        CustomTip.show(element, title, content);
    };

    const leaveHandler = () => {
        CustomTip.scheduleHide();
    };

    // 绑定事件
    element.addEventListener('mouseenter', enterHandler);
    element.addEventListener('mouseleave', leaveHandler);

    // 保存引用以便后续移除
    element._huluEnterHandler = enterHandler;
    element._huluLeaveHandler = leaveHandler;
    element._huluTipBound = type;
}

// ============================================
//   同步功能
// ============================================

// 同步ACC成品到HULU（只同步成品，不同步在制品）
async function syncToHulu() {
    if (!currentWono) {
        alert('请先查询工单');
        return;
    }

    // 前置权限检查
    if (typeof checkOperationPermission === 'function' && !checkOperationPermission('同步HULU')) {
        return;
    }

    const btn = document.getElementById('syncHuluBtn');
    const originalText = btn.innerHTML;

    // 确认操作
    if (!confirm(`确定将工单 ${currentWono} 的ACC成品同步到HULU吗？\n\n注意：只会同步已完工的产品，在制品不会同步。`)) {
        return;
    }

    try {
        // 显示加载状态
        btn.disabled = true;
        btn.innerHTML = '<i class="bi bi-hourglass-split"></i> 同步中...';

        const response = await fetch('/api/sync_to_hulu', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                wono: currentWono,
                operator_id: typeof getOperatorId === 'function' ? getOperatorId() : ''
            })
        });

        const data = await response.json();

        if (data.success) {
            const synced = data.synced || {};
            let msg = `同步成功（仅同步成品）\n\n`;
            msg += `ACC成品数: ${synced.acc_finished || 0}\n`;
            msg += `更新状态: ${synced.updated || 0}个\n`;
            msg += `新增产品: ${synced.inserted || 0}个\n`;
            msg += `---\n`;
            msg += `HULU成品: ${synced.hulu_finished || 0}\n`;
            msg += `HULU在制: ${synced.hulu_wip || 0}`;
            alert(msg);
            log(`ACC→HULU同步成功: 更新${synced.updated}个, 新增${synced.inserted}个`, 'success');
            // 刷新HULU数据显示
            queryHuluData();
        } else {
            // 处理权限错误
            if (data.permission_error) {
                alert(`无操作权限: ${data.reason}`);
                log(`HULU同步被拒绝: ${data.reason}`, 'error');
            } else {
                alert('同步失败: ' + (data.message || '未知错误'));
                log('ACC→HULU同步失败: ' + data.message, 'error');
            }
        }
    } catch (error) {
        alert('同步出错: ' + error.message);
        log('ACC→HULU同步出错: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}
