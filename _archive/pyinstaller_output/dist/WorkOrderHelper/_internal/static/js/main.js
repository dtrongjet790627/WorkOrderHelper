/**
 * main.js - 全局变量、工具函数、初始化
 * 设计：程远 | 2026-01-18
 * 包含：全局变量、Loading、日志、模态框、CustomTip、页面初始化
 */

// ============================================
//   全局变量
// ============================================
let currentWono = '';
let currentErpData = [];
let uploadedErpData = [];
let missingProductsData = [];
let selectedProducts = new Set();
let unpackedProductsData = [];
let selectedUnpackedProducts = new Set();
let packBatchesData = { target_batches: [], reference_batch: null };
let packDataCache = []; // 缓存打包数据用于模态框
let compareDataCache = []; // 缓存对比数据用于模态框
let currentWorkorderLine = ''; // 缓存当前工单产线
let mainPageTipData = { title: '', content: '' }; // 用于CustomTip的数据缓存

// ============================================
//   工具函数
// ============================================

// 加载提示语配置
const loadingMessages = [
    { text: '正在查询中...', sub: '请稍候，小管家正在努力工作' },
    { text: '正在处理数据...', sub: '马上就好，请耐心等待' },
    { text: '正在连接数据库...', sub: '正在获取最新数据' },
    { text: '正在分析工单...', sub: '小管家正在核对信息' },
    { text: '正在加载...', sub: '数据即将呈现' }
];

let loadingMsgInterval = null;

// 显示加载动画（支持自定义文字）
function showLoading(text, subtext) {
    const loading = document.getElementById('loading');
    const textEl = document.getElementById('loadingText');
    const subtextEl = document.getElementById('loadingSubtext');

    // 设置初始文字
    if (text) {
        textEl.textContent = text;
        subtextEl.textContent = subtext || '';
    } else {
        // 使用随机提示语
        const msg = loadingMessages[Math.floor(Math.random() * loadingMessages.length)];
        textEl.textContent = msg.text;
        subtextEl.textContent = msg.sub;

        // 启动文字轮换（每2秒切换一次）
        loadingMsgInterval = setInterval(() => {
            const newMsg = loadingMessages[Math.floor(Math.random() * loadingMessages.length)];
            textEl.style.opacity = '0';
            setTimeout(() => {
                textEl.textContent = newMsg.text;
                subtextEl.textContent = newMsg.sub;
                textEl.style.opacity = '1';
            }, 200);
        }, 2500);
    }

    loading.style.display = 'block';
}

// 隐藏加载动画
function hideLoading() {
    document.getElementById('loading').style.display = 'none';
    // 清除文字轮换定时器
    if (loadingMsgInterval) {
        clearInterval(loadingMsgInterval);
        loadingMsgInterval = null;
    }
}

function log(msg, type = 'info') {
    // 输出到浏览器控制台（按F12打开开发者工具查看）
    const time = new Date().toLocaleTimeString();
    const prefix = `[${time}]`;
    switch(type) {
        case 'success': console.log(`%c${prefix} ✓ ${msg}`, 'color: #4ec9b0'); break;
        case 'error': console.error(`${prefix} ✗ ${msg}`); break;
        case 'warning': console.warn(`${prefix} ⚠ ${msg}`); break;
        default: console.log(`%c${prefix} ${msg}`, 'color: #9cdcfe');
    }
}

function clearLog() {
    console.clear();
}

