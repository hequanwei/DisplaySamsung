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

// 触发模式
async function triggerMode(mode) {
  try {
    await fetch(`/api/mode?action=${encodeURIComponent(mode)}`);
    refreshStatus();
  } catch (e) {
    alert('请求失败: ' + e);
  }
}

// 设置方向
async function setOrientation(orient) {
  try {
    await fetch(`/api/orientation?val=${encodeURIComponent(orient)}`);
    refreshStatus();
  } catch (e) {
    alert('切换方向失败: ' + e);
  }
}

// 设置位置
async function setPosition(pos) {
  try {
    await fetch(`/api/position?val=${encodeURIComponent(pos)}`);
    refreshStatus();
  } catch (e) {
    alert('切换布局失败: ' + e);
  }
}

// 一键下发常亮指令
async function sendStayAwake() {
  try {
    const res = await fetch('/api/stay_awake');
    const msg = await res.text();
    alert(msg);
  } catch (e) {
    alert('执行失败: ' + e);
  }
}

// 日志操作
function copyLogs() {
  const text = document.getElementById('logContent')?.textContent || '';
  navigator.clipboard.writeText(text).then(() => {
    alert('日志内容已成功复制到剪贴板！');
  }).catch(() => {
    alert('复制失败，请手动选取复制');
  });
}

async function clearLogs() {
  if (confirm('确认清空当前的运行日志文件吗？')) {
    try {
      await fetch('/api/logs/clear', { method: 'POST' });
      refreshLogs();
    } catch (e) {
      alert('清空失败: ' + e);
    }
  }
}

function openLogFile() {
  fetch('/api/logs/reveal');
}

function openWebUI() {
  fetch('/api/tools/webui');
}

function reinstallSunshine() {
  fetch('/api/tools/install_sunshine');
}

function runDiagnostics() {
  fetch('/api/tools/diagnostics');
}

// 周期定时器
setInterval(refreshStatus, 2000);
setInterval(refreshLogs, 2500);

// 初始化首轮加载
refreshStatus();
refreshLogs();
