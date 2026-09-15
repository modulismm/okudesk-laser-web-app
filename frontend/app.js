/**
 * Main Application Logic for OKU Desk Laser Interface
 * 
 * @version 0.2.2
 */

// Initialize parsers
const svgParser = new SVGParser();
const gcodeGen = new GCodeGenerator();

// Application state
const appState = {
    svgData: null,
    scale: 1,
    svgElement: null,
    originMode: 'bottom-left',
    originX: 0,
    originY: 0,
    mode: 'vector',
    rasterEnabled: false,
    rasterUrl: '/raster'
};

// Based on the Oku Desk material guide you provided (speed mm/min, power %, passes)
// Defaults are picked as reasonable midpoints; user can still tweak per-layer after applying.
const MATERIAL_PRESETS = {
    fabric: {
        cut: { speed: [1000, 2000], power: [100, 100], passes: [1, 3], depth: '0.5–3 mm' },
        engrave: { speed: [3000, 5000], power: [100, 100] }
    },
    felt: {
        cut: { speed: [500, 1000], power: [100, 100], passes: [1, 3], depth: '1–6 mm' },
        engrave: { speed: [5000, 7000], power: [30, 50] }
    },
    foam_board: {
        cut: { speed: [600, 1200], power: [100, 100], passes: [1, 3], depth: '1–6 mm' },
        engrave: { speed: [5000, 6000], power: [50, 50] }
    },
    eva_rubber: {
        cut: { speed: [1000, 1000], power: [100, 100], passes: [1, 3], depth: '1–20 mm' },
        engrave: { speed: [5000, 7000], power: [10, 25] }
    },
    mdf: {
        cut: { speed: [400, 400], power: [100, 100], passes: [2, 8], depth: '1–3 mm' },
        engrave: { speed: [4000, 7000], power: [10, 25] }
    },
    plywood: {
        cut: { speed: [500, 500], power: [100, 100], passes: [2, 6], depth: '1–4 mm' },
        engrave: { speed: [5000, 8000], power: [80, 100] }
    },
    balsa: {
        cut: { speed: [600, 600], power: [100, 100], passes: [2, 6], depth: '1–5 mm' },
        engrave: { speed: [5000, 8000], power: [80, 100] }
    },
    kraftplex: {
        cut: { speed: [800, 1000], power: [100, 100], passes: [1, 3], depth: '1–3 mm' },
        engrave: { speed: [5000, 7000], power: [100, 100] }
    },
    cardboard: {
        cut: { speed: [600, 1000], power: [100, 100], passes: [1, 3], depth: '0.5–5 mm' },
        engrave: { speed: [4000, 5000], power: [45, 45] }
    },
    paperboard: {
        cut: { speed: [700, 1200], power: [100, 100], passes: [1, 3], depth: '0.5–2 mm' },
        engrave: { speed: [3000, 5000], power: [80, 80] }
    },
    paper: {
        cut: { speed: [1400, 2500], power: [100, 100], passes: [1, 1], depth: '0.2–1 mm' },
        engrave: { speed: [3000, 5000], power: [70, 70] }
    },
    leather: {
        cut: { speed: [1200, 1600], power: [100, 100], passes: [1, 4], depth: '0.5–1 mm' },
        engrave: { speed: [4000, 5000], power: [80, 100] }
    },
    cork: {
        cut: { speed: [2000, 2000], power: [100, 100], passes: [1, 4], depth: '0.5–3 mm' },
        engrave: { speed: [5500, 6000], power: [20, 30] }
    },
    opaque_acrylic: {
        cut: { speed: [400, 400], power: [100, 100], passes: [3, 10], depth: '0.5–2 mm' },
        engrave: { speed: [4000, 5000], power: [70, 80] }
    }
};

// DOM element references (cached)
let elements = {};

/**
 * Initialize application
 */