function scrollToSection(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ============================================
//   操作成功动画反馈
// ============================================

// 显示成功动画覆盖层
function showSuccessAnimation(duration = 1200) {
    // 创建覆盖层（如果不存在）
    let overlay = document.getElementById('successOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'successOverlay';
        overlay.className = 'success-overlay';
        overlay.innerHTML = `
            <div class="success-icon-wrapper">
                <i class="bi bi-check-lg"></i>
            </div>
        `;
        document.body.appendChild(overlay);
    }

    // 显示动画
    setTimeout(() => overlay.classList.add('show'), 10);

    // 自动隐藏
    setTimeout(() => {
        overlay.classList.remove('show');
    }, duration);
}

// 给卡片添加成功高亮效果
function highlightCard(cardSelector) {
    const card = document.querySelector(cardSelector);
    if (card) {
        card.classList.add('card-success-highlight');
        setTimeout(() => {
            card.classList.remove('card-success-highlight');
        }, 1000);
    }
}

// 给按钮添加成功脉冲效果
function pulseButton(button) {
    if (typeof button === 'string') {
        button = document.querySelector(button);
    }
    if (button) {
        button.classList.add('btn-success-pulse');
        setTimeout(() => {
            button.classList.remove('btn-success-pulse');
        }, 600);
    }
}

// 增强版showToast - 添加动画效果
const originalShowToast = typeof showToast === 'function' ? showToast : null;
function showToastWithAnimation(message, type = 'info') {
    // 如果是成功类型，添加动画
    if (type === 'success') {
        // 可以选择显示短暂的成功动画
        // showSuccessAnimation(800);
    }

    // 调用原始toast函数（如果存在）
    if (typeof showToast === 'function' && showToast !== showToastWithAnimation) {
        showToast(message, type);
    }
}

// ============================================
//   刷新打包和ERP对比数据
// ============================================
async function refreshPackErpData() {
    if (!currentWono) {
        alert('请先查询工单');
        return;
    }
    log('刷新打包和ERP对比数据...');
    document.getElementById('compareStatus').innerHTML = '<i class="bi bi-hourglass-split"></i> 刷新中...';

    // 重新查询工单获取最新打包数据
    try {
        const response = await fetch('/api/query_workorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wono: currentWono })
        });
        const data = await response.json();
        if (!data.error) {
            // 更新打包数据缓存
            packDataCache = data.packs || [];
            let actualSum = 0, infoSum = 0, sealedCount = 0;
            packDataCache.forEach(p => {
                actualSum += p.actual_qty || 0;
                infoSum += p.info_qty || 0;
                if (p.status === '已封包') sealedCount++;
            });
            document.getElementById('packCount').textContent = packDataCache.length;
            document.getElementById('packTotal').textContent = actualSum;
            document.getElementById('packSealedCount').textContent = sealedCount;
        document.getElementById('packCount').textContent = packDataCache.length;
            document.getElementById('packInfoSum').textContent = infoSum;
            document.getElementById('accTotalSum').textContent = actualSum;
        }
    } catch (e) {
        log('刷新打包数据失败: ' + e.message, 'error');
    }

    // 刷新ERP对比
    await compareAccErp();
    log('刷新完成', 'success');
}

