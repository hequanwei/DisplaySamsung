/**
 * DisplaySamsung 控制中心前端交互脚本
 * 负责 Tab 切换、实时状态刷新、实时日志拉取与各项调度指令交互
 */

// Tab 标签页切换逻辑
document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

    tab.classList.add('active');
    const targetId = `tab-${tab.getAttribute('data-tab')}`;
    const targetPane = document.getElementById(targetId);
    if (targetPane) {
      targetPane.classList.add('active');
      // 切换到日志页时自动滚动到底部
      if (tab.getAttribute('data-tab') === 'logs') {
        scrollLogsToBottom();
      }
    }
  });
});

// 状态刷新
async function refreshStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();

    // 更新版本与标题
    if (data.version) {
      document.getElementById('appVersion').textContent = `v${data.version}`;
    }

    const dot = document.getElementById('statusDot');
    const title = document.getElementById('statusTitle');
    const badge = document.getElementById('modeBadge');
    const metricRes = document.getElementById('metricRes');
    const metricIp = document.getElementById('metricIp');
    const metricLatency = document.getElementById('metricLatency');

    badge.textContent = data.mode ? data.mode.toUpperCase() : 'IDLE';

    if (data.mode === 'idle') {
      dot.className = 'pulse-dot';
      title.textContent = '未连接 (闲置)';
      badge.className = 'badge-capsule';
      metricIp.textContent = '--';
    } else {
      dot.className = 'pulse-dot green';
      badge.className = 'badge-capsule active';
      metricIp.textContent = data.ip || '127.0.0.1';

      if (data.mode === 'usb') {
        title.textContent = '运行中 [Type-C 有线直连]';
        metricLatency.innerHTML = '&lt; 1 <small>ms</small>';
      } else if (data.mode === 'wifi') {
        title.textContent = '运行中 [Wi-Fi 高速局域网]';
        metricLatency.innerHTML = '~ 2 <small>ms</small>';
      } else if (data.mode === 'hotspot') {
        title.textContent = '运行中 [Mac 便携热点]';
        metricLatency.innerHTML = '~ 1.5 <small>ms</small>';
      }
    }

    if (data.width && data.height) {
      metricRes.textContent = `${data.width} × ${data.height}`;
    }

    // 更新方向高亮
    if (data.orientation === 'portrait') {
      document.getElementById('orientPortrait').classList.add('active');
      document.getElementById('orientLandscape').classList.remove('active');
    } else {
      document.getElementById('orientLandscape').classList.add('active');
      document.getElementById('orientPortrait').classList.remove('active');
    }

    // 更新位置高亮
    const posBoxes = ['posLeft', 'posRight', 'posTop', 'posBottom'];
    posBoxes.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.remove('active');
    });
    if (data.position === 'left') document.getElementById('posLeft')?.classList.add('active');
    else if (data.position === 'top') document.getElementById('posTop')?.classList.add('active');
    else if (data.position === 'bottom') document.getElementById('posBottom')?.classList.add('active');
    else document.getElementById('posRight')?.classList.add('active');

  } catch (e) {
    console.debug('获取状态异常:', e);
  }
}

// 实时日志刷新
async function refreshLogs() {
  try {
    const res = await fetch('/api/logs');
    if (!res.ok) return;
    const text = await res.text();
    const logEl = document.getElementById('logContent');
    if (logEl) {
      logEl.textContent = text || '暂无运行日志';
      if (document.getElementById('chkAutoScroll')?.checked) {
        scrollLogsToBottom();
      }
    }
  } catch (e) {
    console.debug('获取日志异常:', e);
  }
}

function scrollLogsToBottom() {
  const viewer = document.getElementById('logViewer');
  if (viewer) {
    viewer.scrollTop = viewer.scrollHeight;
  }
}