function init() {
    // Cache DOM elements
    elements = {
        appContainer: document.querySelector('.app-container'),
        dropZone: document.getElementById('dropZone'),
        fileInput: document.getElementById('fileInput'),
        jobsContainer: document.getElementById('jobsContainer'),
        svgLayer: document.getElementById('svgLayer'),
        exportBtn: document.getElementById('exportBtn'),
        statDim: document.getElementById('statDim'),
        statTime: document.getElementById('statTime'),
        statsPanel: document.getElementById('statsPanel'),
        travelSpeed: document.getElementById('travelSpeed'),
        fitViewBtn: document.getElementById('fitViewBtn'),
        centerJobBtn: document.getElementById('centerJobBtn'),
        canvasContainer: document.getElementById('canvasContainer'),
        originInputs: document.querySelectorAll('input[name="originMode"]'),
        originMarker: document.querySelector('.origin-marker'),
        customOriginInputs: document.getElementById('customOriginInputs'),
        originX: document.getElementById('originX'),
        originY: document.getElementById('originY'),
        materialPreset: document.getElementById('materialPreset'),
        materialMode: document.getElementById('materialMode'),
        applyMaterialBtn: document.getElementById('applyMaterialBtn'),
        materialHint: document.getElementById('materialHint'),
        modeVectorBtn: document.getElementById('modeVectorBtn'),
        modeRasterBtn: document.getElementById('modeRasterBtn'),
        rasterPanel: document.getElementById('rasterPanel'),
        rasterFrame: document.getElementById('rasterFrame'),
        openRasterTab: document.getElementById('openRasterTab')
    };

    // Setup event listeners
    setupDragDrop();
    setupFileInput();
    setupExport();
    setupControls();
    setupModeSwitch();
    setupMaterialPresets();
    setupProjectLinks().finally(() => {
        maybeShowFirstRunModal();
    });

    // Initial view fit
    requestAnimationFrame(() => fitView());
    window.addEventListener('resize', debounce(fitView, 250));
}

async function setupProjectLinks() {
    const link = document.getElementById('donateLink');
    const gitlab = document.getElementById('gitlabLink');
    if (!link && !gitlab) return;

    // Fallback placeholder (replace via /api/config on your hosted instance)
    if (link) link.href = 'https://buymeacoffee.com/bootlessbear';
    if (gitlab) gitlab.href = 'https://gitlab.com/Bootlessbear/okudesk-laser-web-app';

    try {
        const res = await fetch('/api/config', { cache: 'no-store' });
        if (!res.ok) return;
        const cfg = await res.json();
        if (cfg && cfg.donate_url && link) link.href = cfg.donate_url;
        if (cfg && cfg.gitlab_url && gitlab) gitlab.href = cfg.gitlab_url;
        if (cfg && typeof cfg.raster_enabled !== 'undefined') {
            appState.rasterEnabled = !!cfg.raster_enabled;
            if (cfg.raster_url) appState.rasterUrl = String(cfg.raster_url);
            updateRasterAvailability();
        }
    } catch {
        // ignore (static mode)
    }
}

function setupModeSwitch() {
    const { modeVectorBtn, modeRasterBtn } = elements;
    if (!modeVectorBtn || !modeRasterBtn) return;

    modeVectorBtn.addEventListener('click', () => setAppMode('vector'));
    modeRasterBtn.addEventListener('click', () => setAppMode('raster'));

    // Default mode
    setAppMode('vector');
    updateRasterAvailability();

    // Optional deep link: /#raster
    if (location.hash === '#raster') {
        setAppMode('raster');
    }
}

function updateRasterAvailability() {
    const { modeRasterBtn, openRasterTab } = elements;
    if (modeRasterBtn) {
        modeRasterBtn.disabled = !appState.rasterEnabled;
        modeRasterBtn.title = appState.rasterEnabled ? 'Raster engraving' : 'Raster disabled on server';
    }
    if (openRasterTab) {
        openRasterTab.href = appState.rasterUrl || '/raster';
    }
    // If raster was open but server says disabled, bounce back.
    if (!appState.rasterEnabled && appState.mode === 'raster') {
        setAppMode('vector');
    }
}

