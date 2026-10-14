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
  let selectedTestCameraId = '';
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
    alerts: ['Safety review', 'Alerts'],
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
      document.getElementById('alert-nav-count').textContent = summary.alert_count || '';
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
      api('/api/v1/summary'), api('/api/v1/cameras'), api('/api/v1/events'),
    ]);
    const withStates = await getCameraStates(cameras);
    content.innerHTML = `
      <div class="section-head"><div><h2>Good day, Operator</h2><p>Here is the current township operations overview.</p></div><div class="head-actions"><a class="button button-secondary" href="/algorithm-test">${icon('flask')} Run media test</a><a class="button button-primary" href="/cameras">${icon('camera')} Manage cameras</a></div></div>
      <section class="metric-grid">
        ${metric('Cameras online', `${summary.online_count} / ${summary.camera_count}`, 'Configured monitoring sources', 'camera', '#12a886', '#e7f7f3')}
        ${metric('Open alerts', summary.alert_count, 'Persistent review signals', 'alert', '#d94c5c', '#fff0f2')}
        ${metric('Detections', summary.detection_count, 'This server session', 'person', '#3976e8', '#edf3ff')}
        ${metric('Media tests', summary.algorithm_test_count, 'Saved local test runs', 'flask', '#9a6ad9', '#f4effb')}
      </section>
      <section class="content-grid">
        <article class="panel"><div class="panel-head"><div><h3>Camera network</h3><p>Live state across configured sources</p></div><a class="link-button" href="/cameras">View all →</a></div><div class="panel-body camera-list">
          ${withStates.length ? withStates.map(camera => `<div class="camera-row"><span class="camera-thumb">${icon('camera')}</span><span><strong>${escapeHtml(camera.name)}</strong><small>${escapeHtml(camera.source_label)} · ${camera.zones.length} zones</small></span>${statePill(camera.status.state)}</div>`).join('') : '<div class="empty-state"><p>No cameras configured yet.</p><a class="button button-primary" href="/cameras">Add camera</a></div>'}
        </div></article>
        <article class="panel"><div class="panel-head"><div><h3>Recent alerts</h3><p>Newest signals requiring review</p></div><a class="link-button" href="/alerts">Review all →</a></div><div class="panel-body alert-list">
          ${events.length ? events.slice(0, 6).map(event => `<div class="alert-item"><span class="alert-dot"></span><div><strong>${escapeHtml(titleCase(event.rule))}</strong><p>${escapeHtml(event.message)}</p><time>${escapeHtml(event.camera_id)} · ${formatTime(event.observed_at)}</time></div></div>`).join('') : '<div class="empty-state"><p>No alerts have been recorded.</p></div>'}
        </div></article>
      </section>`;
  }

  function cameraCard(camera) {
    return `<article class="camera-card"><div class="camera-card-body">
      <h3>${escapeHtml(camera.name)}</h3><p>${escapeHtml(camera.source_label)} · ${camera.zones.length} zones</p>
      ${statePill(camera.status.state)} <a class="button button-primary" href="/cameras/${encodeURIComponent(camera.id)}">Open camera →</a>
    </div></article>`;
  }

  function detailCard(camera) {
    const running = ['running', 'starting', 'error'].includes(camera.status.state);
    return `<article class="camera-card" data-camera-card="${escapeHtml(camera.id)}">
      <div class="camera-visual"><span class="camera-placeholder">${icon('camera')}</span><img alt="Live view from ${escapeHtml(camera.name)}" hidden><span class="visual-state">${statePill(camera.status.state)}</span></div>
      <div class="camera-card-body"><div class="camera-title-row"><div><h3>${escapeHtml(camera.name)}</h3><p>${escapeHtml(camera.id)} · ${escapeHtml(camera.source_label)}</p></div><div class="card-menu"><button class="icon-button" data-edit-camera="${escapeHtml(camera.id)}" aria-label="Edit camera">${icon('settings')}</button><button class="icon-button" data-delete-camera="${escapeHtml(camera.id)}" aria-label="Delete camera">${icon('trash')}</button></div></div>
      <div class="camera-meta"><div><span>People</span><strong>${camera.status.person_count || 0}</strong></div><div><span>Vehicles</span><strong>${camera.status.vehicle_count || 0}</strong></div><div><span>Zones</span><strong>${camera.zones.length}</strong></div></div>
      <div class="card-actions"><button class="button ${running ? 'button-secondary' : 'button-primary'}" data-camera-action="${running ? 'stop' : 'start'}" data-camera-id="${escapeHtml(camera.id)}" ${camera.source_type === 'synthetic' ? 'disabled title="Synthetic cameras receive API observations"' : ''}>${running ? 'Stop camera' : camera.source_type === 'synthetic' ? 'Virtual input' : 'Start camera'}</button><button class="button button-secondary" data-zones="${escapeHtml(camera.id)}">Draw zones</button></div></div>
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
    content.innerHTML = `<div class="section-head"><div><h2>Camera management</h2><p>Create sources, control detection, and define semantic monitoring zones.</p></div><button id="add-camera" class="button button-primary">${icon('plus')} Add camera</button></div>
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
      <h2>${escapeHtml(camera.name)}</h2><p>Live view, camera settings, zones, and alerts.</p></div></div>
      <div class="camera-detail">${detailCard(camera)}</div>
      <p id="camera-health" role="status"></p>
      <section class="panel"><div class="panel-head"><h3>Behavior signals</h3><p>Recent alerts highlight for 10 seconds. Review before acting.</p></div>
      <div id="behavior-grid" class="behavior-grid"></div></section>
      <section class="panel camera-alerts"><div class="panel-head"><h3>Camera alert history</h3></div>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Time</th><th>Behavior</th><th>Zone</th><th>Message</th></tr></thead><tbody id="camera-alert-rows"></tbody></table></div></section>`;
    let state = camera.status;
    let polling = false;
    const mounted = content.querySelector('.camera-detail');
    async function refresh() {
      if (polling || !mounted.isConnected) return;
      polling = true;
      try {
        const [nextState, events, tracks] = await Promise.all([
          api(base + '/status'), api('/api/v1/events?camera_id=' + encodeURIComponent(detailId)), api(base + '/tracks')
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
        const counts = content.querySelectorAll('.camera-meta strong');
        counts[0].textContent = live ? state.person_count : 0; counts[1].textContent = live ? state.vehicle_count : 0;
        const rules = [...Object.entries(ruleLabels), ['fire', 'Fire / smoke'], ['fall', 'Human fall'], ['fighting', 'Fighting'], ['drowning', 'Drowning']];
        content.querySelector('#behavior-grid').innerHTML = rules.map(([rule, label]) => {
          const supported = Object.hasOwn(ruleLabels, rule);
          const configured = camera.zones.some(zone => zone.rule === rule);
          const recent = live && events.some(item => item.rule === rule && Date.now() - Date.parse(item.observed_at) >= 0 && Date.now() - Date.parse(item.observed_at) < 10000);
          const message = !supported ? 'Not installed' : !configured ? 'No zone configured' : recent ? 'Recent signal — review' : live ? 'Monitoring' : 'Inactive';
          return `<article class="behavior-tile ${recent ? 'signal-active' : ''}"><strong>${label}</strong><span>${message}</span></article>`;
        }).join('');
        content.querySelector('#camera-alert-rows').innerHTML = events.length ? events.map(item => `<tr><td>${formatTime(item.observed_at)}</td><td>${escapeHtml(titleCase(item.rule))}</td><td>${escapeHtml(item.zone_id)}</td><td>${escapeHtml(item.message)}</td></tr>`).join('') : '<tr><td colspan="4">No alerts for this camera.</td></tr>';
        let overlay = content.querySelector('.track-overlay');
        if (!overlay) { overlay = document.createElement('div'); overlay.className = 'track-overlay'; content.querySelector('.camera-visual').append(overlay); }
        overlay.innerHTML = live ? tracks.map(track => `<div class="track-box" style="left:${track.box[0]*100}%;top:${track.box[1]*100}%;width:${(track.box[2]-track.box[0])*100}%;height:${(track.box[3]-track.box[1])*100}%"><span>${escapeHtml(track.kind)} ${Math.round(track.confidence*100)}%</span></div>`).join('') : '';
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
    const zones = event.target.closest('[data-zones]');
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
      } else if (zones) {
        const cameras = await api('/api/v1/cameras');
        openZoneModal(cameras.find(camera => camera.id === zones.dataset.zones));
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
        <div class="form-field"><label for="camera-id">Camera ID</label><input class="input" id="camera-id" value="${escapeHtml(camera?.id || '')}" placeholder="north-gate" pattern="[a-zA-Z0-9][a-zA-Z0-9_-]*" ${editing ? 'disabled' : ''} required><small>Stable letters, numbers, dashes, or underscores.</small></div>
        <div class="form-field"><label for="camera-name">Display name</label><input class="input" id="camera-name" value="${escapeHtml(camera?.name || '')}" placeholder="North gate" required></div>
        <div class="form-field full"><label for="camera-source">Video source</label><input class="input" id="camera-source" placeholder="0, video file path, RTSP URL, or synthetic" ${editing ? '' : 'required'}><small>${editing ? `Current: ${escapeHtml(camera.source_label)}. Leave blank to keep it.` : 'Use 0 for the first webcam. Credentials in RTSP URLs are kept only in local configuration.'}</small></div>
      </div><div class="modal-actions"><button type="button" class="button button-secondary" data-close-modal>Cancel</button><button class="button button-primary" type="submit">${editing ? 'Save changes' : 'Add camera'}</button></div></form>`);
    const form = modalRoot.querySelector('#camera-form');
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const sourceValue = form.querySelector('#camera-source').value;
      const body = {name: form.querySelector('#camera-name').value.trim()};
      if (sourceValue.trim()) body.source = parseSource(sourceValue);
      if (!editing) { body.id = form.querySelector('#camera-id').value.trim(); body.source = parseSource(sourceValue); }
      const submit = form.querySelector('[type="submit"]'); submit.disabled = true;
      try {
        await api(editing ? `/api/v1/cameras/${encodeURIComponent(camera.id)}` : '/api/v1/cameras', {method: editing ? 'PUT' : 'POST', json: body});
        closeModal(); toast(editing ? 'Camera updated.' : 'Camera added.'); await loadGlobalCounts(); await renderCameras();
      } catch (error) { toast(error.message, 'error'); submit.disabled = false; }
    });
  }

  function openZoneModal(camera, referenceMedia = null) {
    if (!camera) return;
    let zones = structuredClone(camera.zones || []);
    let selected = zones.length ? 0 : -1;
    let points = selected >= 0 ? structuredClone(zones[selected].polygon) : [];
    let drawing = false;
    const meanings = ['restricted area', 'main door', 'entrance / exit', 'perimeter', 'parking area', 'no parking', 'pool danger area', 'gathering area', 'waiting area', 'custom'];
    const rules = Object.keys(ruleLabels);
    showModal(`<div class="modal-head"><div><h2>Zones · ${escapeHtml(camera.name)}</h2></div><button class="icon-button" data-close-modal aria-label="Close">×</button></div>
      <div class="modal-body"><div id="zone-chips" class="zone-list"></div><div class="zone-layout" style="margin-top:14px">
        <div><div class="zone-stage" id="zone-stage"><img id="zone-frame" alt="Camera scene" hidden><svg id="zone-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Zone drawing canvas"></svg></div><div class="zone-tools"><button class="button button-secondary" id="draw-zone">Draw new shape</button><button class="button button-ghost" id="undo-point">Undo point</button><button class="button button-ghost" id="clear-points">Clear</button></div></div>
        <div class="zone-form"><div class="form-field"><label for="zone-id">Zone name</label><input class="input" id="zone-id" placeholder="main-door"></div><div class="form-field"><label for="zone-meaning">Area meaning</label><select class="select" id="zone-meaning">${meanings.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(titleCase(value))}</option>`).join('')}</select></div><div class="form-field"><label for="zone-rule">Detection rule</label><select class="select" id="zone-rule">${rules.map(value => `<option value="${value}">${escapeHtml(titleCase(value))}</option>`).join('')}</select></div><div class="form-grid"><div class="form-field"><label for="zone-dwell">Dwell seconds</label><input class="input" id="zone-dwell" type="number" min="0" step="0.5" value="10"></div><div class="form-field"><label for="zone-cooldown">Cooldown</label><input class="input" id="zone-cooldown" type="number" min="0" step="1" value="30"></div></div><p class="zone-help">Click <strong>Draw new shape</strong>, then place at least three points on the camera view. Choose what the area represents separately from the detection rule.</p><button class="button button-secondary" id="save-zone-local">Save zone draft</button><button class="button button-danger" id="delete-zone" ${selected < 0 ? 'disabled' : ''}>Remove selected zone</button></div>
      </div></div><div class="modal-actions"><button class="button button-secondary" data-close-modal>Cancel</button><button class="button button-primary" id="persist-zones">Save all zones</button></div>`);

    modalRoot.querySelector('.zone-help').insertAdjacentHTML('beforebegin', `
      <div class="form-field" id="crowd-setting"><label for="zone-count">Crowd threshold (people)</label><input class="input" id="zone-count" type="number" min="2" max="1000" step="1" value="5"></div>
      <div class="form-field" id="parking-setting"><label for="zone-stationary">Stationary tolerance (normalized distance)</label><input class="input" id="zone-stationary" type="number" min="0.001" max="0.25" step="0.005" value="0.025"></div>
      <div class="form-field" id="object-setting"><label for="zone-proximity">Nearby-person radius (normalized)</label><input class="input" id="zone-proximity" type="number" min="0.01" max="1" step="0.01" value="0.15"></div>
      <p id="rule-help" class="zone-help"></p>`);
    const svg = modalRoot.querySelector('#zone-svg');
    const fields = {
      id: modalRoot.querySelector('#zone-id'), meaning: modalRoot.querySelector('#zone-meaning'),
      rule: modalRoot.querySelector('#zone-rule'), dwell: modalRoot.querySelector('#zone-dwell'),
      cooldown: modalRoot.querySelector('#zone-cooldown'),
      count: modalRoot.querySelector('#zone-count'), stationary: modalRoot.querySelector('#zone-stationary'),
      proximity: modalRoot.querySelector('#zone-proximity'),
    };

    function updateRuleFields() {
      modalRoot.querySelector('#crowd-setting').hidden = fields.rule.value !== 'crowd';
      modalRoot.querySelector('#parking-setting').hidden = !['illegal_parking', 'unattended_object'].includes(fields.rule.value);
      modalRoot.querySelector('#object-setting').hidden = fields.rule.value !== 'unattended_object';
      const hints = {pool_safety: 'Set dwell to 0 for immediate entry alerts. This is not drowning detection.',
        crowd: 'Alert when the zone continuously contains at least this many people for the dwell duration.',
        illegal_parking: 'Dwell counts only while a vehicle stays within the tolerance of its stationary origin. Calibrate for this view.',
        unattended_object: 'Stationary backpack, handbag or suitcase without a detected nearby person. This cannot establish ownership or abandonment.'};
      modalRoot.querySelector('#rule-help').textContent = hints[fields.rule.value] || 'Duration-based rules need video, not a single picture.';
    }
    fields.rule.addEventListener('change', updateRuleFields);

    function zoneDefaults(zone = {}) {
      return {id: zone.id || '', meaning: zone.meaning || 'custom', rule: zone.rule || 'intrusion', polygon: zone.polygon || [], dwell_seconds: zone.dwell_seconds ?? 10, cooldown_seconds: zone.cooldown_seconds ?? 30, activity_threshold: zone.activity_threshold ?? .7, min_vertical_travel: zone.min_vertical_travel ?? .12, min_activity_samples: zone.min_activity_samples ?? 2, crossing_line_y: zone.crossing_line_y ?? null, min_count: zone.min_count ?? 5, stationary_tolerance: zone.stationary_tolerance ?? .025, proximity_radius: zone.proximity_radius ?? .15};
    }

    function loadFields() {
      const zone = selected >= 0 ? zoneDefaults(zones[selected]) : zoneDefaults();
      fields.id.value = zone.id; fields.meaning.value = meanings.includes(zone.meaning) ? zone.meaning : 'custom'; fields.rule.value = zone.rule; fields.dwell.value = zone.dwell_seconds; fields.cooldown.value = zone.cooldown_seconds;
      fields.count.value = zone.min_count; fields.stationary.value = zone.stationary_tolerance; fields.proximity.value = zone.proximity_radius; updateRuleFields();
      modalRoot.querySelector('#delete-zone').disabled = selected < 0;
    }

    function renderZoneCanvas() {
      const polygons = zones.map((zone, index) => `<polygon points="${zone.polygon.map(point => `${point[0] * 100},${point[1] * 100}`).join(' ')}" opacity="${index === selected ? 1 : .45}"></polygon><text x="${zone.polygon[0]?.[0] * 100 || 2}" y="${zone.polygon[0]?.[1] * 100 || 5}">${escapeHtml(zone.meaning || zone.id)}</text>`).join('');
      const draft = points.length ? `<polyline points="${points.map(point => `${point[0] * 100},${point[1] * 100}`).join(' ')}"></polyline>${points.map(point => `<circle cx="${point[0] * 100}" cy="${point[1] * 100}" r="1.05"></circle>`).join('')}` : '';
      svg.innerHTML = polygons + draft;
      svg.classList.toggle('drawing', drawing);
      modalRoot.querySelector('#zone-chips').innerHTML = `<button class="zone-chip ${selected < 0 ? 'active' : ''}" data-zone-index="-1">+ New zone</button>` + zones.map((zone, index) => `<button class="zone-chip ${selected === index ? 'active' : ''}" data-zone-index="${index}">${escapeHtml(zone.meaning || zone.id)}</button>`).join('');
      modalRoot.querySelectorAll('[data-zone-index]').forEach(button => button.addEventListener('click', () => {
        selected = Number(button.dataset.zoneIndex); points = selected >= 0 ? structuredClone(zones[selected].polygon) : []; drawing = false; loadFields(); renderZoneCanvas();
      }));
    }

    async function loadZoneFrame() {
      try {
        if (referenceMedia) {
          const sourceUrl = rememberUrl(referenceMedia);
          const media = document.createElement(referenceMedia.type.startsWith('image/') ? 'img' : 'video');
          media.muted = true; media.preload = 'auto';
          await new Promise((resolve, reject) => {
            media.addEventListener(media.tagName === 'IMG' ? 'load' : 'loadeddata', resolve, {once: true});
            media.addEventListener('error', () => reject(new Error('This file cannot be previewed by the browser. Use a JPG/PNG reference frame or a browser-playable video.')), {once: true});
            media.src = sourceUrl;
          });
          const image = modalRoot.querySelector('#zone-frame');
          if (!image) return;
          const canvas = document.createElement('canvas');
          const width = media.videoWidth || media.naturalWidth, height = media.videoHeight || media.naturalHeight;
          canvas.width = Math.min(width, 1920); canvas.height = Math.round(canvas.width * height / width);
          canvas.getContext('2d').drawImage(media, 0, 0, canvas.width, canvas.height);
          image.onload = () => { image.parentElement.style.aspectRatio = image.naturalWidth + ' / ' + image.naturalHeight; };
          image.src = canvas.toDataURL('image/jpeg'); image.hidden = false;
          media.removeAttribute('src'); if (media.tagName === 'VIDEO') media.load();
          URL.revokeObjectURL(sourceUrl); objectUrls.delete(sourceUrl);
          return;
        }
        const cameraState = await api(`/api/v1/cameras/${encodeURIComponent(camera.id)}/status`);
        if (cameraState.state !== 'running') return;
        const response = await request(`/api/v1/cameras/${encodeURIComponent(camera.id)}/snapshot`);
        const image = modalRoot.querySelector('#zone-frame');
        if (!image) return;
        image.onload = () => { image.parentElement.style.aspectRatio = image.naturalWidth + ' / ' + image.naturalHeight; };
        image.src = rememberUrl(await response.blob()); image.hidden = false;
      } catch (error) { if (referenceMedia) toast(error.message, 'error'); }
    }

    modalRoot.querySelector('#draw-zone').addEventListener('click', () => { points = []; drawing = true; renderZoneCanvas(); });
    modalRoot.querySelector('#undo-point').addEventListener('click', () => { points.pop(); renderZoneCanvas(); });
    modalRoot.querySelector('#clear-points').addEventListener('click', () => { points = []; renderZoneCanvas(); });
    svg.addEventListener('pointerdown', event => {
      if (!drawing) return;
      const box = svg.getBoundingClientRect();
      points.push([(event.clientX - box.left) / box.width, (event.clientY - box.top) / box.height]);
      renderZoneCanvas();
    });

    function saveDraft() {
      const id = fields.id.value.trim();
      if (!id || points.length < 3) throw new Error('Enter a zone name and draw at least three points.');
      const zone = zoneDefaults(selected >= 0 ? zones[selected] : {});
      Object.assign(zone, {id, meaning: fields.meaning.value, rule: fields.rule.value, polygon: structuredClone(points), dwell_seconds: Number(fields.dwell.value), cooldown_seconds: Number(fields.cooldown.value), min_count: Number(fields.count.value), stationary_tolerance: Number(fields.stationary.value), proximity_radius: Number(fields.proximity.value)});
      if (zones.some((item, index) => item.id === id && index !== selected)) throw new Error('Zone names must be unique for this camera.');
      if (selected >= 0) zones[selected] = zone; else { zones.push(zone); selected = zones.length - 1; }
      drawing = false; loadFields(); renderZoneCanvas();
    }

    modalRoot.querySelector('#save-zone-local').addEventListener('click', () => { try { saveDraft(); toast('Zone draft updated.'); } catch (error) { toast(error.message, 'error'); } });
    modalRoot.querySelector('#delete-zone').addEventListener('click', () => { if (selected < 0) return; zones.splice(selected, 1); selected = zones.length ? Math.min(selected, zones.length - 1) : -1; points = selected >= 0 ? structuredClone(zones[selected].polygon) : []; loadFields(); renderZoneCanvas(); });
    modalRoot.querySelector('#persist-zones').addEventListener('click', async event => {
      event.target.disabled = true;
      try {
        if (selected >= 0 || drawing || (fields.id.value.trim() || points.length)) saveDraft();
        await api(`/api/v1/cameras/${encodeURIComponent(camera.id)}/zones`, {method: 'PUT', json: zones});
        closeModal(); toast('Camera zones saved.');
        if (route === 'algorithm-test') await renderAlgorithmTest(); else await renderCameras();
      } catch (error) { toast(error.message, 'error'); event.target.disabled = false; }
    });
    loadFields(); renderZoneCanvas(); loadZoneFrame();
  }

  async function renderAlerts() {
    const [events, cameras] = await Promise.all([api('/api/v1/events'), api('/api/v1/cameras')]);
    const cameraNames = Object.fromEntries(cameras.map(camera => [camera.id, camera.name]));
    content.innerHTML = `<div class="section-head"><div><h2>Alert review</h2><p>Persistent safety signals remain available after a server restart.</p></div><div class="toolbar"><input id="alert-search" class="input search-input" type="search" placeholder="Search alerts"><select id="alert-rule" class="select"><option value="">All rules</option><option value="intrusion">Intrusion</option><option value="loitering">Loitering</option><option value="wall_climbing">Wall climbing</option><option value="door_tampering">Door tampering</option></select></div></div><article class="panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Observed</th><th>Camera</th><th>Zone</th><th>Rule</th><th>Message</th><th>Confidence</th></tr></thead><tbody id="alert-rows"></tbody></table></div></article>`;
    const rows = content.querySelector('#alert-rows');
    content.querySelector('#alert-rule').innerHTML = '<option value="">All rules</option>' + Object.entries(ruleLabels).map(([rule, label]) => `<option value="${rule}">${escapeHtml(label)}</option>`).join('');
    function applyFilters() {
      const search = content.querySelector('#alert-search').value.toLowerCase();
      const rule = content.querySelector('#alert-rule').value;
      const filtered = events.filter(event => (!rule || event.rule === rule) && (!search || JSON.stringify(event).toLowerCase().includes(search)));
      rows.innerHTML = filtered.length ? filtered.map(event => `<tr><td>${formatTime(event.observed_at)}</td><td><strong>${escapeHtml(cameraNames[event.camera_id] || event.camera_id)}</strong></td><td>${escapeHtml(event.zone_id)}</td><td><span class="rule-pill">${escapeHtml(titleCase(event.rule))}</span></td><td>${escapeHtml(event.message)}</td><td>${Math.round(event.confidence * 100)}%</td></tr>`).join('') : '<tr><td colspan="6"><div class="empty-state"><p>No matching alerts.</p></div></td></tr>';
    }
    content.querySelector('#alert-search').addEventListener('input', applyFilters);
    content.querySelector('#alert-rule').addEventListener('change', applyFilters);
    applyFilters();
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
            <button class="map-control map-control-wide active" type="button" data-map-action="cameras" aria-pressed="true">Camera coverage</button>
          </div>
          <div class="map-hint"><span>Drag to orbit</span><span>Scroll to zoom</span><span>Click an asset</span></div>
        </div>
        <aside class="map-side-panel">
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
          <article class="panel map-camera-panel"><div class="panel-head"><div><h3>Camera positions</h3><p>${cameras.length} configured source${cameras.length === 1 ? '' : 's'}</p></div></div><div class="map-directory-list">${cameras.length ? cameras.map((camera, index) => `<button type="button" class="map-directory-item" data-map-feature="camera-${escapeHtml(camera.id)}"><span class="map-camera-dot"></span><span><strong>${escapeHtml(camera.name)}</strong><small>${escapeHtml(camera.source_label)} · Marker ${String(index + 1).padStart(2, '0')}</small></span><span aria-hidden="true">→</span></button>`).join('') : '<div class="map-empty-cameras"><p>No cameras configured yet.</p><a class="button button-secondary" href="/cameras">Add a camera</a></div>'}</div></article>
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
    content.innerHTML = `<div class="section-head"><div><h2>Robot operations</h2><p>A dedicated workspace for future robot adapters and missions.</p></div><span class="state-pill">0 connected</span></div><article class="panel empty-state" style="min-height:520px"><span class="empty-icon">${icon('robot')}</span><h3>No robots connected</h3><p>Robot hardware is intentionally not simulated as live equipment. When a device is selected, it can be integrated behind a replaceable adapter with virtual-first testing.</p><button class="button button-secondary" disabled>Device adapter required</button></article>`;
  }

  function algorithmHistoryMarkup(tests) {
    return tests.length ? tests.map(test => `<article class="test-card"><div><h4>${escapeHtml(test.filename)}</h4><p>${formatTime(test.created_at)} · ${test.frames_processed || 0} frames · ${test.events?.length || 0} test alerts</p><p>${escapeHtml(test.camera_name || 'Object detection only')}</p></div><div>${test.state === 'completed' ? `<button class="button button-secondary" data-test-result="${escapeHtml(test.id)}" data-result-type="${escapeHtml(test.output_media_type)}">View result</button>` : statePill(test.state)}${test.error ? `<p class="form-error">${escapeHtml(test.error)}</p>` : ''}</div></article>`).join('') : '<div class="empty-state"><p>No media tests have been run.</p></div>';
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
      const events = metadata.events || [];
      const timeline = content.querySelector('#test-timeline');
      timeline.innerHTML = `<div class="panel-head"><div><h3>Test alert timeline</h3><p>Isolated from live alerts · ${escapeHtml(metadata.camera_name || 'Object detection only')}</p></div></div>
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
    content.innerHTML = `<div class="section-head"><div><h2>Algorithm test lab</h2><p>Run the production detector on recorded evidence before trying a scenario at a real camera.</p></div><span class="state-pill">Images + videos</span></div><section class="test-layout"><div><div id="upload-zone" class="upload-zone"><span class="upload-icon">${icon('upload')}</span><h3>Drop a picture or video here</h3><p>JPG, PNG, WEBP, MP4, MOV, AVI, or MKV. Videos are bounded to the first 60 seconds.</p><input id="media-file" type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/x-msvideo,video/x-matroska" hidden><button id="choose-file" class="button button-secondary">Choose media</button><div id="selected-file" class="selected-file"></div></div><button id="run-test" class="button button-primary" style="width:100%;margin-top:12px" disabled>Run algorithm test</button></div><article class="panel"><div class="panel-head"><div><h3>Result viewer</h3><p>Annotated output from the same detector adapter</p></div></div><div class="panel-body"><div id="result-viewer" class="result-viewer"><p>Select a completed test to inspect its output.</p></div></div></article></section><article class="panel" style="margin-top:20px"><div class="panel-head"><div><h3>Test history</h3><p>Stored locally with result metadata</p></div></div><div id="test-history" class="panel-body test-history">${algorithmHistoryMarkup(tests)}</div></article>`;
    const zone = content.querySelector('#upload-zone');
    zone.insertAdjacentHTML('beforebegin', `<div class="panel-body test-configuration"><div class="form-field"><label for="test-camera">Analysis configuration</label><select class="select" id="test-camera"><option value="">Object detection only</option>${cameras.map(camera => `<option value="${escapeHtml(camera.id)}">${escapeHtml(camera.name)} · ${camera.zones.length} zones</option>`).join('')}</select></div><p id="test-config-help" class="zone-help"></p><p class="zone-help">Test alerts never enter live alert history. A still image cannot test duration or movement. Video analysis: up to ${capabilities.inference_fps} FPS, same rules as live cameras.</p></div>`);
    content.querySelector('.test-layout').insertAdjacentHTML('afterend', '<section class="panel" id="test-timeline" style="margin-top:20px"></section>');
    content.insertAdjacentHTML('beforeend', `<details class="panel capability-list" style="margin-top:20px"><summary class="panel-head">A01–A16 capability status · ${escapeHtml(capabilities.tracker)} tracking</summary><div class="table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>Capability</th><th>Status</th><th>Scope</th></tr></thead><tbody>${capabilities.items.map(item => `<tr><td>${item.id}</td><td>${escapeHtml(item.name)}</td><td>${escapeHtml(titleCase(item.status))}</td><td>${escapeHtml(item.note)}</td></tr>`).join('')}</tbody></table></div></details>`);
    const cameraSelect = content.querySelector('#test-camera');
    cameraSelect.value = selectedTestCameraId;
    cameraSelect.insertAdjacentHTML('afterend', '<button id="test-edit-zones" class="button button-secondary" style="margin-top:10px">Edit selected camera zones</button>');
    const editZones = content.querySelector('#test-edit-zones');
    editZones.addEventListener('click', () => openZoneModal(cameras.find(item => item.id === cameraSelect.value), selectedUpload));
    const updateConfiguration = () => {
      selectedTestCameraId = cameraSelect.value;
      const camera = cameras.find(item => item.id === cameraSelect.value);
      editZones.disabled = !camera;
      content.querySelector('#test-config-help').textContent = camera ? `${camera.zones.map(item => ruleLabels[item.rule] || item.rule).join(', ') || 'No zones configured.'} Zones must match the uploaded viewpoint; edit them on the camera detail page.` : 'Select a camera to replay its saved zone rules, or leave object detection only selected.';
    };
    cameraSelect.addEventListener('change', updateConfiguration); updateConfiguration();
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
        await api('/api/v1/algorithm-tests' + (cameraSelect.value ? '?camera_id=' + encodeURIComponent(cameraSelect.value) : ''), {method: 'POST', body: selectedUpload, headers: {'Content-Type': selectedUpload.type || 'application/octet-stream', 'X-Filename': selectedUpload.name.replace(/[^a-zA-Z0-9._-]/g, '_')}});
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
