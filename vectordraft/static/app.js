/* PlotCAD Studio — Application Logic */

// ── State ──
let currentPage = 'dashboard';
let currentJobId = null;
let jobs = [];
let penLibrary = null;
let ws = null;
let plotTotal = 0;
let plotSent = 0;

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
  setupNavigation();
  setupDropzone();
  setupWebSocket();
  loadDashboard();
  loadPenLibrary();
  refreshPorts();
});

// ── Navigation ──
function setupNavigation() {
  document.querySelectorAll('.nav-item[data-page]').forEach(btn => {
    btn.addEventListener('click', () => navigateTo(btn.dataset.page));
  });
}

function navigateTo(page, params) {
  currentPage = page;

  // Hide all sections
  document.querySelectorAll('.page-section').forEach(el => el.classList.remove('active'));

  // Deactivate nav
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

  // Show target section
  const sectionId = page === 'job-detail' ? 'pageJobDetail' : `page${capitalize(page.replace(/-/g, ''))}`;
  const section = document.getElementById(sectionId);
  if (section) section.classList.add('active');

  // Activate nav item
  const nav = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (nav) nav.classList.add('active');

  // Page-specific loads
  if (page === 'dashboard') loadDashboard();
  if (page === 'jobs') loadJobs();
  if (page === 'job-detail' && params?.jobId) loadJobDetail(params.jobId);
  if (page === 'machine') refreshMachineStatus();
  if (page === 'pen-library') renderPenLibrary();
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ── Dashboard ──
async function loadDashboard() {
  try {
    jobs = await api('/api/jobs');
    const completed = jobs.filter(j => j.status === 'completed').length;
    const pending = jobs.filter(j => ['prepared', 'queued', 'uploaded'].includes(j.status)).length;

    document.getElementById('statTotalJobs').textContent = jobs.length;
    document.getElementById('statCompleted').textContent = completed;
    document.getElementById('statPending').textContent = pending;

    // Machine status
    const machine = await api('/api/machine/status');
    document.getElementById('statMachineState').textContent = capitalize(machine.state);
    updateMachineIndicator(machine.state);

    // Recent jobs
    const recent = jobs.slice(0, 5);
    const container = document.getElementById('recentJobsList');
    if (recent.length === 0) {
      container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📭</div>
        <div class="empty-state-title">No jobs yet</div>
        <p class="text-sm text-muted">Upload a drawing to get started.</p></div>`;
    } else {
      container.innerHTML = recent.map(j => renderJobRow(j)).join('');
    }
  } catch (e) {
    console.error('Dashboard load failed:', e);
  }
}

function renderJobRow(job) {
  const time = job.created_at ? new Date(job.created_at).toLocaleString() : '';
  return `<div class="job-card" onclick="openJob('${job.id}')">
    <div class="job-card-header">
      <span class="job-filename">${escHtml(job.source_filename || job.id)}</span>
      <span class="badge ${job.status}">${job.status}</span>
    </div>
    <div class="job-meta">
      <span class="job-meta-item">📐 <span class="value">${job.page_name || '?'}</span></span>
      <span class="job-meta-item">📏 <span class="value">${job.path_count ?? '?'} paths</span></span>
      <span class="job-meta-item">⏱ <span class="value">${formatDuration(job.estimated_duration_s)}</span></span>
      <span class="job-meta-item">📅 <span class="value">${time}</span></span>
    </div>
  </div>`;
}

// ── Jobs List ──
async function loadJobs() {
  try {
    jobs = await api('/api/jobs');
    const grid = document.getElementById('jobGrid');
    const empty = document.getElementById('jobsEmpty');

    if (jobs.length === 0) {
      grid.innerHTML = '';
      empty.classList.remove('hidden');
    } else {
      empty.classList.add('hidden');
      grid.innerHTML = jobs.map(j => renderJobRow(j)).join('');
    }
  } catch (e) {
    console.error('Jobs load failed:', e);
  }
}

function openJob(jobId) {
  currentJobId = jobId;
  navigateTo('job-detail', { jobId });
}

// ── Job Detail ──
async function loadJobDetail(jobId) {
  currentJobId = jobId;
  try {
    const job = await api(`/api/jobs/${jobId}`);

    document.getElementById('detailTitle').textContent = job.source_filename || jobId;
    document.getElementById('detailSubtitle').textContent = `Job ${jobId}`;
    document.getElementById('detailBadge').textContent = job.status;
    document.getElementById('detailBadge').className = `badge ${job.status}`;

    // Info table
    const info = document.getElementById('infoBody');
    info.innerHTML = `
      <tr><td class="text-muted">Page</td><td>${job.page?.name || job.page_name || '?'} — ${job.page?.width_mm || job.page_width_mm || '?'} × ${job.page?.height_mm || job.page_height_mm || '?'} mm</td></tr>
      <tr><td class="text-muted">Paths</td><td>${job.path_count ?? '?'}</td></tr>
      <tr><td class="text-muted">Layers</td><td>${job.layer_count ?? (job.layers?.length ?? '?')}</td></tr>
      <tr><td class="text-muted">Draw length</td><td>${(job.draw_length_mm ?? 0).toFixed(1)} mm</td></tr>
      <tr><td class="text-muted">Est. time</td><td>${formatDuration(job.estimated_duration_s)}</td></tr>
    `;

    // Layers
    const layerBody = document.getElementById('layerBody');
    if (job.layers && job.layers.length > 0) {
      layerBody.innerHTML = job.layers.map(l =>
        `<tr><td>${escHtml(l)}</td><td class="text-mono text-muted">—</td></tr>`
      ).join('');
    } else {
      layerBody.innerHTML = '<tr><td colspan="2" class="text-muted">No layers</td></tr>';
    }

    // Warnings
    const warningsCard = document.getElementById('warningsCard');
    const warningsList = document.getElementById('warningsList');
    if (job.warnings && job.warnings.length > 0) {
      warningsCard.classList.remove('hidden');
      warningsList.innerHTML = job.warnings.map(w =>
        `<li class="warning-item">${escHtml(w)}</li>`
      ).join('');
    } else {
      warningsCard.classList.add('hidden');
    }

    // G-code download
    document.getElementById('downloadGcode').href = `/api/jobs/${jobId}/gcode`;
    document.getElementById('downloadGcode').download = `${job.source_filename || 'plot'}.gcode`;

    // Load preview
    loadPreview(jobId);

    // Load ports for plot
    refreshPortSelect();

  } catch (e) {
    console.error('Job detail load failed:', e);
    toast('Failed to load job details', 'error');
  }
}

async function loadPreview(jobId) {
  try {
    const resp = await fetch(`/api/jobs/${jobId}/preview.svg`);
    if (resp.ok) {
      const svg = await resp.text();
      document.getElementById('previewContent').innerHTML = svg;
    }
  } catch (e) {
    document.getElementById('previewContent').innerHTML =
      '<div class="empty-state"><div class="empty-state-icon">🖼</div><div class="empty-state-title">Preview unavailable</div></div>';
  }
}

function resetPreviewZoom() {
  const svg = document.querySelector('#previewContent svg');
  if (svg) {
    svg.style.transform = '';
  }
}

// ── Upload ──
function setupDropzone() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  const uploadBtn = document.getElementById('uploadBtn');
  const uploadOptions = document.getElementById('uploadOptions');

  ['dragenter', 'dragover'].forEach(evt => {
    dropzone.addEventListener(evt, e => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(evt => {
    dropzone.addEventListener(evt, e => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
    });
  });

  dropzone.addEventListener('drop', e => {
    const file = e.dataTransfer.files[0];
    if (file) selectFile(file);
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) selectFile(fileInput.files[0]);
  });

  uploadBtn.addEventListener('click', doUpload);

  let selectedFile = null;

  function selectFile(file) {
    selectedFile = file;
    uploadOptions.style.display = 'block';
    uploadBtn.disabled = false;
    dropzone.querySelector('.dropzone-text').textContent = file.name;
    dropzone.querySelector('.dropzone-hint').textContent =
      `${(file.size / 1024).toFixed(1)} KB — ready to import`;
  }

  async function doUpload() {
    if (!selectedFile) return;

    uploadBtn.disabled = true;
    document.getElementById('uploadSpinner').classList.remove('hidden');

    const formData = new FormData();
    formData.append('file', selectedFile);

    const page = document.getElementById('pagePreset').value;
    const autoScale = document.getElementById('uploadAutoScale')?.checked || false;
    const rotateDeg = document.getElementById('uploadRotate')?.value || '0';
    let url = '/api/jobs/upload?';
    const params = new URLSearchParams();
    if (page) params.append('page', page);
    if (autoScale) params.append('auto_scale', 'true');
    if (rotateDeg !== '0') params.append('rotate_deg', rotateDeg);
    url += params.toString();

    try {
      const result = await fetch(url, { method: 'POST', body: formData }).then(r => {
        if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
        return r.json();
      });

      toast(`Job created: ${result.source_filename || result.job_id}`, 'success');
      openJob(result.job_id);

    } catch (e) {
      toast(`Upload failed: ${e.message}`, 'error');
    } finally {
      uploadBtn.disabled = false;
      document.getElementById('uploadSpinner').classList.add('hidden');
    }
  }
}

// ── Plot ──
async function startPlot() {
  if (!currentJobId) return;

  const port = document.getElementById('portSelect').value;
  const dryRun = !port;

  document.getElementById('plotBtn').disabled = true;
  document.getElementById('cancelBtn').classList.remove('hidden');
  document.getElementById('plotProgressBar').classList.remove('hidden');
  document.getElementById('plotInfo').classList.remove('hidden');
  document.getElementById('plotProgressFill').style.width = '0%';
  document.getElementById('plotInfo').textContent = 'Starting...';
  plotSent = 0;
  plotTotal = 0;

  try {
    await api(`/api/jobs/${currentJobId}/plot?dry_run=${dryRun}${port ? '&port=' + encodeURIComponent(port) : ''}`, {
      method: 'POST',
    });
  } catch (e) {
    toast(`Plot failed: ${e.message}`, 'error');
    resetPlotUI();
  }
}

async function cancelPlot() {
  try {
    await api('/api/jobs/cancel', { method: 'POST' });
    toast('Plot cancelled', 'info');
  } catch (e) {
    console.error('Cancel failed:', e);
  }
}

function resetPlotUI() {
  document.getElementById('plotBtn').disabled = false;
  document.getElementById('cancelBtn').classList.add('hidden');
  document.getElementById('plotProgressBar').classList.add('hidden');
  document.getElementById('plotInfo').classList.add('hidden');
}

function deleteCurrentJob() {
  if (!currentJobId) return;
  if (!confirm('Delete this job?')) return;
  api(`/api/jobs/${currentJobId}`, { method: 'DELETE' })
    .then(() => {
      toast('Job deleted', 'info');
      navigateTo('jobs');
    })
    .catch(e => toast(`Delete failed: ${e.message}`, 'error'));
}

// ── Pen Library ──
async function loadPenLibrary() {
  try {
    penLibrary = await api('/api/pen-library');
  } catch (e) {
    console.error('Pen library load failed:', e);
  }
}

function renderPenLibrary() {
  if (!penLibrary) return;
  const grid = document.getElementById('penGrid');
  grid.innerHTML = penLibrary.pens.map(pen => `
    <div class="pen-card">
      <div class="pen-header">
        <div class="pen-swatch" style="background: ${pen.color}"></div>
        <span class="pen-name">${escHtml(pen.id)}</span>
      </div>
      <div class="pen-detail">Width: ${pen.nominal_width_mm} mm</div>
      <div class="pen-detail">Draw: ${pen.draw_feed_mm_min} mm/min</div>
      <div class="pen-detail">Travel: ${pen.travel_feed_mm_min} mm/min</div>
      <div class="pen-detail">Dwell: ↓${pen.down_dwell_ms}ms ↑${pen.up_dwell_ms}ms</div>
      <div class="pen-detail">Type: ${pen.tool_type}</div>
    </div>
  `).join('');
}

// ── Machine ──
async function refreshMachineStatus() {
  try {
    const status = await api('/api/machine/status');
    document.getElementById('machineState').textContent = capitalize(status.state);
    document.getElementById('machineActiveJob').textContent = status.active_job_id || '—';
    updateMachineIndicator(status.state);
  } catch (e) {
    console.error('Machine status failed:', e);
  }
}

async function refreshPorts() {
  try {
    const data = await api('/api/machine/ports');
    const list = document.getElementById('machinePortsList');
    if (data.ports.length === 0) {
      list.textContent = 'No serial ports detected.';
    } else {
      list.innerHTML = data.ports.map(p =>
        `<div style="padding: 4px 0; font-family: var(--font-mono);">${escHtml(p)}</div>`
      ).join('');
    }
    refreshPortSelect(data.ports);
  } catch (e) {
    console.error('Ports refresh failed:', e);
  }
}

async function refreshPortSelect(ports) {
  if (!ports) {
    try {
      const data = await api('/api/machine/ports');
      ports = data.ports;
    } catch { ports = []; }
  }
  const select = document.getElementById('portSelect');
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="">Dry Run (no port)</option>';
  ports.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = p;
    select.appendChild(opt);
  });
  if (current) select.value = current;
}

function updateMachineIndicator(state) {
  const dot = document.getElementById('statusDot');
  const text = document.getElementById('statusText');
  dot.className = `status-dot ${state}`;
  text.textContent = capitalize(state);
}

// ── WebSocket ──
function setupWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${protocol}//${location.host}/ws/status`);

  ws.onopen = () => console.log('WebSocket connected');

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleWSMessage(data);
  };

  ws.onclose = () => {
    console.log('WebSocket closed, reconnecting in 3s...');
    setTimeout(setupWebSocket, 3000);
  };

  ws.onerror = () => ws.close();

  // Ping every 30s
  setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send('ping');
    }
  }, 30000);
}

