/**
 * permission.js - 用户权限管理模块
 * 设计：程远 | 2026-01-21
 * 包含：用户登录、权限验证、按钮状态控制
 */

// ============================================
//   全局权限状态
// ============================================
let currentUser = {
    username: '',
    job: '',
    hasPermission: false,
    isLoggedIn: false
};

// ============================================
//   自动登出配置（5分钟无操作）
// ============================================
const AUTO_LOGOUT_TIMEOUT = 5 * 60 * 1000;  // 5分钟，单位毫秒
const WARNING_THRESHOLD = 60 * 1000;  // 1分钟前开始提醒
let idleTimer = null;
let lastActivityTime = Date.now();
let loginTime = null;  // 登录时间
let sessionTimerInterval = null;  // 会话计时器

// 需要权限控制的按钮选择器
const PERMISSION_BUTTONS = [
    '#btnAddToWorkorder',           // 加入工单按钮
    '#btnExecutePacking',           // 执行打包按钮
    '#btnSyncToHulu',               // 同步到HULU按钮
    '.btn-add-missing',             // 加入工单类按钮
    '.btn-execute-pack',            // 打包类按钮
    '.btn-sync-hulu'                // HULU同步类按钮
];

// ============================================
//   卡通头像配置（按职务分组）
// ============================================
const AVATAR_CONFIG = {
    // 管理类职务
    management: {
        keywords: ['经理', '主管', '总监', '主任', '组长', '领导', '负责人', '管理'],
        avatars: ['👔', '🎩', '👨‍💼', '👩‍💼', '🦸', '🦊']
    },
    // 技术/开发类
    tech: {
        keywords: ['工程师', '技术', '开发', '程序', 'IT', '软件', '系统', '架构'],
        avatars: ['👨‍💻', '👩‍💻', '🤖', '🦾', '🧙', '🦉']
    },
    // 设备/维修类
    equipment: {
        keywords: ['设备', '维修', '维护', '机修', '电工', '机电', '技师', '技工'],
        avatars: ['🔧', '⚙️', '🛠️', '👷', '🦺', '🐻']
    },
    // 品质/检验类
    quality: {
        keywords: ['品质', '质量', 'QA', 'QC', '检验', '测试', '品管', '审核'],
        avatars: ['🔍', '📋', '✅', '🎯', '🦅', '🐱']
    },
    // 物流/仓储类
    logistics: {
        keywords: ['物流', '仓库', '仓储', '配送', '物料', '库管', '收发'],
        avatars: ['📦', '🚚', '📥', '🏭', '🐘', '🦛']
    },
    // 生产/制造类
    production: {
        keywords: ['生产', '制造', '操作', '作业', '产线', '车间', '装配', '工艺'],
        avatars: ['🏭', '⚡', '🔩', '🎪', '🐂', '🦬']
    },
    // 默认头像
    default: {
        avatars: ['😊', '🙂', '😎', '🤗', '🐼', '🐨', '🦁', '🐯']
    }
};

// 根据职务获取随机头像
function getAvatarByJob(job) {
    if (!job) return getRandomItem(AVATAR_CONFIG.default.avatars);

    const jobLower = job.toLowerCase();

    // 遍历各分组，查找匹配的关键词
    for (const [group, config] of Object.entries(AVATAR_CONFIG)) {
        if (group === 'default') continue;
        if (config.keywords && config.keywords.some(kw => jobLower.includes(kw))) {
            return getRandomItem(config.avatars);
        }
    }

    // 无匹配，返回默认头像
    return getRandomItem(AVATAR_CONFIG.default.avatars);
}

// 从数组中随机选择一个元素
function getRandomItem(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
}

// ============================================
//   初始化权限模块
// ============================================
function initPermission() {
    // 从localStorage恢复用户状态
    const savedUser = localStorage.getItem('acc_user');
    if (savedUser) {
        try {
            currentUser = JSON.parse(savedUser);
            currentUser.isLoggedIn = true;
            updateUserDisplay();
            updatePermissionButtons();
            // 恢复登录状态后启动空闲检测
            resetIdleTimer();
            // 恢复会话计时器
            restoreSessionTimer();
        } catch (e) {
            console.error('恢复用户状态失败:', e);
            localStorage.removeItem('acc_user');
        }
    }

    // 绑定登录相关事件
    bindLoginEvents();

    // 初始更新按钮状态
    updatePermissionButtons();
}