// ============================================
//   打包+ERP对比合并详情模态框
// ============================================
function showPackErpDetailModal() {
    const tbody = document.getElementById('packErpUnifiedTable').getElementsByTagName('tbody')[0];
    tbody.innerHTML = '';

    // 构建ACC打包数据映射 {packid: {actual_qty, info_qty, status}}
    const accMap = {};
    packDataCache.forEach(p => {
        accMap[p.packid] = { actual_qty: p.actual_qty || 0, info_qty: p.info_qty || 0, status: p.status, schb_number: p.schb_number || '' };
    });

    // 构建ERP数据映射 {packid: {total_qty, records[]}}
    // 同批次多次收货需要累加，并记录每条收货明细
    const erpMap = {};
    compareDataCache.forEach(c => {
        if (!erpMap[c.packid]) {
            erpMap[c.packid] = { total_qty: 0, records: [] };
        }
        erpMap[c.packid].total_qty += (c.erp_qty || 0);
        erpMap[c.packid].records.push({
            qty: c.erp_qty || 0,
            bill_no: c.bill_no || ''
        });
    });

    // 合并所有批次号
    const allPackIds = new Set([...Object.keys(accMap), ...Object.keys(erpMap)]);
    const sortedPackIds = Array.from(allPackIds).sort();

    let totalAcc = 0, totalInfo = 0, totalErp = 0;

    sortedPackIds.forEach(packid => {
        const accData = accMap[packid] || { actual_qty: 0, info_qty: 0, status: '-' };
        const erpData = erpMap[packid] || { total_qty: 0, records: [] };
        const erpQty = erpData.total_qty;
        const erpRecords = erpData.records;
        const accQty = accData.actual_qty;
        const infoQty = accData.info_qty;
        const isPacking = accData.status !== '已封包' && accData.status !== '-';
        const diff = isPacking ? 0 : (accQty - erpQty);  // 打包中不算差异

        // 打包中批次完全不计入任何合计
        if (!isPacking) {
            totalAcc += accQty;
            totalInfo += infoQty;
            totalErp += erpQty;
        }

        // 判断行颜色
        let rowStyle = '';
        let rowTitle = '';
        if (isPacking) {
            // 打包中批次 - 灰色背景
            rowStyle = 'background:linear-gradient(90deg, #fff3e0 0%, #ffe0b2 100%);border-left:4px solid #fd7e14;';
            rowTitle = '打包中(不计入差异)';
        } else if (!accMap[packid] && erpMap[packid]) {
            // ERP独有（手动收货，批次不符）
            rowStyle = 'background:linear-gradient(90deg, #fff3cd 0%, #ffecb5 100%);border-left:4px solid #ffc107;';
            rowTitle = 'ERP手动收货(ACC无此批次)';
        } else if (accMap[packid] && !erpMap[packid]) {
            // ACC独有
            rowStyle = 'background:linear-gradient(90deg, #cfe2ff 0%, #b6d4fe 100%);border-left:4px solid #0d6efd;';
            rowTitle = 'ACC独有(ERP未收货)';
        } else if (diff !== 0) {
            // 有差异
            rowStyle = 'background:linear-gradient(90deg, #f8d7da 0%, #f5c2c7 100%);border-left:4px solid #dc3545;';
            rowTitle = '数量有差异';
        }

        // 打包中批次差异显示"-"
        let diffDisplay = '-';
        if (!isPacking) {
            diffDisplay = diff > 0 ? `<span class="text-danger fw-bold">+${diff}</span>` :
                          diff < 0 ? `<span class="text-success fw-bold">${diff}</span>` : '0';
        }
        let statusBadge = '-';
        if (accData.status === '已封包') {
            statusBadge = '<span class="status-sealed">已封包</span>';
        } else if (accData.status !== '-') {
            statusBadge = '<span class="badge bg-info text-dark">打包中</span>';
        }

        // ERP数量显示：如果有多条记录，显示明细
        let erpQtyDisplay = erpQty || '-';
        if (erpRecords.length > 1) {
            // 同批次多次收货，显示总数和明细
            const details = erpRecords.map(r => `${r.qty}(${r.bill_no})`).join('<br>');
            erpQtyDisplay = `<span class="text-warning fw-bold" data-bs-toggle="tooltip" data-bs-html="true" title="多次收货:<br>${details}">${erpQty} ⚠</span>`;
        }

        const row = tbody.insertRow();
        row.style.cssText = rowStyle;
        row.title = rowTitle;
        // 打包中批次数量用灰色显示
        const packidHtml = isPacking ?
            `${packid} <span class="badge bg-warning text-dark" style="font-size:0.7em;">打包中</span>` : packid;
        const accDisplay = isPacking ?
            `<span class="text-muted">(${accQty})</span>` : (accQty || '-');
        const infoDisplay = isPacking ?
            `<span class="text-muted">(${infoQty})</span>` : (infoQty || '-');

        row.innerHTML = `
            <td class="ps-4">${packidHtml}</td>
            <td class="text-center">${accDisplay}</td>
            <td class="text-center">${infoDisplay}</td>
            <td class="text-center">${erpQtyDisplay}</td>
            <td class="text-center">${diffDisplay}</td>
            <td class="text-center">${accData.schb_number || '-'}</td>
        `;
    });

    // 初始化tooltips
    document.querySelectorAll('#packErpUnifiedTable [data-bs-toggle="tooltip"]').forEach(el => {
        new bootstrap.Tooltip(el);
    });

    // 更新汇总
    document.getElementById('unifiedAccTotal').textContent = totalAcc;
    document.getElementById('unifiedInfoTotal').textContent = totalInfo;
    document.getElementById('unifiedErpTotal').textContent = totalErp;
    const totalDiff = totalAcc - totalErp;
    const diffColor = totalDiff > 0 ? '#90EE90' : (totalDiff < 0 ? '#FFB6C1' : '#fff');
    document.getElementById('unifiedDiffTotal').innerHTML = `<span style="color:${diffColor};font-weight:bold;">${totalDiff > 0 ? '+' : ''}${totalDiff}</span>`;

    new bootstrap.Modal(document.getElementById('packErpCombinedModal')).show();
}