function setAppMode(mode) {
    const { appContainer, modeVectorBtn, modeRasterBtn, rasterPanel, rasterFrame, openRasterTab } = elements;
    if (!appContainer) return;

    if (mode === 'raster' && !appState.rasterEnabled) {
        showError('Raster is disabled on this server. Set ENABLE_RASTER=1 and restart.');
        mode = 'vector';
    }

    appState.mode = mode;
    appContainer.classList.toggle('mode-raster', mode === 'raster');

    if (modeVectorBtn) {
        const active = mode === 'vector';
        modeVectorBtn.classList.toggle('active', active);
        modeVectorBtn.setAttribute('aria-selected', active ? 'true' : 'false');
    }
    if (modeRasterBtn) {
        const active = mode === 'raster';
        modeRasterBtn.classList.toggle('active', active);
        modeRasterBtn.setAttribute('aria-selected', active ? 'true' : 'false');
    }

    if (openRasterTab) {
        openRasterTab.style.display = mode === 'raster' ? 'block' : 'none';
    }

    if (rasterPanel) {
        rasterPanel.style.display = mode === 'raster' ? 'flex' : 'none';
    }

    // Lazy-load iframe only when needed
    if (mode === 'raster' && rasterFrame) {
        const desired = appState.rasterUrl || '/raster';
        if (!rasterFrame.src || rasterFrame.src.endsWith('about:blank')) {
            rasterFrame.src = desired;
        }
    }
}

function maybeShowFirstRunModal() {
    const overlay = document.getElementById('firstRunOverlay');
    const closeBtn = document.getElementById('firstRunClose');
    const gitlabBtn = document.getElementById('firstRunGitlab');
    const donateBtn = document.getElementById('firstRunDonate');
    if (!overlay || !closeBtn) return;

    const key = 'oku_first_run_v1';
    if (localStorage.getItem(key) === '1') return;

    // Wire links from header links if present
    const gitlabLink = document.getElementById('gitlabLink');
    const donateLink = document.getElementById('donateLink');
    if (gitlabBtn && gitlabLink && gitlabLink.href) gitlabBtn.href = gitlabLink.href;
    if (donateBtn && donateLink && donateLink.href) donateBtn.href = donateLink.href;

    const close = () => {
        overlay.style.display = 'none';
        localStorage.setItem(key, '1');
    };

    overlay.style.display = 'flex';
    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
    });
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') close();
    }, { once: true });
}

/**
 * Setup drag and drop functionality
 */
function setupDragDrop() {
    const { dropZone, fileInput } = elements;

    dropZone.addEventListener('click', () => fileInput.click());

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    dropZone.addEventListener('dragover', () => {
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        dropZone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file) loadFile(file);
    });
}

/**
 * Setup file input
 */
function setupFileInput() {
    elements.fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) loadFile(file);
    });
}

/**
 * Setup export button
 */
function setupExport() {
    elements.exportBtn.addEventListener('click', generateAndDownload);
}

/**
 * Setup control buttons
 */
function setupControls() {
    if (elements.fitViewBtn) {
        elements.fitViewBtn.addEventListener('click', fitView);
    }
    if (elements.centerJobBtn) {
        elements.centerJobBtn.addEventListener('click', centerJob);
    }
    if (elements.travelSpeed) {
        elements.travelSpeed.addEventListener('input', debounce(updateStats, 300));
    }

    if (elements.originInputs && elements.originInputs.length) {
        elements.originInputs.forEach(input => {
            input.addEventListener('change', () => {
                appState.originMode = getOriginMode();
                updateCustomOriginVisibility();
                updateOriginMarker();
                if (appState.svgData) renderWorkspace(appState.svgData);
            });
        });
        if (elements.originX) {
            elements.originX.addEventListener('input', () => {
                appState.originX = parseFloat(elements.originX.value) || 0;
                if (appState.svgData) renderWorkspace(appState.svgData);
            });
        }
        if (elements.originY) {
            elements.originY.addEventListener('input', () => {
                appState.originY = parseFloat(elements.originY.value) || 0;
                if (appState.svgData) renderWorkspace(appState.svgData);
            });
        }
        appState.originMode = getOriginMode();
        updateCustomOriginVisibility();
        updateOriginMarker();
    }
}