// ============================================
//   绑定登录相关事件
// ============================================
function bindLoginEvents() {
    // 工号输入框回车事件（跳转到密码框）
    const usernameInput = document.getElementById('operatorUsername');
    if (usernameInput) {
        usernameInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const passwordInput = document.getElementById('operatorPassword');
                if (passwordInput) {
                    passwordInput.focus();
                }
            }
        });
    }

    // 密码输入框回车事件
    const passwordInput = document.getElementById('operatorPassword');
    if (passwordInput) {
        passwordInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                loginUser();
            }
        });
    }

    // 登录按钮点击事件
    const loginBtn = document.getElementById('btnLogin');
    if (loginBtn) {
        loginBtn.addEventListener('click', loginUser);
    }

    // 登出按钮点击事件（使用箭头函数避免event对象被传入）
    const logoutBtn = document.getElementById('btnLogout');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => logoutUser());
    }
}

// ============================================
//   用户登录（带密码验证）
// ============================================
async function loginUser() {
    const usernameInput = document.getElementById('operatorUsername');
    const passwordInput = document.getElementById('operatorPassword');
    const loginBtn = document.getElementById('btnLogin');
    const username = usernameInput ? usernameInput.value.trim() : '';
    const password = passwordInput ? passwordInput.value : '';

    if (!username) {
        showButtonStatus('请输入工号', 'warning');
        return;
    }

    if (!password) {
        showButtonStatus('请输入密码', 'warning');
        return;
    }

    // 显示登录中状态
    if (loginBtn) {
        loginBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> 登录中...';
        loginBtn.disabled = true;
    }

    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        const result = await response.json();

        if (!result.valid) {
            showButtonStatus(result.reason || '登录失败', 'danger');
            return;
        }

        // 更新当前用户状态
        currentUser = {
            username: result.username,
            job: result.job,
            hasPermission: result.has_permission,
            isLoggedIn: true
        };

        // 保存到localStorage
        localStorage.setItem('acc_user', JSON.stringify(currentUser));

        // 清空密码输入框
        if (passwordInput) passwordInput.value = '';

        // 显示登录成功状态，然后切换到用户信息
        const successMsg = result.has_permission ? '登录成功' : '登录成功';
        showButtonStatus(successMsg, 'success', () => {
            // 回调中更新界面
            updateUserDisplay();
            updatePermissionButtons();
        });

        // 记录日志
        log(`用户 ${username} 登录成功，权限: ${result.has_permission ? '有' : '无'}`, 'info');

        // 启动空闲检测计时器
        resetIdleTimer();

        // 启动会话计时器
        startSessionTimer();

    } catch (e) {
        console.error('登录失败:', e);
        showButtonStatus('网络错误', 'danger');
    }
}

// ============================================
//   用户登出
// ============================================
function logoutUser(customMessage) {
    // 记录登出的用户名（在清除状态前保存）
    const logoutUsername = currentUser.username;

    // 停止空闲检测计时器
    stopIdleTimer();

    // 停止会话计时器
    stopSessionTimer();

    // 调用后端API记录登出日志
    if (logoutUsername) {
        fetch('/api/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: logoutUsername })
        }).catch(e => console.warn('登出日志记录失败:', e));
    }

    currentUser = {
        username: '',
        job: '',
        hasPermission: false,
        isLoggedIn: false
    };

    localStorage.removeItem('acc_user');
    updateUserDisplay();
    updatePermissionButtons();

    // 登录按钮显示状态（支持自定义消息）
    showButtonStatus(customMessage || '已退出', 'secondary');

    log('用户已登出', 'info');
}

// ============================================
//   按钮状态显示（统一处理所有提示）
//   type: success(绿)/danger(红)/warning(黄)/secondary(灰)/primary(蓝)
// ============================================
function showButtonStatus(message, type, callback) {
    const loginBtn = document.getElementById('btnLogin');
    if (!loginBtn) {
        if (callback) callback();
        return;
    }

    // 保存原始状态（仅在首次调用时保存）
    if (!loginBtn._originalHTML) {
        loginBtn._originalHTML = '<i class="bi bi-box-arrow-in-right"></i> 登录';
        loginBtn._originalClass = 'btn btn-primary btn-sm w-100';
    }

    // 根据类型设置图标和颜色
    let icon = '';
    let btnClass = 'btn btn-sm w-100';
    switch(type) {
        case 'success':
            icon = '<i class="bi bi-check-circle"></i>';
            btnClass += ' btn-success';
            break;
        case 'danger':
            icon = '<i class="bi bi-x-circle"></i>';
            btnClass += ' btn-danger';
            break;
        case 'warning':
            icon = '<i class="bi bi-exclamation-triangle"></i>';
            btnClass += ' btn-warning';
            break;
        case 'secondary':
            icon = '<i class="bi bi-box-arrow-right"></i>';
            btnClass += ' btn-secondary';
            break;
        default:
            icon = '<i class="bi bi-info-circle"></i>';
            btnClass += ' btn-info';
    }

    // 显示状态
    loginBtn.innerHTML = `${icon} ${message}`;
    loginBtn.className = btnClass;
    loginBtn.disabled = true;

    // 1.5秒后恢复或执行回调
    setTimeout(() => {
        // 如果有回调（如登录成功后切换界面），先执行回调
        if (callback) {
            callback();
        } else {
            // 否则恢复登录按钮
            loginBtn.innerHTML = loginBtn._originalHTML;
            loginBtn.className = loginBtn._originalClass;
            loginBtn.disabled = false;
        }
    }, 1200);
}