// 兼容旧函数名
function showPackDetailModal() {
    showPackErpDetailModal();
}

// 显示ERP对比详情模态框
function showCompareDetailModal() {
    showPackErpDetailModal();
}

// ============================================
//   结果模态框
// ============================================
function showResultModal(type, title, content) {
    const header = document.getElementById('resultModalHeader');
    const bgClass = type === 'success' ? 'bg-success text-white' :
                   type === 'info' ? 'bg-primary text-white' : 'bg-danger text-white';
    header.className = 'modal-header ' + bgClass;
    document.getElementById('resultModalTitle').textContent = title;
    document.getElementById('resultModalBody').innerHTML = content;

    // 成功类型显示动画
    if (type === 'success') {
        showSuccessAnimation(800);
    }

    // 延迟显示模态框，让动画先播放
    setTimeout(() => {
        new bootstrap.Modal(document.getElementById('resultModal')).show();
    }, type === 'success' ? 500 : 0);
}

// ============================================
//   自定义可复制提示框系统
// ============================================
const CustomTip = {
    tip: null,
    currentTrigger: null,
    hideTimer: null,

    init() {
        // 创建提示框容器
        this.tip = document.createElement('div');
        this.tip.className = 'custom-tip';
        this.tip.id = 'customTip';
        document.body.appendChild(this.tip);

        // 鼠标进入提示框时保持显示
        this.tip.addEventListener('mouseenter', () => {
            if (this.hideTimer) {
                clearTimeout(this.hideTimer);
                this.hideTimer = null;
            }
        });

        // 鼠标离开提示框时隐藏
        this.tip.addEventListener('mouseleave', () => {
            this.hide();
        });
    },

    show(trigger, title, content) {
        if (this.hideTimer) {
            clearTimeout(this.hideTimer);
            this.hideTimer = null;
        }

        this.currentTrigger = trigger;

        // 设置内容
        let html = '';
        if (title) {
            html += `<div class="custom-tip-title">${title}</div>`;
        }
        html += `<div class="custom-tip-content">${content}</div>`;
        this.tip.innerHTML = html;

        // 显示并定位
        this.tip.style.display = 'block';

        const rect = trigger.getBoundingClientRect();
        const tipRect = this.tip.getBoundingClientRect();

        let left = rect.left + (rect.width / 2) - (tipRect.width / 2);
        let top = rect.bottom + 8;

        // 边界检查
        if (left < 10) left = 10;
        if (left + tipRect.width > window.innerWidth - 10) {
            left = window.innerWidth - tipRect.width - 10;
        }
        if (top + tipRect.height > window.innerHeight - 10) {
            top = rect.top - tipRect.height - 8;
            // 调整箭头方向
            this.tip.classList.add('tip-above');
        } else {
            this.tip.classList.remove('tip-above');
        }

        this.tip.style.left = left + 'px';
        this.tip.style.top = top + 'px';
    },

    scheduleHide() {
        this.hideTimer = setTimeout(() => this.hide(), 100);
    },

    hide() {
        this.tip.style.display = 'none';
        this.currentTrigger = null;
        if (this.hideTimer) {
            clearTimeout(this.hideTimer);
            this.hideTimer = null;
        }
    },

    bindTrigger(element, title, contentFn) {
        element.addEventListener('mouseenter', () => {
            const content = typeof contentFn === 'function' ? contentFn() : contentFn;
            this.show(element, title, content);
        });
        element.addEventListener('mouseleave', () => {
            this.scheduleHide();
        });
    }
};

// ============================================
//   恢复上次视图
// ============================================
function restoreLastView() {
    const savedView = localStorage.getItem('currentView');
    if (savedView) {
        switchView(savedView);
    }
}

// ============================================
//   搜索历史记录功能
// ============================================
const SEARCH_HISTORY_KEY = 'wono_search_history';
const MAX_HISTORY_SIZE = 10;

// 加载搜索历史到datalist
function loadSearchHistory() {
    const datalist = document.getElementById('wonoHistory');
    if (!datalist) return;

    const history = getSearchHistory();
    datalist.innerHTML = '';

    history.forEach(wono => {
        const option = document.createElement('option');
        option.value = wono;
        datalist.appendChild(option);
    });
}

