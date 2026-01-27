/**
 * sidebar.js - 边栏导航模块
 * 设计：程远 | 2026-01-18
 * 包含：侧边栏初始化、视图切换
 * 优化：使用requestAnimationFrame避免卡顿
 */

// ============================================
//   边栏导航相关函数（简化版 - 固定显示）
// ============================================

// 视图切换锁，防止快速点击导致重复切换
let viewSwitching = false;

// 初始化边栏状态 - 简化版：侧边栏固定显示
function initSidebar() {
    // 绑定导航项点击事件
    document.querySelectorAll('.sidebar-item[data-view]').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();

            // 防止快速重复点击
            if (viewSwitching) return;

            const viewName = item.dataset.view;

            // 更新导航项active状态（同步执行，确保即时反馈）
            document.querySelectorAll('.sidebar-item[data-view]').forEach(navItem => {
                if (navItem.dataset.view === viewName) {
                    navItem.classList.add('active');
                } else {
                    navItem.classList.remove('active');
                }
            });

            // 使用requestAnimationFrame延迟视图切换，避免阻塞UI
            viewSwitching = true;
            requestAnimationFrame(() => {
                switchView(viewName, true);
                viewSwitching = false;
            });

        }, { passive: false });
    });
}

// ============================================
//   视图切换 - 简化版
// ============================================
// skipNavUpdate: 如果导航项已在点击事件中更新，跳过重复更新
function switchView(viewName, skipNavUpdate = false) {
    // 如果离开接口日志视图，停止自动刷新
    if (typeof stopEaiAutoRefresh === 'function') {
        stopEaiAutoRefresh();
    }

    // 如果离开操作日志视图，停止自动刷新
    if (typeof stopLogViewerAutoRefresh === 'function') {
        stopLogViewerAutoRefresh();
    }

    // 如果需要更新导航项状态（非点击触发时）
    if (!skipNavUpdate) {
        const sidebarItems = document.querySelectorAll('.sidebar-item[data-view]');
        sidebarItems.forEach(item => {
            if (item.dataset.view === viewName) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    }

    // 切换视图内容
    const viewContainers = document.querySelectorAll('.view-container');
    const targetView = document.getElementById('view-' + viewName);
    const currentActiveView = document.querySelector('.view-container.active');

    if (targetView && targetView !== currentActiveView) {
        targetView.classList.add('active');
        viewContainers.forEach(view => {
            if (view !== targetView) {
                view.classList.remove('active');
            }
        });
    } else if (targetView) {
        targetView.classList.add('active');
    }

    // 保存当前视图到localStorage
    localStorage.setItem('currentView', viewName);

    // 切换到接口日志视图时自动刷新
    if (viewName === 'interface-log') {
        if (eaiLogsData.length === 0) {
            setTimeout(() => queryEaiLogs(), 100);
        }
    }

    // 切换到HULU视图时：仅首次加载数据
    // 优化：使用requestIdleCallback在空闲时加载，避免阻塞UI
    if (viewName === 'hulu' && currentWono) {
        if (!huluDataLoaded) {
            const loadHuluData = () => {
                queryHuluData();
                huluDataLoaded = true;
            };

            // 优先使用requestIdleCallback，浏览器空闲时执行
            if (typeof requestIdleCallback !== 'undefined') {
                requestIdleCallback(loadHuluData, { timeout: 500 });
            } else {
                // 降级到setTimeout
                setTimeout(loadHuluData, 50);
            }
        }
    }

    // 切换到ERP详情视图时：仅首次加载数据（与HULU页面一致）
    if (viewName === 'erp-detail' && currentWono) {
        if (!erpDetailLoaded) {
            setTimeout(() => {
                refreshErpDetail();
                erpDetailLoaded = true;
            }, 100);
        }
    }

    // 切换到明细查询视图时：不自动加载数据，需要用户主动点击加载按钮
    // 注意：已移除自动加载逻辑

    // 切换到关于系统视图时：加载授权信息
    if (viewName === 'settings') {
        loadLicenseInfo();
    }

    // 切换到操作日志视图时：首次加载日志
    if (viewName === 'operation-log') {
        if (typeof loadLogContent === 'function') {
            setTimeout(() => loadLogContent(), 100);
        }
    }
}

// 加载授权信息（小图标+悬停提示）
let licenseInfoLoaded = false;
async function loadLicenseInfo() {
    if (licenseInfoLoaded) return;

    const iconEl = document.getElementById('licenseStatusIcon');
    if (!iconEl) return;

    try {
        const response = await fetch('/api/license_info');
        const data = await response.json();

        // 计算剩余天数显示（精确到天）
        let remainingText = '-';
        if (data.days_remaining !== undefined && data.days_remaining !== null) {
            if (data.days_remaining > 0) {
                remainingText = `${data.days_remaining} days`;
            } else if (data.days_remaining === 0) {
                remainingText = 'Expires today';
            } else {
                remainingText = `Expired ${-data.days_remaining} days ago`;
            }
        }

        // 构建tooltip内容（使用CSS类控制样式）
        const tooltipContent = `
            <div class="license-title">License Info</div>
            <div><span class="license-label">Customer:</span> <span class="license-value">${data.customer || '-'}</span></div>
            <div><span class="license-label">Expires:</span> <span class="license-value">${data.expire_date || '-'}</span></div>
            <div><span class="license-label">Remaining:</span> <span class="license-value">${remainingText}</span></div>
            <div><span class="license-label">Status:</span> <span class="license-value">${data.status || '-'}</span></div>
        `.trim();

        // 更新图标颜色
        const iconClass = data.status === 'Active'
            ? (data.days_remaining <= 7 ? 'text-warning' : 'text-success')
            : 'text-danger';
        iconEl.className = `license-status-icon ${iconClass}`;

        // 更新tooltip
        iconEl.setAttribute('title', tooltipContent);

        // 初始化或更新Bootstrap tooltip（使用自定义类）
        const existingTooltip = bootstrap.Tooltip.getInstance(iconEl);
        if (existingTooltip) {
            existingTooltip.dispose();
        }
        new bootstrap.Tooltip(iconEl, {
            html: true,
            trigger: 'hover',
            customClass: 'license-tooltip'
        });

        licenseInfoLoaded = true;
    } catch (e) {
        iconEl.className = 'license-status-icon text-secondary';
        iconEl.setAttribute('title', 'License info load failed');
    }
}
