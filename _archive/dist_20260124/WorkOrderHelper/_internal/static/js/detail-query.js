/**
 * detail-query.js - 明细查询模块
 * 设计：程远 | 2026-01-21
 * 包含：包装列表、单品查询、包装明细、导出功能
 * 加载动画：林曦 | 2026-01-23 - 搜索雷达动画
 */

// ============================================
//   明细查询加载动画生成函数
// ============================================

// 生成搜索雷达加载动画
function generateSearchRadarLoading(text) {
    return `<div class="search-loading">
        <div class="search-radar">
            <div class="search-radar-ring"></div>
            <div class="search-radar-ring"></div>
            <div class="search-radar-ring"></div>
            <div class="search-radar-center"></div>
        </div>
        <div class="search-loading-text">
            ${text}
            <span class="search-loading-dots">
                <span></span>
                <span></span>
                <span></span>
            </span>
        </div>
    </div>`;
}

// 生成搜索图标跳动加载动画
function generateSearchIconLoading(text) {
    return `<div class="search-loading">
        <div class="search-loading-icon">
            <i class="bi bi-search"></i>
        </div>
        <div class="search-loading-text">
            ${text}
            <span class="search-loading-dots">
                <span></span>
                <span></span>
                <span></span>
            </span>
        </div>
    </div>`;
}

// ============================================
//   明细查询全局变量
// ============================================
let detailQueryPackList = [];  // 包装列表数据缓存
let detailQueryCurrentPack = null;  // 当前选中的批次
let detailQueryLoaded = false;  // 数据是否已加载
let detailQueryLastWono = '';  // 上次加载的工单号

// 完工明细滚动加载相关变量
let finishedProductsData = [];  // 完工明细全量数据缓存
let finishedProductsPageSize = 100;  // 每次加载数量
let finishedProductsLoadedCount = 0;  // 已加载数量
let finishedProductsLoading = false;  // 是否正在加载
let finishedScrollHandler = null;  // 滚动事件处理器引用

// ============================================
//   初始化明细查询视图
// ============================================
function initDetailQuery() {
    // Tab切换事件绑定
    const tabBtns = document.querySelectorAll('#detailQueryTabs .nav-link');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const targetTab = btn.dataset.tab;
            switchDetailTab(targetTab);
        });
    });

    // SN输入框回车事件
    const snInput = document.getElementById('detailUnitSnInput');
    if (snInput) {
        snInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                queryUnitTrace();
            }
        });
    }

    // 表格行点击高亮 - 使用事件委托
    initTableRowHighlight();
}