// ============================================
//   更新用户显示
// ============================================
function updateUserDisplay() {
    const loginSection = document.getElementById('loginSection');
    const userInfoSection = document.getElementById('userInfoSection');
    const userNameDisplay = document.getElementById('userNameDisplay');
    const userJobDisplay = document.getElementById('userJobDisplay');
    const permissionBadge = document.getElementById('permissionBadge');
    const userAvatar = document.querySelector('.user-avatar');

    if (currentUser.isLoggedIn) {
        // 已登录：显示用户信息
        if (loginSection) loginSection.style.display = 'none';
        if (userInfoSection) userInfoSection.style.display = 'flex';
        if (userNameDisplay) userNameDisplay.textContent = currentUser.username;
        if (userJobDisplay) userJobDisplay.textContent = currentUser.job || '-';

        // 更新卡通头像（根据职务随机选择）
        if (userAvatar) {
            const avatar = getAvatarByJob(currentUser.job);
            userAvatar.innerHTML = `<span class="avatar-emoji">${avatar}</span>`;
        }

        if (permissionBadge) {
            if (currentUser.hasPermission) {
                permissionBadge.className = 'badge bg-success';
                permissionBadge.textContent = '可修改';
            } else {
                permissionBadge.className = 'badge bg-secondary';
                permissionBadge.textContent = '仅查询';
            }
        }
    } else {
        // 未登录：显示登录表单
        if (loginSection) loginSection.style.display = 'block';
        if (userInfoSection) userInfoSection.style.display = 'none';

        // 重置头像为默认图标
        if (userAvatar) {
            userAvatar.innerHTML = '<i class="bi bi-person-check-fill"></i>';
        }
    }
}

// ============================================
//   更新权限按钮状态
// ============================================
function updatePermissionButtons() {
    const hasPermission = currentUser.isLoggedIn && currentUser.hasPermission;

    PERMISSION_BUTTONS.forEach(selector => {
        const buttons = document.querySelectorAll(selector);
        buttons.forEach(btn => {
            if (hasPermission) {
                btn.disabled = false;
                btn.classList.remove('permission-disabled');
                btn.title = '';
            } else {
                btn.disabled = true;
                btn.classList.add('permission-disabled');
                btn.title = currentUser.isLoggedIn ? '您的职位无数据修改权限' : '请先登录';
            }
        });
    });
}

// ============================================
//   显示登录消息
// ============================================
function showLoginMessage(message, type = 'info') {
    const msgDiv = document.getElementById('loginMessage');
    if (msgDiv) {
        msgDiv.className = `login-message alert alert-${type}`;
        msgDiv.textContent = message;
        msgDiv.style.display = 'block';

        // 3秒后自动隐藏
        setTimeout(() => {
            msgDiv.style.display = 'none';
        }, 3000);
    }
}

// ============================================
//   检查操作权限（用于API调用前）
// ============================================
function checkOperationPermission(operationName = '此操作') {
    if (!currentUser.isLoggedIn) {
        showToast(`请先登录再${operationName}`, 'warning');
        return false;
    }

    if (!currentUser.hasPermission) {
        showToast(`您的职位无权${operationName}`, 'warning');
        return false;
    }

    return true;
}

// ============================================
//   获取当前操作员ID（用于API请求）
// ============================================
function getOperatorId() {
    return currentUser.isLoggedIn ? currentUser.username : '';
}

// ============================================
//   处理权限错误响应
// ============================================
function handlePermissionError(response) {
    if (response.permission_error) {
        showToast(`操作被拒绝: ${response.reason}`, 'danger');
        return true;
    }
    return false;
}