// 获取搜索历史
function getSearchHistory() {
    try {
        const saved = localStorage.getItem(SEARCH_HISTORY_KEY);
        return saved ? JSON.parse(saved) : [];
    } catch (e) {
        return [];
    }
}

// 保存搜索历史
function saveSearchHistory(wono) {
    if (!wono || wono.trim() === '') return;

    const cleanWono = wono.trim().toUpperCase();
    let history = getSearchHistory();

    // 移除重复项
    history = history.filter(item => item !== cleanWono);

    // 添加到开头
    history.unshift(cleanWono);

    // 限制数量
    if (history.length > MAX_HISTORY_SIZE) {
        history = history.slice(0, MAX_HISTORY_SIZE);
    }

    localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(history));

    // 更新datalist
    loadSearchHistory();
}

// 清除搜索历史
function clearSearchHistory() {
    if (confirm('确定要清除所有搜索历史吗？')) {
        localStorage.removeItem(SEARCH_HISTORY_KEY);
        loadSearchHistory();
        showToast('搜索历史已清除', 'info');
        log('搜索历史已清除', 'info');
    }
}

// ============================================
//   快捷键支持
// ============================================
const SHORTCUTS = {
    'Ctrl+F': { action: () => focusSearchInput(), desc: '聚焦搜索框' },
    '/': { action: () => focusSearchInput(), desc: '聚焦搜索框' },
    'Ctrl+R': { action: () => refreshCurrentView(), desc: '刷新当前视图' },
    '1': { action: () => switchView('workorder'), desc: '切换到工单数据' },
    '2': { action: () => switchView('hulu'), desc: '切换到HULU同步' },
    '3': { action: () => switchView('erp-detail'), desc: '切换到明细查询' },
    '4': { action: () => switchView('eai-logs'), desc: '切换到EAI日志' },
    'Escape': { action: () => closeAllModals(), desc: '关闭弹窗' }
};

function initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // 如果在输入框中，只响应Escape
        const isInInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName);
        if (isInInput && e.key !== 'Escape') return;

        let shortcut = '';
        if (e.ctrlKey) shortcut += 'Ctrl+';
        if (e.altKey) shortcut += 'Alt+';
        if (e.shiftKey) shortcut += 'Shift+';
        shortcut += e.key.toUpperCase();

        // 检查单键快捷键（数字键和/键）
        if (!e.ctrlKey && !e.altKey && !e.shiftKey) {
            if (e.key === '/') {
                e.preventDefault();
                SHORTCUTS['/'].action();
                return;
            }
            if (['1', '2', '3', '4'].includes(e.key)) {
                SHORTCUTS[e.key].action();
                return;
            }
            if (e.key === 'Escape') {
                SHORTCUTS['Escape'].action();
                return;
            }
        }

        // 检查组合键快捷键
        if (SHORTCUTS[shortcut]) {
            e.preventDefault();
            SHORTCUTS[shortcut].action();
        }
    });

    log('快捷键已启用: / 搜索, 1-4 切换视图, Ctrl+R 刷新, Esc 关闭弹窗', 'info');
}

function focusSearchInput() {
    const input = document.getElementById('wonoInput');
    if (input) {
        input.focus();
        input.select();
    }
}

function refreshCurrentView() {
    const savedView = localStorage.getItem('currentView') || 'workorder';
    switch (savedView) {
        case 'workorder':
            if (currentWono) queryWorkorder();
            break;
        case 'eai-logs':
            queryEaiLogs();
            break;
        case 'hulu':
            // HULU视图刷新
            break;
        case 'erp-detail':
            // 明细查询刷新
            break;
    }
    log('视图已刷新', 'info');
}

function closeAllModals() {
    // 关闭所有Bootstrap模态框
    document.querySelectorAll('.modal.show').forEach(modal => {
        const bsModal = bootstrap.Modal.getInstance(modal);
        if (bsModal) bsModal.hide();
    });
}

// ============================================
//   页面初始化
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    initSidebar();
    restoreLastView();
    CustomTip.init();
    loadSearchHistory();  // 加载搜索历史
    initKeyboardShortcuts();  // 初始化快捷键
});