// ============================================
//   表格行点击高亮功能
// ============================================
function initTableRowHighlight() {
    // 需要添加点击高亮的表格ID列表
    const tableIds = [
        'detailUnitHistoryBody',
        'detailPackProductsBody',
        'detailFinishedProductsBody',
        'detailWipProductsBody'
    ];

    tableIds.forEach(tableId => {
        const tbody = document.getElementById(tableId);
        if (tbody) {
            tbody.addEventListener('click', (e) => {
                // 找到被点击的行
                const row = e.target.closest('tr');
                if (!row || row.querySelector('td[colspan]')) {
                    // 忽略空状态行（带有colspan的行）
                    return;
                }

                // 如果点击的是链接，不处理高亮（让链接正常跳转）
                if (e.target.classList.contains('sn-link') || e.target.closest('.sn-link')) {
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
            });
        }
    });
}

// ============================================
//   Tab切换（仅切换显示，不自动加载数据）
// ============================================
function switchDetailTab(tabName) {
    // 更新Tab按钮状态
    document.querySelectorAll('#detailQueryTabs .nav-link').forEach(btn => {
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // 切换Tab内容
    document.querySelectorAll('.detail-tab-pane').forEach(pane => {
        if (pane.id === 'detail-tab-' + tabName) {
            pane.classList.add('active');
        } else {
            pane.classList.remove('active');
        }
    });

    // 切换到完工明细时，重新绑定滚动事件（因为元素可能在隐藏时无法正确绑定）
    if (tabName === 'finished-products' && finishedProductsData.length > 0) {
        setTimeout(() => {
            setupFinishedScrollListener();
        }, 100);
    }
}

// ============================================
//   加载包装列表
// ============================================
async function loadDetailPackList() {
    if (!currentWono) {
        return;
    }

    // 如果工单号未变化且已加载，则不重复加载
    if (detailQueryLoaded && detailQueryLastWono === currentWono) {
        return;
    }

    const listBody = document.getElementById('detailPackListBody');
    listBody.innerHTML = generateSearchRadarLoading('搜索包装列表');

    try {
        const response = await fetch(`/api/detail/pack_list?wono=${encodeURIComponent(currentWono)}`);
        const data = await response.json();

        if (data.error) {
            listBody.innerHTML = `<div class="text-center py-3 text-danger"><i class="bi bi-exclamation-circle"></i> ${data.error}</div>`;
            return;
        }

        detailQueryPackList = data.packs || [];
        renderDetailPackList();
        detailQueryLoaded = true;
        detailQueryLastWono = currentWono;  // 记录当前加载的工单号

        // 更新工单信息显示
        document.getElementById('detailWonoLabel').textContent = currentWono;

    } catch (e) {
        listBody.innerHTML = `<div class="text-center py-3 text-danger"><i class="bi bi-exclamation-circle"></i> 加载失败: ${e.message}</div>`;
    }
}

// ============================================
//   渲染包装列表
// ============================================
function renderDetailPackList() {
    const listBody = document.getElementById('detailPackListBody');

    if (detailQueryPackList.length === 0) {
        listBody.innerHTML = '<div class="text-center py-3 text-muted"><i class="bi bi-inbox"></i> 暂无包装数据</div>';
        return;
    }

    let html = '';
    detailQueryPackList.forEach((pack, idx) => {
        const statusClass = getPackStatusClass(pack.status);
        const isActive = detailQueryCurrentPack && detailQueryCurrentPack.packid === pack.packid ? 'active' : '';

        html += `
            <div class="detail-pack-item ${isActive}" data-packid="${pack.packid}" onclick="selectDetailPack('${pack.packid}')">
                <div class="d-flex justify-content-between align-items-center">
                    <div class="pack-id text-truncate" title="${pack.packid}">${pack.packid}</div>
                    <span class="badge ${statusClass}">${pack.status}</span>
                </div>
                <div class="pack-meta">
                    <span><i class="bi bi-box"></i> ${pack.quantity || 0}</span>
                    ${pack.schb_number ? `<span class="text-success" title="已报工"><i class="bi bi-check-circle"></i></span>` : ''}
                </div>
            </div>
        `;
    });

    listBody.innerHTML = html;

    // 更新统计
    document.getElementById('detailPackCount').textContent = detailQueryPackList.length;
}

// ============================================
//   获取状态样式类
// ============================================
function getPackStatusClass(status) {
    switch (status) {
        case '已报工':
            return 'bg-success';
        case '已封包':
            return 'bg-primary';
        case '打包中':
            return 'bg-warning text-dark';
        default:
            return 'bg-secondary';
    }
}

// ============================================
//   选择批次
// ============================================
function selectDetailPack(packid) {
    // 更新选中状态
    document.querySelectorAll('.detail-pack-item').forEach(item => {
        if (item.dataset.packid === packid) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // 缓存当前选中的批次
    detailQueryCurrentPack = detailQueryPackList.find(p => p.packid === packid);

    // 切换到包装明细Tab并加载数据
    switchDetailTab('pack-detail');
    loadPackDetail(packid);
}

// ============================================
//   加载包装明细
// ============================================
async function loadPackDetail(packid) {
    const infoContainer = document.getElementById('detailPackInfo');
    const tableBody = document.getElementById('detailPackProductsBody');

    // 显示搜索图标加载动画
    infoContainer.innerHTML = generateSearchIconLoading('加载批次信息');
    tableBody.innerHTML = `<tr><td colspan="4">${generateSearchRadarLoading('查询产品列表')}</td></tr>`;

    try {
        const line = currentWorkorderLine || '';
        const response = await fetch(`/api/detail/pack_detail?packid=${encodeURIComponent(packid)}&line=${encodeURIComponent(line)}`);
        const data = await response.json();

        if (data.error) {
            infoContainer.innerHTML = `<div class="text-danger"><i class="bi bi-exclamation-circle"></i> ${data.error}</div>`;
            tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-danger"><i class="bi bi-exclamation-circle"></i> ${data.error}</td></tr>`;
            return;
        }

        // 渲染批次信息卡片
        const info = data.pack_info;
        const statusClass = getPackStatusClass(info.status);
        infoContainer.innerHTML = `
            <div class="row g-2">
                <div class="col-6">
                    <div class="detail-info-item">
                        <span class="label">批次号:</span>
                        <strong>${info.packid}</strong>
                    </div>
                </div>
                <div class="col-3">
                    <div class="detail-info-item">
                        <span class="label">数量:</span>
                        <strong>${info.currquantity || 0}</strong>
                    </div>
                </div>
                <div class="col-3">
                    <div class="detail-info-item">
                        <span class="label">状态:</span>
                        <span class="badge ${statusClass}">${info.status}</span>
                    </div>
                </div>
                <div class="col-6">
                    <div class="detail-info-item">
                        <span class="label">封包时间:</span>
                        <span>${info.lastupdate || '-'}</span>
                    </div>
                </div>
                <div class="col-6">
                    <div class="detail-info-item">
                        <span class="label">报工单号:</span>
                        <span>${info.schb_number || '-'}</span>
                    </div>
                </div>
            </div>
        `;

        // 渲染产品列表
        const products = data.products || [];
        if (products.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="4" class="text-center py-3 text-muted">暂无产品数据</td></tr>';
        } else {
            let html = '';
            products.forEach(p => {
                html += `
                    <tr>
                        <td class="text-center">${p.seq}</td>
                        <td>
                            <code class="sn-link" onclick="jumpToUnitTrace('${p.unitsn}')">${p.unitsn}</code>
                        </td>
                        <td class="text-center"><small>${p.packdate || '-'}</small></td>
                        <td class="text-center"><small>${p.stn || '-'}</small></td>
                    </tr>
                `;
            });
            tableBody.innerHTML = html;
        }

        // 更新产品数量显示
        document.getElementById('detailPackProductCount').textContent = products.length;

    } catch (e) {
        infoContainer.innerHTML = `<div class="text-danger"><i class="bi bi-exclamation-circle"></i> 加载失败: ${e.message}</div>`;
        tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-danger"><i class="bi bi-exclamation-circle"></i> 加载失败: ${e.message}</td></tr>`;
    }
}

// ============================================
//   单品追溯查询
// ============================================
async function queryUnitTrace() {
    const snInput = document.getElementById('detailUnitSnInput');
    const unitsn = snInput.value.trim();

    if (!unitsn) {
        alert('请输入产品序列号');
        snInput.focus();
        return;
    }

    const infoContainer = document.getElementById('detailUnitInfo');
    const tableBody = document.getElementById('detailUnitHistoryBody');

    // 显示搜索雷达加载动画
    infoContainer.innerHTML = generateSearchRadarLoading('追溯产品信息');
    tableBody.innerHTML = `<tr><td colspan="5">${generateSearchIconLoading('查询过站履历')}</td></tr>`;

    try {
        const line = currentWorkorderLine || '';
        const response = await fetch(`/api/detail/unit_trace?unitsn=${encodeURIComponent(unitsn)}&line=${encodeURIComponent(line)}`);
        const data = await response.json();

        if (data.error) {
            infoContainer.innerHTML = `<div class="alert alert-danger mb-0">${data.error}</div>`;
            tableBody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">${data.error}</td></tr>`;
            return;
        }

        // 渲染产品信息卡片
        const info = data.unit_info;
        const statusBadge = info.status === 'FG'
            ? '<span class="badge bg-success">FG</span>'
            : (info.status === 'WIP' ? '<span class="badge bg-warning text-dark">WIP</span>' : '<span class="badge bg-secondary">-</span>');

        infoContainer.innerHTML = `
            <div class="row g-2">
                <div class="col-md-4">
                    <div class="detail-info-item">
                        <span class="label">产品SN:</span>
                        <strong><code>${info.unitsn}</code></strong>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="detail-info-item">
                        <span class="label">型号:</span>
                        <span>${info.partno || '-'}</span>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="detail-info-item">
                        <span class="label">产线:</span>
                        <span>${info.line || '-'}</span>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="detail-info-item">
                        <span class="label">状态:</span>
                        ${statusBadge}
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="detail-info-item">
                        <span class="label">当前工位:</span>
                        <span>${info.current_op || '-'}</span>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="detail-info-item">
                        <span class="label">工单:</span>
                        <span>${info.wono || '-'}</span>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="detail-info-item">
                        <span class="label">所属批次:</span>
                        ${info.packid ? `<a href="javascript:void(0)" onclick="selectDetailPack('${info.packid}')">${info.packid}</a>` : '-'}
                    </div>
                </div>
            </div>
        `;

        // 渲染过站履历
        const history = data.history || [];
        if (history.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center py-3 text-muted">暂无过站记录</td></tr>';
        } else {
            let html = '';
            history.forEach(h => {
                let resultBadge;
                if (h.result === 'OK') {
                    resultBadge = '<span class="badge bg-success">OK</span>';
                } else if (h.result === 'NOK') {
                    resultBadge = '<span class="badge bg-danger">NOK</span>';
                } else if (h.result === 'N/A') {
                    resultBadge = '<span class="badge bg-warning text-dark">N/A</span>';
                } else {
                    resultBadge = '<span class="badge bg-secondary">-</span>';
                }

                html += `
                    <tr>
                        <td class="text-center">${h.seq}</td>
                        <td>${h.op}</td>
                        <td class="text-center">${h.start_time || '-'}</td>
                        <td class="text-center">${h.end_time || '-'}</td>
                        <td class="text-center">${resultBadge}</td>
                    </tr>
                `;
            });
            tableBody.innerHTML = html;
        }

        // 更新工位数量显示
        document.getElementById('detailUnitStationCount').textContent = history.length;

    } catch (e) {
        infoContainer.innerHTML = `<div class="alert alert-danger mb-0">查询失败: ${e.message}</div>`;
        tableBody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">查询失败: ${e.message}</td></tr>`;
    }
}

// ============================================
//   跳转到单品查询
// ============================================
function jumpToUnitTrace(unitsn) {
    // 切换到单品查询Tab
    switchDetailTab('unit-trace');

    // 填入SN并查询
    const snInput = document.getElementById('detailUnitSnInput');
    snInput.value = unitsn;
    queryUnitTrace();
}

// ============================================
//   跳转到包装明细
// ============================================
function jumpToPackDetail(packid) {
    // 切换到包装明细Tab并选中该批次
    selectDetailPack(packid);
}

// ============================================
//   导出全部包装
// ============================================
function exportAllPacks() {
    if (!currentWono) {
        alert('请先查询工单');
        return;
    }

    window.location.href = `/api/detail/export_packs?wono=${encodeURIComponent(currentWono)}`;
}

// ============================================
//   导出当前批次明细
// ============================================
function exportPackDetail() {
    if (!detailQueryCurrentPack) {
        alert('请先选择一个批次');
        return;
    }

    const line = currentWorkorderLine || '';
    window.location.href = `/api/detail/export_pack_detail?packid=${encodeURIComponent(detailQueryCurrentPack.packid)}&line=${encodeURIComponent(line)}`;
}

// ============================================
//   加载完工明细
// ============================================
async function loadFinishedProducts() {
    if (!currentWono) {
        return;
    }

    const infoContainer = document.getElementById('detailFinishedInfo');
    const tableBody = document.getElementById('detailFinishedProductsBody');

    // 显示搜索加载动画
    infoContainer.innerHTML = generateSearchIconLoading('统计完工数据');
    tableBody.innerHTML = `<tr><td colspan="4">${generateSearchRadarLoading('加载完工明细')}</td></tr>`;

    try {
        const response = await fetch(`/api/detail/finished_products?wono=${encodeURIComponent(currentWono)}`);
        const data = await response.json();

        if (data.error) {
            infoContainer.innerHTML = `<div class="text-danger"><i class="bi bi-exclamation-circle"></i> ${data.error}</div>`;
            tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-danger"><i class="bi bi-exclamation-circle"></i> ${data.error}</td></tr>`;
            return;
        }

        // 渲染统计卡片
        const summary = data.summary;
        infoContainer.innerHTML = `
            <div class="row g-2">
                <div class="col-4 col-md-2">
                    <div class="detail-info-item">
                        <span class="label">完工总数:</span>
                        <strong class="text-success">${summary.total_count}</strong>
                    </div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="detail-info-item">
                        <span class="label">已打包:</span>
                        <strong class="text-primary">${summary.packed_count}</strong>
                    </div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="detail-info-item">
                        <span class="label">未打包:</span>
                        <strong class="text-warning">${summary.unpacked_count}</strong>
                    </div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="detail-info-item">
                        <span class="label">在制:</span>
                        <strong class="text-info">${summary.wip_count || 0}</strong>
                    </div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="detail-info-item">
                        <span class="label">型号:</span>
                        <span>${summary.partno || '-'}</span>
                    </div>
                </div>
                <div class="col-4 col-md-2">
                    <div class="detail-info-item">
                        <span class="label">末站工位:</span>
                        <span>${summary.last_station || '-'}</span>
                    </div>
                </div>
            </div>
        `;

        // 缓存全量数据，重置加载状态
        finishedProductsData = data.products || [];
        finishedProductsLoadedCount = 0;
        finishedProductsLoading = false;

        // 渲染产品列表（滚动加载）
        renderFinishedProductsPage();

        // 更新数量显示
        document.getElementById('detailFinishedCount').textContent = finishedProductsData.length;

    } catch (e) {
        infoContainer.innerHTML = `<div class="text-danger"><i class="bi bi-exclamation-circle"></i> 加载失败: ${e.message}</div>`;
        tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-danger"><i class="bi bi-exclamation-circle"></i> 加载失败: ${e.message}</td></tr>`;
    }
}

// ============================================
//   渲染完工明细（初始加载）
// ============================================
function renderFinishedProductsPage() {
    const tableBody = document.getElementById('detailFinishedProductsBody');
    const products = finishedProductsData;

    if (products.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="4" class="text-center py-3 text-muted">暂无完工产品</td></tr>';
        updateFinishedLoadStatus();
        return;
    }

    // 重置加载状态
    finishedProductsLoadedCount = 0;
    tableBody.innerHTML = '';

    // 加载第一批数据
    loadMoreFinishedProducts();

    // 绑定滚动事件
    setupFinishedScrollListener();
}

// ============================================
//   加载更多完工明细
// ============================================
function loadMoreFinishedProducts() {
    if (finishedProductsLoading) return;
    if (finishedProductsLoadedCount >= finishedProductsData.length) return;

    finishedProductsLoading = true;
    const tableBody = document.getElementById('detailFinishedProductsBody');
    const products = finishedProductsData;

    const startIndex = finishedProductsLoadedCount;
    const endIndex = Math.min(startIndex + finishedProductsPageSize, products.length);
    const batchProducts = products.slice(startIndex, endIndex);

    // 移除状态行（如果存在）
    const statusRow = document.getElementById('detailFinishedLoadStatus');
    if (statusRow) {
        statusRow.remove();
    }

    // 渲染这批数据
    let html = '';
    batchProducts.forEach(p => {
        const packidCell = p.packid && p.packid !== '-'
            ? `<code class="sn-link" onclick="jumpToPackDetail('${p.packid}')">${p.packid}</code>`
            : '<span class="text-muted">-</span>';

        html += `
            <tr>
                <td class="text-center">${p.seq}</td>
                <td>
                    <code class="sn-link" onclick="jumpToUnitTrace('${p.unitsn}')">${p.unitsn}</code>
                </td>
                <td class="text-center"><small>${p.finish_time}</small></td>
                <td class="text-center">${packidCell}</td>
            </tr>
        `;
    });
    tableBody.insertAdjacentHTML('beforeend', html);

    finishedProductsLoadedCount = endIndex;
    finishedProductsLoading = false;

    // 更新加载状态显示（会重新创建状态行在最后）
    updateFinishedLoadStatus();
}

// ============================================
//   更新完工明细加载状态
// ============================================
function updateFinishedLoadStatus() {
    const tableBody = document.getElementById('detailFinishedProductsBody');
    if (!tableBody) return;

    // 移除旧的状态行
    const oldStatusRow = document.getElementById('detailFinishedLoadStatus');
    if (oldStatusRow) {
        oldStatusRow.remove();
    }

    const total = finishedProductsData.length;
    const loaded = finishedProductsLoadedCount;

    if (total === 0) return;

    // 创建新的状态行
    const statusRow = document.createElement('tr');
    statusRow.id = 'detailFinishedLoadStatus';

    if (loaded >= total) {
        statusRow.innerHTML = `<td colspan="4" class="text-center py-2 small"><span class="text-success"><i class="bi bi-check-circle"></i> 已加载全部 ${total} 条记录</span></td>`;
    } else {
        statusRow.innerHTML = `<td colspan="4" class="text-center py-2 small"><span class="text-primary"><i class="bi bi-arrow-down-circle"></i> 已加载 ${loaded} / ${total} 条，向下滚动加载更多...</span></td>`;
    }

    tableBody.appendChild(statusRow);
}

// ============================================
//   设置完工明细滚动监听
// ============================================
function setupFinishedScrollListener() {
    // 尝试多个可能的滚动容器
    let tableWrapper = document.querySelector('.detail-finished-products-table');

    // 如果没有找到或没有滚动条，尝试父容器
    if (!tableWrapper) {
        tableWrapper = document.getElementById('detail-tab-finished-products');
    }

    if (!tableWrapper) return;

    // 移除旧的监听器
    if (finishedScrollHandler) {
        tableWrapper.removeEventListener('scroll', finishedScrollHandler);
    }

    // 创建新的监听器
    finishedScrollHandler = function() {
        // 当滚动到底部附近时加载更多
        const scrollTop = tableWrapper.scrollTop;
        const scrollHeight = tableWrapper.scrollHeight;
        const clientHeight = tableWrapper.clientHeight;

        // 距离底部100px时触发加载
        if (scrollTop + clientHeight >= scrollHeight - 100) {
            loadMoreFinishedProducts();
        }
    };

    tableWrapper.addEventListener('scroll', finishedScrollHandler);

    // 同时监听表格容器的父元素（以防滚动发生在外层）
    const cardBody = tableWrapper.closest('.card-body');
    if (cardBody && cardBody !== tableWrapper) {
        cardBody.addEventListener('scroll', finishedScrollHandler);
    }
}

// ============================================
//   加载在制明细（优化版：一次查询获取所有数据）
// ============================================
async function loadWipProducts() {
    if (!currentWono) {
        return;
    }

    const infoContainer = document.getElementById('detailWipInfo');
    const tableBody = document.getElementById('detailWipProductsBody');

    // 显示搜索加载动画
    infoContainer.innerHTML = generateSearchIconLoading('统计在制数据');
    tableBody.innerHTML = `<tr><td colspan="7">${generateSearchRadarLoading('加载在制明细')}</td></tr>`;

    try {
        const response = await fetch(`/api/detail/wip_products?wono=${encodeURIComponent(currentWono)}`);
        const data = await response.json();

        if (data.error) {
            infoContainer.innerHTML = `<div class="text-danger"><i class="bi bi-exclamation-circle"></i> ${data.error}</div>`;
            tableBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger"><i class="bi bi-exclamation-circle"></i> ${data.error}</td></tr>`;
            return;
        }

        // 渲染统计卡片
        const summary = data.summary;
        infoContainer.innerHTML = `
            <div class="row g-2">
                <div class="col-12">
                    <div class="detail-info-item">
                        <span class="label">在制总数:</span>
                        <strong class="text-warning">${summary.total_count}</strong>
                    </div>
                </div>
            </div>
        `;

        // 渲染产品列表
        const products = data.products || [];
        if (products.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" class="text-center py-3 text-muted">暂无在制产品</td></tr>';
        } else {
            let html = '';
            products.forEach(p => {
                // 滞留时长超过4小时显示警告颜色
                let durationClass = '';
                if (p.duration && p.duration.includes('天')) {
                    durationClass = 'text-danger fw-bold';
                } else if (p.duration && p.duration.includes('小时')) {
                    const hours = parseInt(p.duration);
                    if (hours >= 4) {
                        durationClass = 'text-warning';
                    }
                }

                // 结果badge样式（与单品查询保持一致）
                let resultBadge = '';
                if (p.result === 'OK') {
                    resultBadge = '<span class="badge bg-success">OK</span>';
                } else if (p.result === 'NOK') {
                    resultBadge = '<span class="badge bg-danger">NOK</span>';
                } else if (p.result === 'N/A') {
                    resultBadge = '<span class="badge bg-warning text-dark">N/A</span>';
                } else {
                    resultBadge = '<span class="badge bg-secondary">-</span>';
                }

                html += `
                    <tr>
                        <td class="text-center">${p.seq}</td>
                        <td>
                            <code class="sn-link" onclick="jumpToUnitTrace('${p.unitsn}')">${p.unitsn}</code>
                        </td>
                        <td class="text-center"><small>${p.current_op}</small></td>
                        <td class="text-center"><small>${p.enter_time}</small></td>
                        <td class="text-center"><small>${p.end_time || '-'}</small></td>
                        <td class="text-center">${resultBadge}</td>
                        <td class="text-center ${durationClass}"><small>${p.duration}</small></td>
                    </tr>
                `;
            });
            tableBody.innerHTML = html;
        }

        // 更新数量显示
        document.getElementById('detailWipCount').textContent = products.length;

    } catch (e) {
        infoContainer.innerHTML = `<div class="text-danger"><i class="bi bi-exclamation-circle"></i> 加载失败: ${e.message}</div>`;
        tableBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger"><i class="bi bi-exclamation-circle"></i> 加载失败: ${e.message}</td></tr>`;
    }
}

// ============================================
//   导出完工明细
// ============================================
function exportFinishedProducts() {
    if (!currentWono) {
        alert('请先查询工单');
        return;
    }

    window.location.href = `/api/detail/export_finished?wono=${encodeURIComponent(currentWono)}`;
}

// ============================================
//   导出在制明细
// ============================================
function exportWipProducts() {
    if (!currentWono) {
        alert('请先查询工单');
        return;
    }

    window.location.href = `/api/detail/export_wip?wono=${encodeURIComponent(currentWono)}`;
}

// ============================================
//   重置明细查询状态
// ============================================
function resetDetailQuery() {
    detailQueryPackList = [];
    detailQueryCurrentPack = null;
    detailQueryLoaded = false;
    detailQueryLastWono = '';

    // 清空UI
    document.getElementById('detailPackListBody').innerHTML = '<div class="text-center py-3 text-muted"><i class="bi bi-inbox"></i> 请先查询工单</div>';
    document.getElementById('detailPackCount').textContent = '-';
    document.getElementById('detailWonoLabel').textContent = '-';

    // 清空单品查询
    document.getElementById('detailUnitSnInput').value = '';
    document.getElementById('detailUnitInfo').innerHTML = '<div class="text-center py-3 text-muted"><i class="bi bi-search"></i> 输入产品SN进行查询</div>';
    document.getElementById('detailUnitHistoryBody').innerHTML = '<tr><td colspan="5" class="text-center py-3 text-muted">等待查询</td></tr>';
    document.getElementById('detailUnitStationCount').textContent = '-';

    // 清空包装明细
    document.getElementById('detailPackInfo').innerHTML = '<div class="text-center py-3 text-muted"><i class="bi bi-box"></i> 从左侧选择一个批次</div>';
    document.getElementById('detailPackProductsBody').innerHTML = '<tr><td colspan="4" class="text-center py-3 text-muted"><i class="bi bi-hourglass"></i> 等待选择批次</td></tr>';
    document.getElementById('detailPackProductCount').textContent = '-';

    // 清空完工明细
    document.getElementById('detailFinishedInfo').innerHTML = '<div class="text-center py-3 text-muted"><i class="bi bi-check-circle"></i> 请先查询工单</div>';
    document.getElementById('detailFinishedProductsBody').innerHTML = '<tr><td colspan="4" class="text-center py-3 text-muted">请先查询工单</td></tr>';
    document.getElementById('detailFinishedCount').textContent = '-';

    // 清空在制明细
    document.getElementById('detailWipInfo').innerHTML = '<div class="text-center py-3 text-muted"><i class="bi bi-clock-history"></i> 请先查询工单</div>';
    document.getElementById('detailWipProductsBody').innerHTML = '<tr><td colspan="7" class="text-center py-3 text-muted">请先查询工单</td></tr>';
    document.getElementById('detailWipCount').textContent = '-';

    // 切换回单品查询Tab
    switchDetailTab('unit-trace');
}

// ============================================
//   页面初始化时绑定事件
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    initDetailQuery();
});