function setupMaterialPresets() {
    const { materialPreset, materialMode, applyMaterialBtn } = elements;
    if (!materialPreset || !materialMode || !applyMaterialBtn) return;

    const refresh = () => {
        const key = materialPreset.value;
        applyMaterialBtn.disabled = !key || !appState.svgData;
        updateMaterialHint();
    };

    materialPreset.addEventListener('change', refresh);
    materialMode.addEventListener('change', refresh);
    applyMaterialBtn.addEventListener('click', applySelectedMaterialPreset);
    refresh();
}

function midpoint(range) {
    if (!range || range.length < 2) return null;
    const a = Number(range[0]);
    const b = Number(range[1]);
    if (!isFinite(a) || !isFinite(b)) return null;
    return Math.round((a + b) / 2);
}

function applySelectedMaterialPreset() {
    if (!appState.svgData) return;
    const key = elements.materialPreset?.value;
    const mode = elements.materialMode?.value || 'cut';
    const preset = MATERIAL_PRESETS[key]?.[mode];
    if (!preset) return;

    const speed = midpoint(preset.speed) ?? 1000;
    const power = midpoint(preset.power) ?? 100;
    const passes = preset.passes ? (midpoint(preset.passes) ?? 1) : 1;

    // Apply to enabled jobs (vector: jobs = colors/layers)
    appState.svgData.jobs.forEach(job => {
        if (!job?.enabled) return;
        job.speed = speed;
        job.power = power;
        if (mode === 'cut') job.passes = passes;
        if (mode === 'engrave') job.passes = 1;
    });

    renderJobs(appState.svgData.jobs);
    updateStats();
    updateMaterialHint();
}

function updateMaterialHint() {
    const el = elements.materialHint;
    const key = elements.materialPreset?.value;
    const mode = elements.materialMode?.value || 'cut';
    if (!el || !key) {
        if (el) el.style.display = 'none';
        return;
    }
    const preset = MATERIAL_PRESETS[key]?.[mode];
    if (!preset) {
        el.style.display = 'none';
        return;
    }

    const speedTxt = preset.speed ? `${preset.speed[0]}–${preset.speed[1]} mm/min` : '—';
    const powerTxt = preset.power ? `${preset.power[0]}–${preset.power[1]}%` : '—';
    const passesTxt = preset.passes ? `${preset.passes[0]}–${preset.passes[1]} passes` : '—';
    const depthTxt = preset.depth ? `, depth ${preset.depth}` : '';

    el.textContent = mode === 'cut'
        ? `Cut: speed ${speedTxt}, power ${powerTxt}, ${passesTxt}${depthTxt}.`
        : `Engrave: speed ${speedTxt}, power ${powerTxt}.`;
    el.style.display = 'block';
}

function getOriginMode() {
    const inputs = elements.originInputs;
    if (!inputs || !inputs.length) return 'bottom-left';
    const checked = Array.from(inputs).find(i => i.checked);
    return checked ? checked.value : 'bottom-left';
}

function updateCustomOriginVisibility() {
    const { customOriginInputs } = elements;
    if (!customOriginInputs) return;
    customOriginInputs.style.display = appState.originMode === 'custom' ? 'block' : 'none';
    if (appState.originMode === 'custom') {
        if (elements.originX) elements.originX.value = appState.originX;
        if (elements.originY) elements.originY.value = appState.originY;
    }
}

