(() => {
  const apiKey = sessionStorage.getItem('sentinel_api_key');
  if (!apiKey) {
    window.location.replace('/login');
    return;
  }

  const content = document.getElementById('page-content');
  const modalRoot = document.getElementById('modal-root');
  const route = window.location.pathname.split('/')[1] || 'dashboard';
  const detailId = route === 'cameras' ? decodeURIComponent(window.location.pathname.split('/')[2] || '') : '';
  const frameBusy = new Set();
  const objectUrls = new Set();
  const timers = new Set();
  let selectedUpload = null;
  let resultLoadVersion = 0;
  const ruleLabels = {
    intrusion: 'Restricted-area entry', loitering: 'Loitering', wall_climbing: 'Suspected climbing',
    door_tampering: 'Door-handle activity', pool_safety: 'Pool danger zone', crowd: 'Crowd threshold',
    illegal_parking: 'Suspected illegal parking', unattended_object: 'Unattended bag',
  };

  const pageMeta = {
    dashboard: ['Operations', 'Dashboard'],
    cameras: ['Monitoring', 'Cameras'],
    robots: ['Automation', 'Robots'],
    map: ['Township', 'Residential map'],
    settings: ['Administration', 'Analysis settings'],
    alerts: ['Visual analysis', 'Review findings'],
    'algorithm-test': ['Testing lab', 'Algorithm test'],
  };

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'}[character]));
  }

  function icon(name) {
    const paths = {
      camera: '<rect x="3" y="6" width="14" height="12" rx="2"/><path d="m17 10 4-2v8l-4-2"/>',
      alert: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
      person: '<circle cx="12" cy="7" r="3"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/>',
      flask: '<path d="M9 3h6M10 3v5l-5.5 9.5A2.3 2.3 0 0 0 6.5 21h11a2.3 2.3 0 0 0 2-3.5L14 8V3M7 15h10"/>',
      plus: '<path d="M12 5v14M5 12h14"/>',
      settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
      trash: '<path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"/>',
      upload: '<path d="M12 16V4M7 9l5-5 5 5M5 20h14"/>',
      robot: '<rect x="4" y="7" width="16" height="12" rx="3"/><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8"/>',
      map: '<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6ZM9 3v15M15 6v15"/>',
    };
    return `<svg viewBox="0 0 24 24">${paths[name] || ''}</svg>`;
  }

  async function request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {'X-API-Key': apiKey, ...(options.headers || {})},
    });
    if (response.status === 401) {
      sessionStorage.removeItem('sentinel_api_key');
      window.location.replace('/login');
      throw new Error('Session expired');
    }
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try { message = (await response.json()).detail || message; } catch (_) { /* no JSON body */ }
      throw new Error(message);
    }
    return response;
  }

  async function api(path, options = {}) {
    const settings = {...options};
    if (settings.json !== undefined) {
      settings.body = JSON.stringify(settings.json);
      settings.headers = {'Content-Type': 'application/json', ...(settings.headers || {})};
      delete settings.json;
    }
    const response = await request(path, settings);
    return response.status === 204 ? null : response.json();
  }

  function toast(message, type = '') {
    const element = document.createElement('div');
    element.className = `toast ${type}`;
    element.textContent = message;
    document.getElementById('toast-region').append(element);
    window.setTimeout(() => element.remove(), 3800);
  }

  function formatTime(value) {
    if (!value) return '—';
    return new Intl.DateTimeFormat(undefined, {dateStyle: 'medium', timeStyle: 'short'}).format(new Date(value));
  }

  function titleCase(value) {
    return String(value || '').replaceAll('_', ' ').replace(/\b\w/g, character => character.toUpperCase());
  }

  function statePill(value) {
    const state = value || 'stopped';
    return `<span class="state-pill ${escapeHtml(state)}">${state === 'running' ? '<span class="status-dot"></span>' : ''}${escapeHtml(titleCase(state))}</span>`;
  }

  function addTimer(callback, milliseconds) {
    const timer = window.setInterval(callback, milliseconds);
    timers.add(timer);
    return timer;
  }

  function clearTimers() {
    for (const timer of timers) window.clearInterval(timer);
    timers.clear();
  }

  function rememberUrl(blob) {
    const url = URL.createObjectURL(blob);
    objectUrls.add(url);
    return url;
  }

  function closeModal() { modalRoot.replaceChildren(); }

  function showModal(markup) {
    modalRoot.innerHTML = `<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true">${markup}</section></div>`;
    modalRoot.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', closeModal));
    modalRoot.querySelector('.modal-backdrop').addEventListener('click', event => {
      if (event.target.classList.contains('modal-backdrop')) closeModal();
    });
  }

  async function loadGlobalCounts() {
    try {
      const summary = await api('/api/v1/summary');
      document.getElementById('camera-nav-count').textContent = summary.camera_count;
      document.getElementById('alert-nav-count').textContent = summary.finding_count || '';
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  function metric(label, value, caption, iconName, color, wash) {
    return `<article class="metric-card" style="--metric-color:${color};--metric-wash:${wash}">
      <div class="metric-top"><span>${escapeHtml(label)}</span><span class="metric-icon">${icon(iconName)}</span></div>
      <div class="metric-value">${escapeHtml(value)}</div><div class="metric-caption">${escapeHtml(caption)}</div>
    </article>`;
  }

  async function getCameraStates(cameras) {
    return Promise.all(cameras.map(async camera => {
      try { return {...camera, status: await api(`/api/v1/cameras/${encodeURIComponent(camera.id)}/status`)}; }
      catch (_) { return {...camera, status: {state: 'error', person_count: 0, vehicle_count: 0}}; }
    }));
  }

  async function renderDashboard() {
    const [summary, cameras, events] = await Promise.all([
      api('/api/v1/summary'), api('/api/v1/cameras'), api('/api/v1/findings'),
    ]);
    const withStates = await getCameraStates(cameras);
    content.innerHTML = `
      <div class="section-head"><div><h2>Good day, Operator</h2><p>Here is the current township operations overview.</p></div><div class="head-actions"><a class="button button-secondary" href="/algorithm-test">${icon('flask')} Run media test</a><a class="button button-primary" href="/cameras">${icon('camera')} Manage cameras</a></div></div>
      <section class="metric-grid">
        ${metric('Cameras online', `${summary.online_count} / ${summary.camera_count}`, 'Configured monitoring sources', 'camera', '#12a886', '#e7f7f3')}
        ${metric('Review findings', summary.finding_count, 'Saved visual descriptions', 'alert', '#d94c5c', '#fff0f2')}
        ${metric('Analysis model', 'SmolVLM2', 'Local video understanding', 'person', '#3976e8', '#edf3ff')}
        ${metric('Media tests', summary.algorithm_test_count, 'Saved local test runs', 'flask', '#9a6ad9', '#f4effb')}
      </section>
      <section class="content-grid">
        <article class="panel"><div class="panel-head"><div><h3>Camera network</h3><p>Live state across configured sources</p></div><a class="link-button" href="/cameras">View all →</a></div><div class="panel-body camera-list">
          ${withStates.length ? withStates.map(camera => `<div class="camera-row"><span class="camera-thumb">${icon('camera')}</span><span><strong>${escapeHtml(camera.name)}</strong><small>${escapeHtml(camera.source_label)} · SmolVLM2 analysis</small></span>${statePill(camera.status.state)}</div>`).join('') : '<div class="empty-state"><p>No cameras configured yet.</p><a class="button button-primary" href="/cameras">Add camera</a></div>'}
        </div></article>
        <article class="panel"><div class="panel-head"><div><h3>Recent findings</h3><p>Visual descriptions requiring review</p></div><a class="link-button" href="/alerts">Review all →</a></div><div class="panel-body alert-list">
          ${events.length ? events.slice(0, 6).map(event => `<div class="alert-item"><span class="alert-dot"></span><div><strong>${escapeHtml('Visual analysis')}</strong><p>${escapeHtml(event.description)}</p><time>${escapeHtml(event.camera_id)} · ${formatTime(event.observed_at)}</time></div></div>`).join('') : '<div class="empty-state"><p>No visual findings have been recorded.</p></div>'}
        </div></article>
      </section>`;
  }

  function cameraCard(camera) {
    return `<article class="camera-card"><div class="camera-card-body">
      <h3>${escapeHtml(camera.name)}</h3><p>${escapeHtml(camera.source_label)} · SmolVLM2 analysis</p>
      ${statePill(camera.status.state)} <a class="button button-primary" href="/cameras/${encodeURIComponent(camera.id)}">Open camera →</a>
    </div></article>`;
  }

  function detailCard(camera) {
    const running = ['running', 'starting', 'error'].includes(camera.status.state);
    return `<article class="camera-card" data-camera-card="${escapeHtml(camera.id)}">
      <div class="camera-visual"><span class="camera-placeholder">${icon('camera')}</span><img alt="Live view from ${escapeHtml(camera.name)}" hidden><span class="visual-state">${statePill(camera.status.state)}</span></div>
      <div class="camera-card-body"><div class="camera-title-row"><div><h3>${escapeHtml(camera.name)}</h3><p>${escapeHtml(camera.id)} · ${escapeHtml(camera.source_label)}</p></div><div class="card-menu"><button class="icon-button" data-edit-camera="${escapeHtml(camera.id)}" aria-label="Edit camera">${icon('settings')}</button><button class="icon-button" data-delete-camera="${escapeHtml(camera.id)}" aria-label="Delete camera">${icon('trash')}</button></div></div>
      <div class="camera-meta"><div><span>Model</span><strong>SmolVLM2</strong></div><div><span>Output</span><strong>Review findings</strong></div></div>
      <div class="card-actions"><button class="button ${running ? 'button-secondary' : 'button-primary'}" data-camera-action="${running ? 'stop' : 'start'}" data-camera-id="${escapeHtml(camera.id)}" ${camera.source_type === 'synthetic' ? 'disabled title="Synthetic cameras receive API observations"' : ''}>${running ? 'Stop camera' : camera.source_type === 'synthetic' ? 'Virtual input' : 'Start camera'}</button></div></div>
    </article>`;
  }

  async function loadCameraFrame(cameraId) {
    const card = content.querySelector(`[data-camera-card="${CSS.escape(cameraId)}"]`);
    if (!card || frameBusy.has(cameraId) || document.hidden) return;
    frameBusy.add(cameraId);
    try {
      const response = await request(`/api/v1/cameras/${encodeURIComponent(cameraId)}/snapshot`, {signal: AbortSignal.timeout(4000)});
      const image = card.querySelector('img');
      if (!card.isConnected) return;
      const oldUrl = image.dataset.url;
      const url = rememberUrl(await response.blob());
      image.src = url; image.hidden = false; image.dataset.url = url;
      image.onload = () => { card.querySelector('.camera-visual').style.aspectRatio = image.naturalWidth + ' / ' + image.naturalHeight; };
      card.querySelector('.camera-placeholder').hidden = true;
      if (oldUrl) { URL.revokeObjectURL(oldUrl); objectUrls.delete(oldUrl); }
    } catch (_) { /* Status polling reports unavailable or disconnected cameras. */ }
    finally { frameBusy.delete(cameraId); }
  }

  async function renderCameras() {
    if (detailId) return renderCameraDetail();
    clearTimers();
    const cameras = await api('/api/v1/cameras');
    const withStates = await getCameraStates(cameras);
    content.innerHTML = `<div class="section-head"><div><h2>Camera management</h2><p>Create sources and review local video analysis.</p></div><button id="add-camera" class="button button-primary">${icon('plus')} Add camera</button></div>
      <section class="camera-grid">${withStates.length ? withStates.map(cameraCard).join('') : `<article class="panel empty-state"><span class="empty-icon">${icon('camera')}</span><h3>No cameras configured</h3><p>Add a webcam, local video, RTSP source, or synthetic input to begin.</p><button class="button button-primary" id="empty-add-camera">Add first camera</button></article>`}</section>`;

    content.querySelector('#add-camera')?.addEventListener('click', () => openCameraModal());
    content.querySelector('#empty-add-camera')?.addEventListener('click', () => openCameraModal());
  }

  async function renderCameraDetail() {
    clearTimers();
    const base = `/api/v1/cameras/${encodeURIComponent(detailId)}`;
    const camera = await api(base);
    camera.status = await api(base + '/status');
    document.getElementById('page-title').textContent = camera.name;
    document.title = `${camera.name} · Township Sentinel`;
    content.innerHTML = `<div class="section-head"><div><a href="/cameras">← All cameras</a>
      <h2>${escapeHtml(camera.name)}</h2><p>Live view and timestamped visual analysis.</p></div></div>
      <div class="camera-detail">${detailCard(camera)}</div>
      <p id="camera-health" role="status"></p>
      <section class="panel"><div class="panel-head"><h3>Visual analysis</h3><p>Sampled descriptions require human review.</p></div>
      <div id="behavior-grid" class="behavior-grid"></div></section>
      <section class="panel camera-alerts"><div class="panel-head"><h3>Camera findings</h3></div>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Time</th><th>Window</th><th>Frames</th><th>Description</th></tr></thead><tbody id="camera-alert-rows"></tbody></table></div></section>`;
    let state = camera.status;
    let polling = false;
    const mounted = content.querySelector('.camera-detail');
    async function refresh() {
      if (polling || !mounted.isConnected) return;
      polling = true;
      try {
        const [nextState, events, tracks] = await Promise.all([
          api(base + '/status'), api('/api/v1/findings?camera_id=' + encodeURIComponent(detailId)), api(base + '/tracks')
        ]);
        if (!mounted.isConnected) return;
        state = nextState;
        const fresh = state.last_frame_at && Date.now() - Date.parse(state.last_frame_at) < 4000;
        const live = state.state === 'running' && fresh;
        content.querySelector('.visual-state').innerHTML = statePill(live ? 'running' : state.state === 'running' ? 'stale' : state.state);
        content.querySelector('#camera-health').textContent = state.error || (live ? 'Live preview · up to 5 FPS' : state.state === 'starting' ? 'Connecting to camera…' : 'Camera ' + state.state);
        const action = content.querySelector('[data-camera-action]');
        action.dataset.cameraAction = ['running', 'starting', 'error'].includes(state.state) ? 'stop' : 'start';
        action.textContent = camera.source_type === 'synthetic' ? 'Virtual input' : action.dataset.cameraAction === 'stop' ? 'Stop camera' : 'Start camera';
        content.querySelector('#behavior-grid').innerHTML = `<article class="behavior-tile"><strong>${escapeHtml(state.analysis_state || 'Waiting for frames')}</strong><span>${escapeHtml(state.analysis_error || 'Sampling uses the settings active when this camera started. Findings require review; automatic alerts are disabled.')}</span></article>`;
        content.querySelector('#camera-alert-rows').innerHTML = events.length ? events.map(item => `<tr><td>${formatTime(item.observed_at)}</td><td>${Number(item.start_seconds).toFixed(1)}–${Number(item.end_seconds).toFixed(1)}s</td><td>${Number(item.frames_analyzed)}</td><td>${escapeHtml(item.description)}</td></tr>`).join('') : '<tr><td colspan="4">Waiting for the first analysis result.</td></tr>';
        if (!live) { content.querySelector('.camera-visual img').hidden = true; content.querySelector('.camera-placeholder').hidden = false; }
      } catch (error) {
        if (mounted.isConnected) {
          content.querySelector('#camera-health').textContent = 'Connection lost: ' + error.message;
          state = {state: 'unavailable'};
          content.querySelector('.camera-visual img').hidden = true;
          content.querySelector('.visual-state').innerHTML = statePill('unavailable');
          content.querySelector('.track-overlay')?.replaceChildren();
          content.querySelectorAll('.signal-active').forEach(tile => tile.classList.remove('signal-active'));
        }
      } finally { polling = false; }
    }
    await refresh();
    addTimer(refresh, 1000);
    addTimer(() => {
      if (state.state === 'running' && Date.now() - Date.parse(state.last_frame_at) < 4000) loadCameraFrame(detailId);
    }, 200);
  }

  async function cameraClickHandler(event) {
    const action = event.target.closest('[data-camera-action]');
    const edit = event.target.closest('[data-edit-camera]');
    const remove = event.target.closest('[data-delete-camera]');
    try {
      if (action) {
        action.disabled = true;
        const operation = action.dataset.cameraAction;
        await api(`/api/v1/cameras/${encodeURIComponent(action.dataset.cameraId)}/${operation}`, {method: 'POST'});
        toast(`Camera ${operation === 'start' ? 'start requested' : 'stopped'}.`);
        await renderCameras();
        return;
      }
      if (edit) {
        const cameras = await api('/api/v1/cameras');
        openCameraModal(cameras.find(camera => camera.id === edit.dataset.editCamera));
      } else if (remove) {
        if (window.confirm('Delete this camera and its zone configuration? Existing alerts will be retained.')) {
          await api(`/api/v1/cameras/${encodeURIComponent(remove.dataset.deleteCamera)}`, {method: 'DELETE'});
          toast('Camera deleted.'); window.location.assign('/cameras');
        }

      }
    } catch (error) { toast(error.message, 'error'); }
    finally { if (action?.isConnected) action.disabled = false; }
  }

  function parseSource(value) {
    const trimmed = value.trim();
    return /^\d+$/.test(trimmed) ? Number(trimmed) : trimmed;
  }

  function openCameraModal(camera = null) {
    const editing = Boolean(camera);
    showModal(`<div class="modal-head"><h2>${editing ? 'Edit camera' : 'Add camera'}</h2><button class="icon-button" data-close-modal aria-label="Close">×</button></div>
      <form id="camera-form"><div class="modal-body form-grid">
        <div class="form-field"><label for="camera-id">Camera ID</label><input class="input" id="camera-id" value="${escapeHtml(camera?.id || '')}" placeholder="north-gate" pattern="[a-zA-Z0-9](?:[a-zA-Z0-9_]|-)*" ${editing ? 'disabled' : ''} required><small>Stable letters, numbers, dashes, or underscores.</small></div>
        <div class="form-field"><label for="camera-name">Display name</label><input class="input" id="camera-name" value="${escapeHtml(camera?.name || '')}" placeholder="North gate" required></div>
        <div class="form-field"><label for="camera-x">Map X (−80 to 80)</label><input class="input" type="number" step="any" min="-80" max="80" id="camera-x" value="${camera?.map_position?.x ?? ''}"></div>
        <div class="form-field"><label for="camera-y">Map Y (−55 to 55)</label><input class="input" type="number" step="any" min="-55" max="55" id="camera-y" value="${camera?.map_position?.y ?? ''}"></div>
        <small class="full">Optional: center (0, 0), +X right/east, +Y up/north. Plan units, not metres or GPS. Leave both blank to remove placement.</small>
        <div class="form-field full"><label for="camera-source">Video source</label><input class="input" id="camera-source" placeholder="0, video file path, RTSP URL, or synthetic" ${editing ? '' : 'required'}><small>${editing ? `Current: ${escapeHtml(camera.source_label)}. Leave blank to keep it.` : 'Use 0 for the first webcam. Credentials in RTSP URLs are kept only in local configuration.'}</small></div>
      </div><div class="modal-actions"><button type="button" class="button button-secondary" data-close-modal>Cancel</button><button class="button button-primary" type="submit">${editing ? 'Save changes' : 'Add camera'}</button></div></form>`);
    const form = modalRoot.querySelector('#camera-form');
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const sourceValue = form.querySelector('#camera-source').value;
      const body = {name: form.querySelector('#camera-name').value.trim()};
      const x=form.querySelector('#camera-x').value,y=form.querySelector('#camera-y').value;
      if((x==='')!==(y==='')){toast('Enter both X and Y, or leave both blank.', 'error');return;}
      body.map_position=x===''?null:{x:Number(x),y:Number(y)};
      if (sourceValue.trim()) body.source = parseSource(sourceValue);
      if (!editing) { body.id = form.querySelector('#camera-id').value.trim(); body.source = parseSource(sourceValue); }
      const submit = form.querySelector('[type="submit"]'); submit.disabled = true;
      try {
        await api(editing ? `/api/v1/cameras/${encodeURIComponent(camera.id)}` : '/api/v1/cameras', {method: editing ? 'PUT' : 'POST', json: body});
        closeModal(); toast(editing ? 'Camera updated.' : 'Camera added.'); await loadGlobalCounts(); await renderCameras();
      } catch (error) { toast(error.message, 'error'); submit.disabled = false; }
    });
  }

  async function renderAlerts() {
    const [findings, cameras] = await Promise.all([api('/api/v1/findings'), api('/api/v1/cameras')]);
    const names = Object.fromEntries(cameras.map(camera => [camera.id, camera.name]));
    content.innerHTML = `<div class="section-head"><div><h2>Visual review</h2><p>SmolVLM2 descriptions from sampled camera frames. Review the source before acting.</p></div></div>
      <article class="panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Observed</th><th>Camera</th><th>Sample window</th><th>Description</th></tr></thead><tbody>${findings.length ? findings.map(item => `<tr><td>${formatTime(item.observed_at)}</td><td>${escapeHtml(names[item.camera_id] || item.camera_id)}</td><td>${Number(item.start_seconds).toFixed(1)}–${Number(item.end_seconds).toFixed(1)}s</td><td>${escapeHtml(item.description)}</td></tr>`).join('') : '<tr><td colspan="4">No visual findings yet. Start a camera to analyze its sampled frames.</td></tr>'}</tbody></table></div></article>`;
  }

  async function renderMap() {
    const cameras = await api('/api/v1/cameras');
    content.innerHTML = `<div class="section-head map-page-head"><div><h2>Residential digital twin</h2><p>Interactive 3D site model based on the supplied residential plan.</p></div><span class="state-pill running"><span class="status-dot"></span> Interactive model</span></div>
      <section class="map-grid">
        <div class="map-stage panel">
          <canvas id="residential-map-canvas" tabindex="0" aria-label="Interactive three-dimensional residential site map. Drag to orbit, scroll to zoom, and select a building or amenity.">Your browser does not support the interactive map canvas.</canvas>
          <div class="map-brand"><span class="map-brand-mark">TS</span><span><strong>Township Sentinel</strong><small>Residential digital twin</small></span></div>
          <div class="map-controls" aria-label="Map controls">
            <button class="map-control" type="button" data-map-action="zoom-in" aria-label="Zoom in">+</button>
            <button class="map-control" type="button" data-map-action="zoom-out" aria-label="Zoom out">−</button>
            <button class="map-control map-control-wide" type="button" data-map-action="reset">Reset view</button>
            <button class="map-control map-control-wide active" type="button" data-map-action="cameras" aria-pressed="true">Camera pins</button>
          </div>
          <div class="map-hint"><span>Drag to orbit</span><span>Scroll to zoom</span><span>Click an asset</span></div>
        </div>
        <aside class="map-side-panel">
          <article class="panel"><div class="panel-body"><h3>Plan coordinates</h3><p>Center (0, 0) · X: −80…80 · Y: −55…55<br>+X right/east · +Y up/north. Plan units, not GPS.</p><a href="/cameras" class="link-button">Set camera coordinates →</a><p><button class="button button-secondary" data-map-feature="patrol-robot">Locate simulated patrol robot</button></p></div></article>
          <article class="panel map-inspector" aria-live="polite">
            <div class="map-inspector-hero"><span id="map-inspector-icon">⌂</span><span class="state-pill" id="map-inspector-state">Site overview</span></div>
            <div class="panel-body"><span class="eyebrow" id="map-inspector-type">Master plan</span><h3 id="map-inspector-title">Sentinel Residences</h3><p id="map-inspector-description">Select any building or amenity to inspect it. The model follows the layout of the supplied plan and works without an external map service.</p><dl class="map-inspector-facts" id="map-inspector-facts"><div><dt>Homes</dt><dd>4</dd></div><div><dt>Amenities</dt><dd>3</dd></div><div><dt>Cameras</dt><dd>${cameras.length}</dd></div></dl></div>
          </article>
          <article class="panel map-directory"><div class="panel-head"><div><h3>Site directory</h3><p>Select a place to focus the model</p></div></div><div class="map-directory-list">
            ${[
              ['house-1', 'House 1', 'Residence'], ['house-2', 'House 2', 'Residence'],
              ['house-3', 'House 3', 'Residence'], ['house-4', 'House 4', 'Residence'],
              ['clubhouse', 'Clubhouse', 'Community'], ['pool', 'Swimming pool', 'Amenity'],
              ['garden', 'Garden', 'Amenity'], ['guardhouse', 'Guardhouse', 'Security'],
            ].map(([id, name, type]) => `<button type="button" class="map-directory-item" data-map-feature="${id}"><span class="map-directory-dot ${id}"></span><span><strong>${name}</strong><small>${type}</small></span><span aria-hidden="true">→</span></button>`).join('')}
          </div></article>
          <article class="panel map-camera-panel"><div class="panel-head"><div><h3>Camera positions</h3><p>${cameras.filter(c=>c.map_position).length} placed / ${cameras.length} configured</p></div></div><div class="map-directory-list">${cameras.length ? cameras.map(camera => `<button type="button" class="map-directory-item" ${camera.map_position ? `data-map-feature="camera-${escapeHtml(camera.id)}"` : 'disabled'}><span class="map-camera-dot"></span><span><strong>${escapeHtml(camera.name)}</strong><small>${camera.map_position ? `(${camera.map_position.x}, ${camera.map_position.y})` : 'Not placed — edit camera to set coordinates'}</small></span><span aria-hidden="true">→</span></button>`).join('') : '<div class="map-empty-cameras"><p>No cameras configured yet.</p><a class="button button-secondary" href="/cameras">Add a camera</a></div>'}</div></article>
        </aside>
      </section>`;

    if (!window.SentinelResidentialMap) throw new Error('Residential map renderer is unavailable');
    await window.SentinelResidentialMap.mount(content.querySelector('#residential-map-canvas'), {
      cameras,
      root: content,
      onSelect(feature) {
        content.querySelectorAll('[data-map-feature]').forEach(item => item.classList.toggle('active', item.dataset.mapFeature === feature.id));
        content.querySelector('#map-inspector-icon').textContent = feature.icon;
        content.querySelector('#map-inspector-type').textContent = feature.type;
        content.querySelector('#map-inspector-title').textContent = feature.label;
        content.querySelector('#map-inspector-description').textContent = feature.description;
        content.querySelector('#map-inspector-state').textContent = feature.state;
        content.querySelector('#map-inspector-facts').innerHTML = feature.facts.map(item => `<div><dt>${escapeHtml(item[0])}</dt><dd>${escapeHtml(item[1])}</dd></div>`).join('');
      },
    });
  }

  function renderRobots() {
    content.innerHTML = `<div class="section-head"><div><h2>Robot operations</h2><p>Virtual-first patrol demonstration.</p></div><span class="state-pill">Simulation only</span></div><article class="panel empty-state"><span class="empty-icon">${icon('robot')}</span><h3>Residential patrol robot</h3><p>A simulated robot continuously follows the perimeter road while the map is open. No physical robot is connected or controlled.</p><a class="button button-primary" href="/map">View patrol on map</a></article>`;
  }

  async function renderSettings() {
    content.innerHTML=`<article class="panel"><div class="panel-head"><div><h2>Analysis settings</h2><p>Administrator access. Changes are saved locally.</p></div></div><div class="panel-body"><form id="settings-unlock" class="form-grid"><div class="form-field full"><label for="admin-key">Admin key (if separately configured)</label><input class="input" id="admin-key" type="password" autocomplete="off"><small>Without SENTINEL_ADMIN_API_KEY, the signed-in API key has owner access.</small></div><button class="button button-secondary">Load settings</button></form><div id="settings-editor"></div></div></article>`;
    const unlock=content.querySelector('#settings-unlock');
    async function load(event){
      event?.preventDefault();
      const headers={'X-Admin-Key':content.querySelector('#admin-key').value || apiKey};
      try{
        const value=await api('/api/v1/settings',{headers});
        const editor=content.querySelector('#settings-editor');
        editor.innerHTML=`<form id="analysis-settings" class="form-grid"><p class="full">Prompt and output limit apply to the next model call. Sampling, window size and preview rate apply when cameras or media jobs start. Restart running cameras to use new rates. Sampling FPS is not model calls per second; live windows may be skipped when the model is busy.</p><div class="form-field full"><label for="analysis-prompt">VLM prompt</label><textarea class="input" id="analysis-prompt" name="prompt" rows="8" maxlength="4000" required>${escapeHtml(value.prompt)}</textarea><small>Describe observable evidence and uncertainty. Outputs still require human review.</small></div>${[
          ['sample_fps','Sampled frames per second',.25,10,.25],['window_frames','Frames per analysis window',1,8,1],
          ['max_new_tokens','Maximum output tokens',16,256,1],['preview_fps','Preview frames per second',1,15,1]
        ].map(([name,label,min,max,step])=>`<div class="form-field"><label for="setting-${name}">${label}</label><input class="input" id="setting-${name}" name="${name}" type="number" min="${min}" max="${max}" step="${step}" value="${value[name]}" required></div>`).join('')}<div class="full"><button class="button button-primary" type="submit">Save settings</button><span id="settings-status" role="status"></span></div></form>`;
        editor.querySelector('form').addEventListener('submit',async event=>{
          event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');
          const body=Object.fromEntries(new FormData(form));
          for(const name of ['sample_fps','window_frames','max_new_tokens','preview_fps'])body[name]=Number(body[name]);
          button.disabled=true;
          try{await api('/api/v1/settings',{method:'PUT',headers,json:body});content.querySelector('#settings-status').textContent=' Saved. Restart running cameras to apply sampling changes.';toast('Settings saved.');}
          catch(error){toast(error.message,'error');}finally{button.disabled=false;}
        });
      }catch(error){content.querySelector('#settings-editor').replaceChildren();toast(error.message,'error');}
    }
    unlock.addEventListener('submit',load);await load();
  }

  function algorithmHistoryMarkup(tests) {
    return tests.length ? tests.map(test => `<article class="test-card"><div><h4>${escapeHtml(test.filename)}</h4><p>${formatTime(test.created_at)} · ${test.frames_processed || 0} frames · ${test.findings?.length || 0} findings</p><p>${escapeHtml(test.camera_name || 'Visual analysis')}</p></div><div>${test.state === 'completed' ? `<button class="button button-secondary" data-test-result="${escapeHtml(test.id)}" data-result-type="${escapeHtml(test.output_media_type)}">View result</button>` : statePill(test.state)}${test.error ? `<p class="form-error">${escapeHtml(test.error)}</p>` : ''}</div></article>`).join('') : '<div class="empty-state"><p>No media tests have been run.</p></div>';
  }

  async function loadAlgorithmResult(id, mediaType) {
    const viewer = content.querySelector('#result-viewer');
    const version = ++resultLoadVersion;
    viewer.innerHTML = '<span class="spinner"></span>';
    content.querySelector('#test-timeline').innerHTML = '';
    try {
      const [response, metadata] = await Promise.all([request(`/api/v1/algorithm-tests/${encodeURIComponent(id)}/result`), api(`/api/v1/algorithm-tests/${encodeURIComponent(id)}`)]);
      if (version !== resultLoadVersion) return;
      const url = rememberUrl(await response.blob());
      if (version !== resultLoadVersion) { URL.revokeObjectURL(url); objectUrls.delete(url); return; }
      const previous = viewer.dataset.url;
      viewer.dataset.url = url;
      if (previous) { URL.revokeObjectURL(previous); objectUrls.delete(previous); }
      viewer.innerHTML = response.headers.get('Content-Type')?.startsWith('video') ? `<video src="${url}" controls autoplay muted playsinline></video>` : `<img src="${url}" alt="Annotated algorithm test result">`;
      viewer.querySelector('video')?.addEventListener('error', () => toast('Video could not decode. Run the test again to generate a new WebM result.', 'error'));
        if (metadata.mode === 'visual_analysis') {
          const findings = metadata.findings || [];
          const timeline = content.querySelector('#test-timeline');
          timeline.innerHTML = `<div class="panel-head"><h3>Analysis timeline</h3><p>Descriptions require review</p></div><div class="panel-body">${(metadata.warnings || []).map(item => `<p>${escapeHtml(item)}</p>`).join('')}${findings.map(item => `<article class="test-card"><div><button class="button button-ghost" data-seek="${Number(item.start_seconds)}">${Number(item.start_seconds).toFixed(1)}–${Number(item.end_seconds).toFixed(1)}s</button><p>${escapeHtml(item.description)}</p><small>${Number(item.frames_analyzed)} sampled frames</small></div></article>`).join('')}</div>`;
          const video = viewer.querySelector('video');
          timeline.querySelectorAll('[data-seek]').forEach(button => {
            button.disabled = !video;
            button.addEventListener('click', () => { video.currentTime = Number(button.dataset.seek); });
          });
          return;
        }
      const events = metadata.events || [];
      const timeline = content.querySelector('#test-timeline');
      timeline.innerHTML = `<div class="panel-head"><div><h3>Test alert timeline</h3><p>Isolated from live alerts · ${escapeHtml(metadata.camera_name || 'Visual analysis')}</p></div></div>
        <div class="panel-body">${(metadata.warnings || []).map(warning => `<p class="zone-help">${escapeHtml(warning)}</p>`).join('')}
        ${metadata.events_truncated ? '<p>Showing the first 1,000 test alerts.</p>' : ''}
        <div class="behavior-grid">${Object.entries(ruleLabels).filter(([rule]) => (metadata.zones || []).some(zone => zone.rule === rule)).map(([rule, label]) => `<article class="behavior-tile" data-replay-rule="${rule}"><strong>${escapeHtml(label)}</strong><span>Test signal</span></article>`).join('')}</div></div>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>Video time</th><th>Rule</th><th>Zone</th><th>Message</th></tr></thead><tbody>${events.length ? events.map(event => `<tr><td><button class="button button-ghost" data-seek="${Number(event.offset_seconds)}">${Number(event.offset_seconds).toFixed(1)}s</button></td><td>${escapeHtml(ruleLabels[event.rule] || event.rule)}</td><td>${escapeHtml(event.zone_id)}</td><td>${escapeHtml(event.message)}</td></tr>`).join('') : '<tr><td colspan="4">No test alerts. This does not establish that a scene is safe.</td></tr>'}</tbody></table></div>`;
      const video = viewer.querySelector('video');
      const highlight = () => {
        const at = video ? video.currentTime : 0;
        timeline.querySelectorAll('[data-replay-rule]').forEach(tile => tile.classList.toggle('signal-active', events.some(event => event.rule === tile.dataset.replayRule && at >= event.offset_seconds && at - event.offset_seconds <= 3)));
      };
      timeline.querySelectorAll('[data-seek]').forEach(button => {
        button.disabled = !video;
        button.addEventListener('click', () => { video.currentTime = Number(button.dataset.seek); highlight(); });
      });
      video?.addEventListener('timeupdate', highlight); highlight();
    } catch (error) { if (version === resultLoadVersion) viewer.innerHTML = `<p>${escapeHtml(error.message)}</p>`; }
  }

  async function refreshAlgorithmHistory() {
    const tests = await api('/api/v1/algorithm-tests');
    const history = content.querySelector('#test-history');
    if (!history) return tests;
    history.innerHTML = algorithmHistoryMarkup(tests);
    history.querySelectorAll('[data-test-result]').forEach(button => button.addEventListener('click', () => loadAlgorithmResult(button.dataset.testResult, button.dataset.resultType)));
    return tests;
  }

  async function renderAlgorithmTest() {
    const [tests, cameras, capabilities] = await Promise.all([api('/api/v1/algorithm-tests'), api('/api/v1/cameras'), api('/api/v1/capabilities')]);
    content.innerHTML = `<div class="section-head"><div><h2>Algorithm test lab</h2><p>Analyze images and recorded video with the same local SmolVLM2 model used by cameras.</p></div><span class="state-pill">Images + videos</span></div><section class="test-layout"><div><div id="upload-zone" class="upload-zone"><span class="upload-icon">${icon('upload')}</span><h3>Drop a picture or video here</h3><p>JPG, PNG, WEBP, MP4, MOV, AVI, or MKV. Videos are bounded to the first 60 seconds.</p><input id="media-file" type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/x-msvideo,video/x-matroska" hidden><button id="choose-file" class="button button-secondary">Choose media</button><div id="selected-file" class="selected-file"></div></div><button id="run-test" class="button button-primary" style="width:100%;margin-top:12px" disabled>Run algorithm test</button></div><article class="panel"><div class="panel-head"><div><h3>Result viewer</h3><p>Source playback with an analysis timeline</p></div></div><div class="panel-body"><div id="result-viewer" class="result-viewer"><p>Select a completed test to inspect its output.</p></div></div></article></section><article class="panel" style="margin-top:20px"><div class="panel-head"><div><h3>Test history</h3><p>Stored locally with result metadata</p></div></div><div id="test-history" class="panel-body test-history">${algorithmHistoryMarkup(tests)}</div></article>`;
    const zone = content.querySelector('#upload-zone');
    content.querySelector('.test-layout').insertAdjacentHTML('afterend', '<section class="panel" id="test-timeline" style="margin-top:20px"></section>');
    const input = content.querySelector('#media-file');
    const run = content.querySelector('#run-test');
    const choose = content.querySelector('#choose-file');
    function select(file) {
      selectedUpload = file || null; run.disabled = !selectedUpload;
      content.querySelector('#selected-file').textContent = selectedUpload ? `${selectedUpload.name} · ${(selectedUpload.size / 1024 / 1024).toFixed(1)} MB` : '';
    }
    select(selectedUpload);
    choose.addEventListener('click', () => input.click()); input.addEventListener('change', () => select(input.files[0]));
    for (const name of ['dragenter', 'dragover']) zone.addEventListener(name, event => { event.preventDefault(); zone.classList.add('dragging'); });
    for (const name of ['dragleave', 'drop']) zone.addEventListener(name, event => { event.preventDefault(); zone.classList.remove('dragging'); });
    zone.addEventListener('drop', event => select(event.dataTransfer.files[0]));
    run.addEventListener('click', async () => {
      if (!selectedUpload) return;
      run.disabled = true; run.textContent = 'Uploading…';
      try {
        await api('/api/v1/analysis-jobs', {method: 'POST', body: selectedUpload, headers: {'Content-Type': selectedUpload.type || 'application/octet-stream', 'X-Filename': selectedUpload.name.replace(/[^a-zA-Z0-9._-]/g, '_')}});
        toast('Test queued. Processing continues in the background.'); select(null); run.textContent = 'Run algorithm test';
        await refreshAlgorithmHistory();
      } catch (error) { toast(error.message, 'error'); run.disabled = false; run.textContent = 'Run algorithm test'; }
    });
    content.querySelectorAll('[data-test-result]').forEach(button => button.addEventListener('click', () => loadAlgorithmResult(button.dataset.testResult, button.dataset.resultType)));
    let historyBusy = false;
    addTimer(async () => {
      if (historyBusy) return;
      historyBusy = true;
      try { await refreshAlgorithmHistory(); } catch (error) { toast(error.message, 'error'); }
      finally { historyBusy = false; }
    }, 2200);
  }

  async function renderPage() {
    try {
      if (route === 'dashboard') await renderDashboard();
      else if (route === 'cameras') await renderCameras();
      else if (route === 'robots') renderRobots();
      else if (route === 'map') await renderMap();
      else if (route === 'settings') await renderSettings();
      else if (route === 'alerts') await renderAlerts();
      else if (route === 'algorithm-test') await renderAlgorithmTest();
      else window.location.replace('/dashboard');
      content.focus({preventScroll: true});
    } catch (error) {
      content.innerHTML = `<div class="empty-state"><h3>Could not load this workspace</h3><p>${escapeHtml(error.message)}</p><button class="button button-primary" onclick="window.location.reload()">Try again</button></div>`;
    }
  }

  const meta = pageMeta[route] || pageMeta.dashboard;
  document.getElementById('page-kicker').textContent = meta[0];
  document.getElementById('page-title').textContent = meta[1];
  document.title = `${meta[1]} · Township Sentinel`;
  document.querySelector(`[data-route="${CSS.escape(route)}"]`)?.classList.add('active');
  document.getElementById('logout').addEventListener('click', () => { sessionStorage.removeItem('sentinel_api_key'); window.location.replace('/login'); });
  content.addEventListener('click', cameraClickHandler);
  document.getElementById('menu-toggle').addEventListener('click', () => document.getElementById('sidebar').classList.toggle('open'));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') { closeModal(); document.getElementById('sidebar').classList.remove('open'); } });
  window.addEventListener('beforeunload', () => { clearTimers(); objectUrls.forEach(url => URL.revokeObjectURL(url)); });
  loadGlobalCounts();
  renderPage();
})();