// ============================================
//   自动登出：重置空闲计时器
// ============================================
function resetIdleTimer() {
    lastActivityTime = Date.now();

    // 清除旧的计时器
    if (idleTimer) {
        clearTimeout(idleTimer);
    }

    // 只有在登录状态下才启动计时器
    if (currentUser.isLoggedIn) {
        idleTimer = setTimeout(() => {
            autoLogout();
        }, AUTO_LOGOUT_TIMEOUT);
    }
}

// ============================================
//   自动登出：执行登出
// ============================================
function autoLogout() {
    if (currentUser.isLoggedIn) {
        const username = currentUser.username;
        logoutUser('超时退出');
        log(`用户 ${username} 因5分钟无操作被自动登出`, 'info');
    }
}

// ============================================
//   自动登出：启动空闲检测
// ============================================
function startIdleDetection() {
    // 监听用户活动事件
    const activityEvents = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];

    activityEvents.forEach(eventType => {
        document.addEventListener(eventType, () => {
            if (currentUser.isLoggedIn) {
                resetIdleTimer();
            }
        }, { passive: true });
    });

    // 如果已登录，立即启动计时器
    if (currentUser.isLoggedIn) {
        resetIdleTimer();
    }
}

// ============================================
//   自动登出：停止空闲检测
// ============================================
function stopIdleTimer() {
    if (idleTimer) {
        clearTimeout(idleTimer);
        idleTimer = null;
    }
}

// ============================================
//   会话计时器：启动
// ============================================
function startSessionTimer() {
    loginTime = Date.now();
    // 保存登录时间到localStorage
    localStorage.setItem('acc_login_time', loginTime.toString());

    // 清除旧的计时器
    if (sessionTimerInterval) {
        clearInterval(sessionTimerInterval);
    }

    // 每秒更新显示
    sessionTimerInterval = setInterval(updateSessionTimerDisplay, 1000);
    updateSessionTimerDisplay();  // 立即显示一次
}

// ============================================
//   会话计时器：恢复（从localStorage）
// ============================================
function restoreSessionTimer() {
    const savedLoginTime = localStorage.getItem('acc_login_time');
    if (savedLoginTime) {
        loginTime = parseInt(savedLoginTime, 10);

        // 清除旧的计时器
        if (sessionTimerInterval) {
            clearInterval(sessionTimerInterval);
        }

        // 每秒更新显示
        sessionTimerInterval = setInterval(updateSessionTimerDisplay, 1000);
        updateSessionTimerDisplay();
    }
}

// ============================================
//   会话计时器：停止
// ============================================
function stopSessionTimer() {
    if (sessionTimerInterval) {
        clearInterval(sessionTimerInterval);
        sessionTimerInterval = null;
    }
    loginTime = null;
    localStorage.removeItem('acc_login_time');

    // 重置显示
    const timerDisplay = document.getElementById('sessionTimeDisplay');
    const timerContainer = document.getElementById('sessionTimer');
    if (timerDisplay) timerDisplay.textContent = '--:--';
    if (timerContainer) timerContainer.classList.remove('warning');
}

// ============================================
//   会话计时器：更新显示
// ============================================
function updateSessionTimerDisplay() {
    if (!loginTime || !currentUser.isLoggedIn) return;

    const timerDisplay = document.getElementById('sessionTimeDisplay');
    const timerContainer = document.getElementById('sessionTimer');
    if (!timerDisplay || !timerContainer) return;

    const now = Date.now();
    const elapsed = now - loginTime;  // 已登录时长
    const idleTime = now - lastActivityTime;  // 空闲时间
    const remainingIdle = AUTO_LOGOUT_TIMEOUT - idleTime;  // 剩余空闲时间

    // 格式化已登录时长
    const elapsedMinutes = Math.floor(elapsed / 60000);
    const elapsedSeconds = Math.floor((elapsed % 60000) / 1000);
    const elapsedStr = `${elapsedMinutes}:${elapsedSeconds.toString().padStart(2, '0')}`;

    // 检查是否需要警告
    if (remainingIdle <= WARNING_THRESHOLD && remainingIdle > 0) {
        // 显示倒计时警告
        const remainingSeconds = Math.ceil(remainingIdle / 1000);
        timerDisplay.textContent = `${remainingSeconds}秒后登出`;
        timerContainer.classList.add('warning');
    } else {
        // 正常显示已登录时长
        timerDisplay.textContent = `已登录 ${elapsedStr}`;
        timerContainer.classList.remove('warning');
    }
}

// ============================================
//   页面加载时初始化
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    initPermission();
    startIdleDetection();
});