function updateOriginMarker() {
    const m = elements.originMarker;
    if (!m) return;
    m.classList.remove(
        'origin-bottom-left',
        'origin-bottom-right',
        'origin-top-left',
        'origin-top-right',
        'origin-center',
        'origin-custom'
    );
    if (appState.originMode === 'custom') {
        m.classList.add('origin-custom');
        // Position custom marker at specified coordinates
        const x = Math.min(Math.max(appState.originX, 0), 500);
        const y = Math.min(Math.max(285 - appState.originY, 0), 285); // Flip Y for SVG
        m.style.left = `${(x / 500) * 100}%`;
        m.style.bottom = `${(y / 285) * 100}%`;
        m.style.top = 'auto';
        m.style.right = 'auto';
        m.style.transform = 'none';
    } else {
        m.classList.add(`origin-${appState.originMode}`);
        m.style.left = '';
        m.style.bottom = '';
        m.style.top = '';
        m.style.right = '';
        m.style.transform = '';
    }
}

/**
 * Load and parse SVG file
 * @param {File} file - SVG file to load
 */
async function loadFile(file) {
    if (!file || !file.name.toLowerCase().endsWith('.svg')) {
        showError('Please select a valid SVG file.');
        return;
    }

    try {
        showLoading(true);
        const result = await svgParser.parseSVG(file);
        
        appState.svgData = result;
        
        renderWorkspace(result);
        renderJobs(result.jobs);
        updateStats();
        
        elements.exportBtn.disabled = false;
        elements.statsPanel.style.display = 'block';
        
        showLoading(false);
    } catch (err) {
        console.error('Error loading SVG:', err);
        showError('Error parsing SVG: ' + err.message);
        showLoading(false);
    }
}

/**
 * Render SVG in workspace visualization
 * @param {Object} data - Parsed SVG data
 */
function renderWorkspace(data) {
    elements.svgLayer.innerHTML = '';
    updateOriginMarker();
    
    // Create bed SVG container
    const bedSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    bedSvg.setAttribute('viewBox', '0 0 500 285');
    bedSvg.setAttribute('width', '100%');
    bedSvg.setAttribute('height', '100%');
    
    // Clone user SVG and position it
    const userSvg = data.element.cloneNode(true);
    const w = data.dimensions.width;
    const h = data.dimensions.height;
    let x = 0;
    let y = 285 - h; // bottom-left default (SVG y-down)

    switch (appState.originMode) {
        case 'top-left':
            x = 0;
            y = 0;
            break;
        case 'top-right':
            x = 500 - w;
            y = 0;
            break;
        case 'bottom-right':
            x = 500 - w;
            y = 285 - h;
            break;
        case 'center':
            x = (500 - w) / 2;
            y = (285 - h) / 2;
            break;
        case 'custom':
            x = Math.max(0, Math.min(appState.originX, 500 - w));
            y = Math.max(0, Math.min(285 - appState.originY - h, 285 - h));
            break;
        default:
            x = 0;
            y = 285 - h;
    }

    userSvg.setAttribute('x', String(x));
    userSvg.setAttribute('y', String(y));
    userSvg.setAttribute('width', String(data.dimensions.width));
    userSvg.setAttribute('height', String(data.dimensions.height));
    userSvg.removeAttribute('id');
    
    bedSvg.appendChild(userSvg);
    elements.svgLayer.appendChild(bedSvg);
    appState.svgElement = bedSvg;
}

/**
 * Render job cards in sidebar
 * @param {Array} jobs - Array of job objects
 */
function renderJobs(jobs) {
    if (!jobs || jobs.length === 0) {
        elements.jobsContainer.innerHTML = '<div class="empty-state">No paths found in SVG</div>';
        return;
    }

    elements.jobsContainer.innerHTML = '';
    
    jobs.forEach((job, idx) => {
        const card = createJobCard(job, idx);
        elements.jobsContainer.appendChild(card);
    });
}

function moveJob(fromIdx, direction) {
    if (!appState.svgData || !Array.isArray(appState.svgData.jobs)) return;
    const jobs = appState.svgData.jobs;
    const toIdx = fromIdx + direction;
    if (fromIdx < 0 || fromIdx >= jobs.length) return;
    if (toIdx < 0 || toIdx >= jobs.length) return;

    const [item] = jobs.splice(fromIdx, 1);
    jobs.splice(toIdx, 0, item);

    renderJobs(jobs);
    updateStats();
}