// ==============================================================================
// 现代无阻塞 Toast 浮层通知
// ==============================================================================
function showToast(title, desc = '', type = 'info', duration = 3000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const icons = {
    info: '💡',
    success: '✅',
    warning: '⚠️',
    error: '❌'
  };

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || '💡'}</span>
    <div class="toast-body">
      <div class="toast-title">${title}</div>
      ${desc ? `<div class="toast-desc">${desc}</div>` : ''}
    </div>
  `;

  container.appendChild(toast);

  // 触发滑入动画
  requestAnimationFrame(() => {
    toast.classList.add('show');
  });

  // 自动淡出并销毁
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 300);
  }, duration);
}

// 触发模式
async function triggerMode(mode) {
  const modeNames = {
    usb: 'Type-C 有线直连',
    wifi: 'Wi-Fi 局域网',
    hotspot: 'Mac 便携热点',
    stop: '停止副屏'
  };
  showToast('正在切换模式', `正在唤起 ${modeNames[mode] || mode}...`, 'info', 2000);

  try {
    const res = await fetch(`/api/mode?action=${encodeURIComponent(mode)}`);
    const data = await res.json();
    if (data.success) {
      showToast('模式已生效', `已成功启动 ${modeNames[mode] || mode}`, 'success', 2500);
    } else {
      showToast('切换失败', data.error || '执行异常', 'error', 3500);
    }
    refreshStatus();
  } catch (e) {
    showToast('网络请求异常', String(e), 'error');
  }
}

// 设置方向
async function setOrientation(orient) {
  // 乐观即时更新高亮反馈
  if (orient === 'portrait') {
    document.getElementById('orientPortrait')?.classList.add('active');
    document.getElementById('orientLandscape')?.classList.remove('active');
  } else {
    document.getElementById('orientLandscape')?.classList.add('active');
    document.getElementById('orientPortrait')?.classList.remove('active');
  }

  showToast('正在调整屏幕方向', orient === 'portrait' ? '切换为竖屏模式' : '切换为横屏模式', 'info', 1800);

  try {
    const res = await fetch(`/api/orientation?val=${encodeURIComponent(orient)}`);
    const data = await res.json();
    if (data.success) {
      showToast('屏幕朝向已就绪', orient === 'portrait' ? '当前竖屏 1752×2800' : '当前横屏 2800×1752', 'success', 2000);
    } else {
      showToast('旋转屏幕异常', data.error || '切换失败', 'error');
    }
    refreshStatus();
  } catch (e) {
    showToast('切换方向失败', String(e), 'error');
  }
}

// 设置位置
async function setPosition(pos) {
  // 乐观即时更新位置高亮
  const posBoxes = ['posLeft', 'posRight', 'posTop', 'posBottom'];
  posBoxes.forEach(id => document.getElementById(id)?.classList.remove('active'));
  const activeMap = { left: 'posLeft', right: 'posRight', top: 'posTop', bottom: 'posBottom' };
  document.getElementById(activeMap[pos])?.classList.add('active');

  const posNames = { left: '左侧', right: '右侧', top: '上方', bottom: '下方' };
  showToast('副屏方位已更新', `鼠标现在穿透至主屏幕${posNames[pos]}`, 'success', 2000);

  try {
    await fetch(`/api/position?val=${encodeURIComponent(pos)}`);
    refreshStatus();
  } catch (e) {
    showToast('切换布局失败', String(e), 'error');
  }
}

// 一键下发常亮指令
async function sendStayAwake() {
  showToast('正在下发指令', '正在通过 ADB 唤醒平板屏幕...', 'info', 1800);
  try {
    const res = await fetch('/api/stay_awake');
    const data = await res.json();
    if (data.success) {
      showToast('常亮守护已激活', data.message, 'success', 3500);
    } else {
      showToast('未检测到设备', data.message, 'warning', 4000);
    }
  } catch (e) {
    showToast('执行失败', String(e), 'error');
  }
}

// 检查更新
async function checkAppUpdate() {
  const btnText = document.getElementById('btnCheckUpdateText');
  const badge = document.getElementById('updateBadge');
  const infoBox = document.getElementById('updateInfoBox');
  const msgEl = document.getElementById('updateMsg');
  const notesEl = document.getElementById('updateNotes');
  const dlBtn = document.getElementById('btnDownloadUpdate');

  if (btnText) btnText.textContent = '正在检测最新版本...';
  showToast('检查更新', '正在连接 GitHub Releases 校验版本...', 'info', 2000);

  try {
    const res = await fetch('/api/update/check');
    const data = await res.json();

    if (btnText) btnText.textContent = '立即检查更新';

    if (data.has_update) {
      if (badge) {
        badge.textContent = `发现 v${data.latest_version}`;
        badge.className = 'badge-capsule active';
      }
      if (infoBox) infoBox.style.display = 'block';
      if (msgEl) msgEl.textContent = `发现最新版本 v${data.latest_version}！建议更新以获取最佳体验。`;
      if (notesEl) notesEl.textContent = data.release_notes || '暂无详细更新日志';

      if (dlBtn) {
        dlBtn.style.display = 'flex';
        dlBtn.href = data.download_url || data.html_url || 'https://github.com/hequanwei/DisplaySamsung/releases';
      }

      showToast('发现新版本', `最新版本: v${data.latest_version}，已就绪可下载！`, 'success', 4000);
    } else {
      if (badge) {
        badge.textContent = '已是最新';
        badge.className = 'badge-capsule';
      }
      if (infoBox) {
        infoBox.style.display = 'block';
      }
      if (msgEl) msgEl.textContent = data.message || `当前版本已是最新 (v${data.current_version})。`;
      if (notesEl) notesEl.textContent = '系统运行平稳，暂无待升级项目。';
      if (dlBtn) dlBtn.style.display = 'none';

      showToast('当前已是最新', `已是最新版本 v${data.current_version}，无需更新。`, 'info', 2500);
    }
  } catch (e) {
    if (btnText) btnText.textContent = '立即检查更新';
    showToast('检查更新异常', String(e), 'warning', 3000);
  }
}

// 日志操作
function copyLogs() {
  const text = document.getElementById('logContent')?.textContent || '';
  navigator.clipboard.writeText(text).then(() => {
    showToast('复制成功', '日志内容已存入系统剪贴板', 'success', 2000);
  }).catch(() => {
    showToast('复制失败', '请手动全选复制', 'warning');
  });
}

async function clearLogs() {
  try {
    await fetch('/api/logs/clear', { method: 'POST' });
    refreshLogs();
    showToast('日志已清空', '运行日志文件已重置', 'info', 1800);
  } catch (e) {
    showToast('清空失败', String(e), 'error');
  }
}

function openLogFile() {
  fetch('/api/logs/reveal');
  showToast('正在打开访达', '已在 Finder 中定位日志文件', 'info', 1800);
}

function openWebUI() {
  fetch('/api/tools/webui');
  showToast('正在打开后台', '正在呼出 Sunshine Web 控制台...', 'info', 1800);
}

function reinstallSunshine() {
  fetch('/api/tools/install_sunshine');
  showToast('开始安装服务', '后台正在检测并安装 Sunshine 串流服务端...', 'info', 2500);
}

function runDiagnostics() {
  fetch('/api/tools/diagnostics');
  showToast('自检报告', '正在收集系统 DisplayID 与网络拓扑...', 'info', 2000);
}

// 周期定时器
setInterval(refreshStatus, 2000);
setInterval(refreshLogs, 2500);

// 初始化首轮加载
refreshStatus();
refreshLogs();