function handleWSMessage(data) {
  switch (data.type) {
    case 'job_created':
      toast('New job created', 'success');
      if (currentPage === 'jobs') loadJobs();
      if (currentPage === 'dashboard') loadDashboard();
      break;

    case 'job_deleted':
      if (currentPage === 'jobs') loadJobs();
      if (currentPage === 'dashboard') loadDashboard();
      break;

    case 'plot_progress':
      plotSent = data.sent;
      plotTotal = data.total || plotTotal;
      if (plotTotal > 0) {
        const pct = Math.min(100, (plotSent / plotTotal) * 100);
        document.getElementById('plotProgressFill').style.width = `${pct}%`;
      }
      document.getElementById('plotInfo').textContent =
        `${plotSent}${plotTotal ? '/' + plotTotal : ''} commands sent`;
      updateMachineIndicator('plotting');
      break;

    case 'plot_complete':
      toast(`Plot complete: ${data.commands_sent} commands${data.dry_run ? ' (dry run)' : ''}`, 'success');
      resetPlotUI();
      document.getElementById('plotProgressFill').style.width = '100%';
      document.getElementById('plotProgressBar').classList.remove('hidden');
      updateMachineIndicator('idle');
      if (currentJobId === data.job_id) loadJobDetail(data.job_id);
      break;

    case 'plot_error':
      toast(`Plot error: ${data.error}`, 'error');
      resetPlotUI();
      updateMachineIndicator('error');
      break;

    case 'plot_cancelled':
      toast('Plot cancelled', 'info');
      resetPlotUI();
      updateMachineIndicator('idle');
      break;

    case 'pong':
      break;

    default:
      console.log('Unknown WS message:', data);
  }
}

// ── API Helpers ──
async function api(url, opts = {}) {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `HTTP ${resp.status}`);
  }
  return resp.json();
}

// ── Utilities ──
function escHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return '—';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function toast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);

  setTimeout(() => {
    el.classList.add('toast-exit');
    setTimeout(() => el.remove(), 300);
  }, 4000);
}