/**
 * Create a job card element
 * @param {Object} job - Job object
 * @param {number} idx - Job index
 * @returns {HTMLElement} Job card element
 */
function createJobCard(job, idx) {
    const card = document.createElement('div');
    card.className = 'job-card expanded';
    card.dataset.jobIndex = idx;
    
    const header = document.createElement('div');
    header.className = 'job-header';
    header.innerHTML = `
        <div class="job-title">
            <div class="color-dot" style="background:${escapeHtml(job.color)}"></div>
            <span>${escapeHtml(job.color)}</span>
            <span style="color: var(--text-muted); font-weight: normal;">(${job.paths.length} paths)</span>
        </div>
        <div class="job-controls">
            <div class="job-order">
                <button class="job-move" data-move="-1" aria-label="Move job up" title="Move up">▲</button>
                <button class="job-move" data-move="1" aria-label="Move job down" title="Move down">▼</button>
            </div>
            <input type="checkbox" ${job.enabled ? 'checked' : ''} 
                data-field="enabled" data-index="${idx}">
        </div>
    `;
    
    const body = document.createElement('div');
    body.className = 'job-body';
    body.innerHTML = `
        <div class="slider-group">
            <div class="slider-header">
                <span>Power</span>
                <span class="value-display" data-field="power" data-index="${idx}">${job.power}%</span>
            </div>
            <input type="range" min="0" max="100" value="${job.power}" 
                data-field="power" data-index="${idx}">
        </div>
        <div class="slider-group">
            <div class="slider-header">
                <span>Speed</span>
                <span class="value-display" data-field="speed" data-index="${idx}">${job.speed} mm/min</span>
            </div>
            <input type="range" min="100" max="6000" step="100" value="${job.speed}" 
                data-field="speed" data-index="${idx}">
        </div>
        <div class="slider-group">
            <div class="slider-header">
                <span>Passes</span>
                <span class="value-display" data-field="passes" data-index="${idx}">${job.passes}</span>
            </div>
            <input type="range" min="1" max="10" value="${job.passes}" 
                data-field="passes" data-index="${idx}">
        </div>
    `;
    
    // Setup event listeners
    header.addEventListener('click', (e) => {
        if (e.target.type !== 'checkbox') {
            card.classList.toggle('expanded');
        }
    });

    // Move up/down controls
    header.querySelectorAll('button.job-move').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const delta = parseInt(btn.dataset.move, 10);
            moveJob(idx, delta);
        });
    });
    
    const checkbox = header.querySelector('input[type="checkbox"]');
    checkbox.addEventListener('change', (e) => {
        updateJobSetting(idx, 'enabled', e.target.checked);
    });
    
    body.querySelectorAll('input[type="range"]').forEach(slider => {
        slider.addEventListener('input', (e) => {
            const field = e.target.dataset.field;
            const value = field === 'passes' ? parseInt(e.target.value) : parseFloat(e.target.value);
            updateJobSetting(idx, field, value);
            
            // Update display
            const display = body.querySelector(`.value-display[data-field="${field}"]`);
            if (display) {
                if (field === 'power') {
                    display.textContent = `${value}%`;
                } else if (field === 'speed') {
                    display.textContent = `${value} mm/min`;
                } else {
                    display.textContent = value;
                }
            }
        });
    });
    
    card.appendChild(header);
    card.appendChild(body);
    
    return card;
}

/**
 * Update job setting
 * @param {number} idx - Job index
 * @param {string} field - Field name
 * @param {*} value - New value
 */
function updateJobSetting(idx, field, value) {
    if (!appState.svgData || !appState.svgData.jobs[idx]) return;
    
    appState.svgData.jobs[idx][field] = value;
    updateStats();
}

/**
 * Update statistics display
 */
function updateStats() {
    if (!appState.svgData) return;
    
    const travelSpeed = parseInt(elements.travelSpeed.value) || 5000;
    
    // Use optimized time estimation (doesn't generate full G-code)
    const timeMinutes = gcodeGen.estimateTime(
        appState.svgData.jobs,
        appState.svgData.dimensions.height,
        travelSpeed
    );
    
    const mins = Math.ceil(timeMinutes);
    const secs = Math.floor((timeMinutes - Math.floor(timeMinutes)) * 60);
    
    if (mins > 0) {
        elements.statTime.textContent = `${mins}m ${secs > 0 ? secs + 's' : ''}`;
    } else {
        elements.statTime.textContent = `${secs}s`;
    }
    
    const dim = appState.svgData.dimensions;
    elements.statDim.textContent = `${dim.width.toFixed(1)} × ${dim.height.toFixed(1)} mm`;
}

/**
 * Generate G-code and trigger download
 */
function generateAndDownload() {
    if (!appState.svgData) {
        showError('No file loaded');
        return;
    }

    try {
        const travelSpeed = parseInt(elements.travelSpeed.value) || 5000;

        // G-code is always generated server-side: the client-side generator
        // (gcode-generator.js) does not apply <g transform="..."> and is
        // missing several path commands (A/Q/S/T), so it produces wrong
        // geometry on real-world SVGs. There is intentionally no client-side
        // fallback for the actual cut file - if the backend fails, we must
        // surface that clearly rather than silently downloading wrong G-code.
        generateViaBackend(travelSpeed);

    } catch (err) {
        console.error('Error generating G-code:', err);
        showError('Error generating G-code: ' + err.message);
    }
}

async function generateViaBackend(travelSpeed) {
    const svgString = appState.svgData?.svgString;
    if (!svgString) throw new Error('Missing SVG source');

    let data;
    try {
        const payload = {
            svg_content: svgString,
            origin: appState.originMode,
            travel_speed: travelSpeed,
            jobs: appState.svgData.jobs
        };
        if (appState.originMode === 'custom') {
            payload.origin_x = appState.originX;
            payload.origin_y = appState.originY;
        }
        const res = await fetch('/api/generate-vector-advanced', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        data = await res.json();
        if (res.ok && data && data.success && data.gcode) {
            downloadText(data.gcode, data.filename || 'oku-job.gco');
            return;
        }
        throw new Error(data?.error || data?.details || 'Backend generation failed');
    } catch (e) {
        // No client-side fallback here on purpose (see comment in
        // generateAndDownload()) - a silently-downloaded wrong G-code file
        // can physically destroy material. Surface the failure instead.
        const reason = e?.message || String(e);
        showError(
            'G-code generation failed: the backend could not generate a file for this SVG (' +
            reason +
            '). Nothing was downloaded. Check that the backend server is running and that the SVG is valid.'
        );
    }
}

function downloadText(text, filename) {
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

/**
 * Fit bed view to container
 */
function fitView() {
    const { canvasContainer } = elements;
    const bed = document.querySelector('.machine-bed');
    
    if (!canvasContainer || !bed) return;
    
    const padding = 40;
    const availW = canvasContainer.clientWidth - padding * 2;
    const availH = canvasContainer.clientHeight - padding * 2;
    
    if (availW <= 0 || availH <= 0) return;
    
    const scaleW = availW / 500;
    const scaleH = availH / 285;
    const scale = Math.min(scaleW, scaleH, 1); // Don't scale up
    
    bed.style.transform = `scale(${scale})`;
    appState.scale = scale;
}

/**
 * Center job in workspace
 */
function centerJob() {
    if (!appState.svgData || !appState.svgElement) return;
    
    // TODO: Implement centering logic
    fitView();
}

/**
 * Show/hide loading state
 */
function showLoading(show) {
    // TODO: Add loading indicator
    if (show) {
        elements.exportBtn.disabled = true;
    }
}

/**
 * Show error message
 * @param {string} message - Error message
 */
function showError(message) {
    alert(message); // TODO: Replace with better UI
    console.error(message);
}

/**
 * Escape HTML to prevent XSS
 * @param {string} str - String to escape
 * @returns {string} Escaped string
 */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Debounce function calls
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in ms
 * @returns {Function} Debounced function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
