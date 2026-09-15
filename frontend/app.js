/**
 * Main Application Logic for OKU Desk Laser Interface
 * 
 * @version 0.2.2
 */

// Initialize parsers
const svgParser = new SVGParser();
const gcodeGen = new GCodeGenerator();
const toolpathPreview = new ToolpathPreview();

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
    rasterUrl: '/raster',
    // Toolpath preview. lastGcode is cached so Generate can reuse what Preview
    // already fetched instead of paying for a second backend round-trip.
    lastGcode: null,
    lastGcodeFilename: null,
    lastGcodeSignature: null,
    previewVisible: false,
    showRapids: true,
    showOrder: true,
    // U2 view transform. The bed uses transform-origin 0 0, so the mapping is
    // screen = bedLayoutOrigin + translate + scale * bedPoint.
    view: { scale: 1, tx: 0, ty: 0 },
    viewTouched: false
};

const MIN_SCALE = 0.1;
const MAX_SCALE = 8;
const BED_W_MM = 500;
const BED_H_MM = 285;
const SVG_NS = 'http://www.w3.org/2000/svg';

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
        previewBtn: document.getElementById('previewBtn'),
        loadedFile: document.getElementById('loadedFile'),
        loadedFileName: document.getElementById('loadedFileName'),
        removeFileBtn: document.getElementById('removeFileBtn'),
        toolpathLayer: document.getElementById('toolpathLayer'),
        toggleRapidsBtn: document.getElementById('toggleRapidsBtn'),
        toggleOrderBtn: document.getElementById('toggleOrderBtn'),
        clearPreviewBtn: document.getElementById('clearPreviewBtn'),
        statCut: document.getElementById('statCut'),
        statRapid: document.getElementById('statRapid'),
        statCutRow: document.getElementById('statCutRow'),
        statRapidRow: document.getElementById('statRapidRow'),
        statDim: document.getElementById('statDim'),
        statTime: document.getElementById('statTime'),
        statsPanel: document.getElementById('statsPanel'),
        travelSpeed: document.getElementById('travelSpeed'),
        fitViewBtn: document.getElementById('fitViewBtn'),
        centerJobBtn: document.getElementById('centerJobBtn'),
        canvasContainer: document.getElementById('canvasContainer'),
        zoomInBtn: document.getElementById('zoomInBtn'),
        zoomOutBtn: document.getElementById('zoomOutBtn'),
        zoomLevel: document.getElementById('zoomLevel'),
        errorBanner: document.getElementById('errorBanner'),
        errorBannerText: document.getElementById('errorBannerText'),
        errorBannerClose: document.getElementById('errorBannerClose'),
        loadingOverlay: document.getElementById('loadingOverlay'),
        loadingText: document.getElementById('loadingText'),
        dragHint: document.getElementById('dragHint'),
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
    setupPanZoom();
    setupDragToPlace();
    setupMaterialPresets();
    setupProjectLinks().finally(() => {
        maybeShowFirstRunModal();
    });

    // Initial view fit
    requestAnimationFrame(() => fitView());
    window.addEventListener('resize', debounce(() => {
        if (appState.viewTouched) applyView(); else fitView();
    }, 250));
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

    if (elements.previewBtn) {
        elements.previewBtn.addEventListener('click', previewToolpath);
    }
    if (elements.removeFileBtn) {
        elements.removeFileBtn.addEventListener('click', clearFile);
    }
    if (elements.toggleRapidsBtn) {
        elements.toggleRapidsBtn.addEventListener('click', () => {
            appState.showRapids = !appState.showRapids;
            redrawToolpath();
        });
    }
    if (elements.toggleOrderBtn) {
        elements.toggleOrderBtn.addEventListener('click', () => {
            appState.showOrder = !appState.showOrder;
            redrawToolpath();
        });
    }
    if (elements.clearPreviewBtn) {
        elements.clearPreviewBtn.addEventListener('click', clearToolpath);
    }
}

/**
 * Setup control buttons
 */
function setupControls() {
    if (elements.zoomInBtn) {
        elements.zoomInBtn.addEventListener('click', () => zoomBy(1.25));
    }
    if (elements.zoomOutBtn) {
        elements.zoomOutBtn.addEventListener('click', () => zoomBy(1 / 1.25));
    }
    if (elements.errorBannerClose) {
        elements.errorBannerClose.addEventListener('click', hideError);
    }
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
                updateOriginMarker();
                if (appState.svgData) renderWorkspace(appState.svgData);
            });
        }
        if (elements.originY) {
            elements.originY.addEventListener('input', () => {
                appState.originY = parseFloat(elements.originY.value) || 0;
                updateOriginMarker();
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

    // "Score outline" is a light vector pass along the same paths - not raster
    // engraving. Calling it "Engrave" here read as the raster mode's engraving,
    // which is a different operation on a different kind of file.
    el.textContent = mode === 'cut'
        ? `Cut through: speed ${speedTxt}, power ${powerTxt}, ${passesTxt}${depthTxt}.`
        : `Score outline: a light single pass along the vector paths - ` +
          `speed ${speedTxt}, power ${powerTxt}. ` +
          `For photo or greyscale engraving of an image, use Raster mode instead.`;
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
        const x = Math.min(Math.max(appState.originX, 0), BED_W_MM);
        // No flip here: `bottom` is already measured up from the bed's bottom
        // edge, which is the same direction originY uses. Subtracting from the
        // bed height mirrored the marker vertically.
        const y = Math.min(Math.max(appState.originY, 0), BED_H_MM);
        m.style.left = `${(x / BED_W_MM) * 100}%`;
        m.style.bottom = `${(y / BED_H_MM) * 100}%`;
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
        if (elements.previewBtn) elements.previewBtn.disabled = false;
        setDragToPlaceEnabled(true);
        elements.statsPanel.style.display = 'block';

        if (elements.loadedFileName) {
            elements.loadedFileName.textContent = file.name;
            elements.loadedFileName.title = file.name;
        }
        if (elements.loadedFile) elements.loadedFile.hidden = false;

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
    // The overlay describes the previous job's G-code; drop it rather than
    // leave a toolpath on screen that no longer matches what is loaded.
    clearToolpath();
    appState.lastGcode = null;
    appState.lastGcodeFilename = null;
    appState.lastGcodeSignature = null;
    updateOriginMarker();

    // Create bed SVG container
    const bedSvg = document.createElementNS(SVG_NS, 'svg');
    bedSvg.setAttribute('viewBox', `0 0 ${BED_W_MM} ${BED_H_MM}`);
    bedSvg.setAttribute('width', '100%');
    bedSvg.setAttribute('height', '100%');

    // Placement comes from getJobPlacement() rather than a second copy of the
    // origin switch. Two copies of this logic is how the preview and the cut
    // file drifted apart before (see the custom-origin fix).
    const place = getJobPlacement();
    if (!place) {
        elements.svgLayer.appendChild(bedSvg);
        appState.svgElement = bedSvg;
        return;
    }

    // Clone user SVG and position it
    const userSvg = data.element.cloneNode(true);
    userSvg.setAttribute('x', String(place.x));
    userSvg.setAttribute('y', String(place.y));
    userSvg.setAttribute('width', String(place.w));
    userSvg.setAttribute('height', String(place.h));
    userSvg.removeAttribute('id');
    // Stroke/fill are normalised to white by CSS via this class: an imported
    // SVG can carry any colour, including black, which is invisible on the
    // dark bed.
    userSvg.setAttribute('class', 'user-svg');

    bedSvg.appendChild(userSvg);
    bedSvg.appendChild(buildJobBounds(place));

    elements.svgLayer.appendChild(bedSvg);
    // After insertion: normalizeArtworkColors reads getComputedStyle, which
    // only resolves inheritance once the node is in the document.
    normalizeArtworkColors(userSvg);
    appState.svgElement = bedSvg;
}


/* ============================================================
   ARTWORK COLOUR NORMALISATION
   ============================================================ */

// The machine bed's background (--bed-bg). Artwork contrast is measured
// against this, not against black.
const BED_BG_RGB = { r: 0x0d, g: 0x11, b: 0x17 };
// WCAG-style contrast floor, verified against the bed background by porting
// this maths to Python and checking real colours. 3.0 (the graphics threshold)
// left black at #616161, too dim for a hairline stroke; 4.5 lifts it to #808080
// while leaving already-bright colours such as pure red untouched.
const MIN_ARTWORK_CONTRAST = 4.5;

/**
 * Parse a CSS colour into RGB. Handles the rgb()/rgba() forms getComputedStyle
 * returns, plus hex literals. Returns null for none/transparent/unparseable.
 * @param {string} value
 * @returns {{r: number, g: number, b: number}|null}
 */
function parseCssColor(value) {
    if (!value) return null;
    const v = String(value).trim().toLowerCase();
    if (!v || v === 'none' || v === 'transparent') return null;

    const fn = v.match(/^rgba?\(([^)]+)\)$/);
    if (fn) {
        const parts = fn[1].split(/[\s,/]+/).filter(Boolean);
        if (parts.length < 3) return null;
        // A fully transparent colour carries no visual information.
        if (parts.length >= 4 && parseFloat(parts[3]) === 0) return null;
        const [r, g, b] = parts.slice(0, 3).map(n => parseInt(n, 10));
        if ([r, g, b].some(n => !Number.isFinite(n))) return null;
        return { r, g, b };
    }

    let hex = v.startsWith('#') ? v.slice(1) : null;
    if (hex && hex.length === 3) hex = hex.split('').map(c => c + c).join('');
    if (hex && hex.length === 6 && /^[0-9a-f]{6}$/.test(hex)) {
        return {
            r: parseInt(hex.slice(0, 2), 16),
            g: parseInt(hex.slice(2, 4), 16),
            b: parseInt(hex.slice(4, 6), 16)
        };
    }
    return null;
}

/**
 * WCAG relative luminance.
 * @param {{r: number, g: number, b: number}} rgb
 * @returns {number} 0..1
 */
function relativeLuminance(rgb) {
    const channel = (c) => {
        const x = c / 255;
        return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b);
}

/**
 * WCAG contrast ratio between two colours.
 * @returns {number} 1..21
 */
function contrastRatio(a, b) {
    const la = relativeLuminance(a);
    const lb = relativeLuminance(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** @returns {{h: number, s: number, l: number}} h in 0..360, s/l in 0..1 */
function rgbToHsl({ r, g, b }) {
    const rn = r / 255, gn = g / 255, bn = b / 255;
    const max = Math.max(rn, gn, bn), min = Math.min(rn, gn, bn);
    const l = (max + min) / 2;
    const d = max - min;
    if (d === 0) return { h: 0, s: 0, l };
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    let h;
    if (max === rn) h = ((gn - bn) / d) % 6;
    else if (max === gn) h = (bn - rn) / d + 2;
    else h = (rn - gn) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
    return { h, s, l };
}

/** @returns {{r: number, g: number, b: number}} */
function hslToRgb({ h, s, l }) {
    const c = (1 - Math.abs(2 * l - 1)) * s;
    const hp = h / 60;
    const x = c * (1 - Math.abs((hp % 2) - 1));
    let rgb;
    if (hp < 1) rgb = [c, x, 0];
    else if (hp < 2) rgb = [x, c, 0];
    else if (hp < 3) rgb = [0, c, x];
    else if (hp < 4) rgb = [0, x, c];
    else if (hp < 5) rgb = [x, 0, c];
    else rgb = [c, 0, x];
    const m = l - c / 2;
    return {
        r: Math.round((rgb[0] + m) * 255),
        g: Math.round((rgb[1] + m) * 255),
        b: Math.round((rgb[2] + m) * 255)
    };
}

/**
 * Raise a colour's lightness until it reads against the bed, keeping its hue
 * and saturation so the layer stays recognisable. A black stroke has no hue,
 * so it lifts to near-white; a navy lifts to a bright blue, not to white.
 *
 * @param {{r: number, g: number, b: number}} rgb
 * @returns {{r: number, g: number, b: number}}
 */
function liftForContrast(rgb) {
    if (contrastRatio(rgb, BED_BG_RGB) >= MIN_ARTWORK_CONTRAST) return rgb;

    const hsl = rgbToHsl(rgb);
    // Walk lightness up in small steps rather than solving analytically: the
    // luminance curve is per-channel and hue-dependent, so stepping is both
    // simpler and predictable.
    for (let l = hsl.l; l <= 0.92; l += 0.02) {
        const candidate = hslToRgb({ h: hsl.h, s: hsl.s, l });
        if (contrastRatio(candidate, BED_BG_RGB) >= MIN_ARTWORK_CONTRAST) {
            return candidate;
        }
    }
    return hslToRgb({ h: hsl.h, s: hsl.s, l: 0.92 });
}

/** @returns {string} CSS hex */
function rgbToCss({ r, g, b }) {
    const hx = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
    return `#${hx(r)}${hx(g)}${hx(b)}`;
}

const ARTWORK_SHAPES = 'path, rect, circle, ellipse, line, polyline, polygon';

/**
 * Give every shape in the imported artwork an explicit, legible stroke.
 *
 * Per-layer colour is the point: a job is identified by its colour in the
 * sidebar, so recolouring everything to one value would throw that away. Only
 * colours that fail the contrast floor against the bed are lifted, and they
 * keep their hue - a dark red stays red.
 *
 * Must run after the node is in the document: it reads getComputedStyle, which
 * is what resolves inherited stroke from parent <g> elements and any <style>
 * block inside the imported file.
 *
 * @param {SVGElement} root - The cloned user SVG, already attached to the DOM
 */
function normalizeArtworkColors(root) {
    if (!root) return;
    const shapes = root.querySelectorAll(ARTWORK_SHAPES);

    for (const el of shapes) {
        const computed = window.getComputedStyle(el);
        // Mirrors the backend's _element_color(): stroke wins, fill is the
        // fallback for shapes drawn as filled areas.
        const source = parseCssColor(computed.stroke) || parseCssColor(computed.fill);
        const colour = source ? rgbToCss(liftForContrast(source)) : null;

        // setProperty with 'important' is required: source SVGs commonly carry
        // stroke in an inline style attribute, which outranks a stylesheet rule.
        el.style.setProperty('stroke', colour || 'var(--artwork-stroke)', 'important');
        el.style.setProperty('fill', 'none', 'important');
    }
}

/**
 * A bounding outline around the imported artwork, so its position and extent
 * on the bed are obvious at a glance.
 *
 * @param {{x: number, y: number, w: number, h: number}} place - Bed coords, SVG y-down
 * @returns {SVGElement}
 */
function buildJobBounds(place) {
    const group = document.createElementNS(SVG_NS, 'g');
    group.setAttribute('class', 'job-bounds');

    const rect = document.createElementNS(SVG_NS, 'rect');
    rect.setAttribute('x', String(place.x));
    rect.setAttribute('y', String(place.y));
    rect.setAttribute('width', String(Math.max(place.w, 0)));
    rect.setAttribute('height', String(Math.max(place.h, 0)));
    group.appendChild(rect);

    // Solid corner brackets read as deliberate registration marks and stay
    // legible when the dashed rect gets small at low zoom.
    const arm = Math.max(Math.min(place.w, place.h) * 0.12, 2);
    const corners = [
        [place.x, place.y, 1, 1],
        [place.x + place.w, place.y, -1, 1],
        [place.x, place.y + place.h, 1, -1],
        [place.x + place.w, place.y + place.h, -1, -1]
    ];
    for (const [cx, cy, sx, sy] of corners) {
        const path = document.createElementNS(SVG_NS, 'path');
        path.setAttribute('d',
            `M ${cx + sx * arm} ${cy} L ${cx} ${cy} L ${cx} ${cy + sy * arm}`);
        path.setAttribute('class', 'job-bounds-corner');
        group.appendChild(path);
    }

    return group;
}

/**
 * Render job cards in sidebar
 * @param {Array} jobs - Array of job objects
 */
/**
 * Unload the current file and return the workspace to its empty state.
 *
 * Everything derived from the file goes together - artwork, job list, cached
 * G-code and the toolpath overlay. Leaving any of it behind would show data
 * belonging to a file that is no longer open.
 */
function clearFile() {
    appState.svgData = null;
    appState.svgElement = null;
    appState.lastGcode = null;
    appState.lastGcodeFilename = null;
    appState.lastGcodeSignature = null;

    clearToolpath();
    if (elements.svgLayer) elements.svgLayer.innerHTML = '';

    if (elements.jobsContainer) {
        elements.jobsContainer.innerHTML = '<div class="empty-state">No file loaded</div>';
    }
    if (elements.statsPanel) elements.statsPanel.style.display = 'none';
    if (elements.statDim) elements.statDim.textContent = '—';
    if (elements.statTime) elements.statTime.textContent = '—';

    if (elements.exportBtn) elements.exportBtn.disabled = true;
    if (elements.previewBtn) elements.previewBtn.disabled = true;
    setDragToPlaceEnabled(false);

    if (elements.loadedFile) elements.loadedFile.hidden = true;
    if (elements.loadedFileName) {
        elements.loadedFileName.textContent = '—';
        elements.loadedFileName.title = '';
    }
    // Reset the input, or picking the same file again fires no change event.
    if (elements.fileInput) elements.fileInput.value = '';

    hideError();
}

/**
 * Explain an empty job list.
 *
 * "No paths found" is true but useless: the file usually does contain shapes,
 * and the reason none became a job is specific and fixable. A job needs a
 * resolvable colour, and neither this parser nor the backend implements a CSS
 * cascade, so shapes styled through a <style> block resolve to nothing.
 *
 * @returns {string}
 */
function explainNoJobs() {
    const stats = appState.svgData && appState.svgData.stats;
    if (!stats) return 'No paths found in SVG';

    if (stats.uncoloured > 0 && (stats.hasStyleBlock || stats.classStyled > 0)) {
        return `Found ${stats.uncoloured} shape(s), but their colours come from a ` +
            `<style> block or CSS classes, which this tool does not read. ` +
            `Re-export with presentation attributes ("plain SVG" in Inkscape), or ` +
            `set a stroke colour on the shapes directly.`;
    }
    if (stats.uncoloured > 0) {
        return `Found ${stats.uncoloured} shape(s), but none has a stroke or fill ` +
            `colour. Give each shape a stroke colour - layers are identified by colour.`;
    }
    return 'No drawable shapes found in this SVG (paths, rects, circles, lines or polygons).';
}

function renderJobs(jobs) {
    if (!jobs || jobs.length === 0) {
        elements.jobsContainer.innerHTML =
            `<div class="empty-state">${escapeHtml(explainNoJobs())}</div>`;
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
        showLoading(true);
        generateViaBackend(travelSpeed);

    } catch (err) {
        console.error('Error generating G-code:', err);
        showError('Error generating G-code: ' + err.message);
    }
}

/**
 * Build the request payload for the backend generator.
 * @param {number} travelSpeed
 * @returns {Object}
 */
function buildGeneratePayload(travelSpeed) {
    const svgString = appState.svgData?.svgString;
    if (!svgString) throw new Error('Missing SVG source');

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
    return payload;
}

/**
 * Fetch G-code from the backend, reusing the cached result only when the
 * request is byte-for-byte the one that produced it.
 *
 * The cache key is the serialised payload rather than a dirty flag: a preview
 * the user saw must never be downloadable as a file that was generated from
 * different settings. If anything about the job changed, we re-fetch.
 *
 * @param {number} travelSpeed
 * @returns {Promise<{gcode: string, filename: string}>}
 */
async function requestGcode(travelSpeed) {
    const payload = buildGeneratePayload(travelSpeed);
    const signature = JSON.stringify(payload);

    if (appState.lastGcode && appState.lastGcodeSignature === signature) {
        return { gcode: appState.lastGcode, filename: appState.lastGcodeFilename };
    }

    const res = await fetch('/api/generate-vector-advanced', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!(res.ok && data && data.success && data.gcode)) {
        throw new Error(data?.error || data?.details || 'Backend generation failed');
    }

    appState.lastGcode = data.gcode;
    appState.lastGcodeFilename = data.filename || 'oku-job.gco';
    appState.lastGcodeSignature = signature;
    return { gcode: appState.lastGcode, filename: appState.lastGcodeFilename };
}

async function generateViaBackend(travelSpeed) {
    try {
        const { gcode, filename } = await requestGcode(travelSpeed);
        downloadText(gcode, filename);
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
    } finally {
        showLoading(false);
    }
}

/**
 * Generate G-code and draw it over the bed without downloading anything.
 */
async function previewToolpath() {
    if (!appState.svgData) {
        showError('No file loaded');
        return;
    }

    const travelSpeed = parseInt(elements.travelSpeed.value) || 5000;
    showLoading(true);

    try {
        const { gcode } = await requestGcode(travelSpeed);
        appState.previewVisible = true;
        redrawToolpath();
    } catch (e) {
        const reason = e?.message || String(e);
        showError(
            'Could not preview the toolpath: the backend failed to generate G-code (' +
            reason +
            '). The preview shows the real emitted G-code, so there is nothing to draw ' +
            'until generation succeeds.'
        );
    } finally {
        showLoading(false);
    }
}

/**
 * Redraw the cached toolpath with the current display toggles.
 */
function redrawToolpath() {
    if (!appState.previewVisible || !appState.lastGcode || !elements.toolpathLayer) return;

    const parsed = toolpathPreview.render(elements.toolpathLayer, appState.lastGcode, {
        showRapids: appState.showRapids,
        showOrder: appState.showOrder
    });

    updateToolpathStats(parsed);
    syncToolpathControls();
}

/**
 * Remove the preview overlay and reset its controls.
 */
function clearToolpath() {
    appState.previewVisible = false;
    toolpathPreview.clear(elements.toolpathLayer);
    if (elements.statCutRow) elements.statCutRow.style.display = 'none';
    if (elements.statRapidRow) elements.statRapidRow.style.display = 'none';
    syncToolpathControls();
}

/**
 * Show measured cut and travel distance from the parsed toolpath.
 * @param {Object} parsed - Result of ToolpathPreview.parse()
 */
function updateToolpathStats(parsed) {
    if (elements.statCut) {
        elements.statCut.textContent = `${parsed.cutLength.toFixed(1)} mm`;
    }
    if (elements.statRapid) {
        elements.statRapid.textContent = `${parsed.rapidLength.toFixed(1)} mm`;
    }
    if (elements.statCutRow) elements.statCutRow.style.display = '';
    if (elements.statRapidRow) elements.statRapidRow.style.display = '';
}

/**
 * Keep the toolpath control buttons in sync with state.
 */
function syncToolpathControls() {
    const on = appState.previewVisible;
    const set = (btn, enabled, pressed) => {
        if (!btn) return;
        btn.disabled = !enabled;
        if (pressed !== undefined) btn.setAttribute('aria-pressed', String(pressed));
        btn.classList.toggle('active', Boolean(pressed) && enabled);
    };
    set(elements.toggleRapidsBtn, on, appState.showRapids);
    set(elements.toggleOrderBtn, on, appState.showOrder);
    set(elements.clearPreviewBtn, on);
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
/**
 * The machine bed's unscaled layout origin inside the canvas container.
 * offsetLeft/Top are unaffected by transforms, so this stays stable while
 * panning and zooming.
 * @returns {{x: number, y: number}|null}
 */
function getBedLayoutOrigin() {
    const bed = document.querySelector('.machine-bed');
    if (!bed) return null;
    return { x: bed.offsetLeft, y: bed.offsetTop };
}

/**
 * Push the current view transform onto the bed.
 */
function applyView() {
    const bed = document.querySelector('.machine-bed');
    if (!bed) return;
    const { scale, tx, ty } = appState.view;
    bed.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    // Mirrored onto appState.scale, which is what the drag-to-place maths reads
    // to convert screen pixels back to millimetres.
    appState.scale = scale;
    if (elements.zoomLevel) {
        elements.zoomLevel.textContent = `${Math.round(scale * 100)}%`;
    }
}

/**
 * Fit the whole bed in the viewport and centre it.
 */
function fitView() {
    const { canvasContainer } = elements;
    const origin = getBedLayoutOrigin();
    if (!canvasContainer || !origin) return;

    const padding = 40;
    const availW = canvasContainer.clientWidth - padding * 2;
    const availH = canvasContainer.clientHeight - padding * 2;
    if (availW <= 0 || availH <= 0) return;

    // Fit only - never scale a small bed up past 1:1 on load.
    const scale = Math.min(availW / BED_W_MM, availH / BED_H_MM, 1);
    appState.viewTouched = false;
    centreAt(scale);
}

/**
 * Centre the bed in the container at a given scale.
 * @param {number} scale
 */
function centreAt(scale) {
    const { canvasContainer } = elements;
    const origin = getBedLayoutOrigin();
    if (!canvasContainer || !origin) return;

    appState.view.scale = clampScale(scale);
    const s = appState.view.scale;
    appState.view.tx = (canvasContainer.clientWidth - BED_W_MM * s) / 2 - origin.x;
    appState.view.ty = (canvasContainer.clientHeight - BED_H_MM * s) / 2 - origin.y;
    applyView();
}

/** @param {number} s @returns {number} */
function clampScale(s) {
    return Math.max(MIN_SCALE, Math.min(MAX_SCALE, s));
}

/**
 * Zoom about a fixed point so whatever is under the cursor stays put.
 *
 * With transform-origin 0 0: screen = origin + t + s * bedPoint, so the bed
 * point under the cursor is p = (screen - origin - t) / s, and holding it fixed
 * across a scale change gives t' = screen - origin - s' * p.
 *
 * @param {number} factor - Multiplier applied to the current scale
 * @param {number} [clientX] - Anchor in viewport coords; defaults to container centre
 * @param {number} [clientY]
 */
function zoomBy(factor, clientX, clientY) {
    const { canvasContainer } = elements;
    const origin = getBedLayoutOrigin();
    if (!canvasContainer || !origin) return;

    const rect = canvasContainer.getBoundingClientRect();
    const mx = (clientX === undefined ? rect.left + rect.width / 2 : clientX) - rect.left;
    const my = (clientY === undefined ? rect.top + rect.height / 2 : clientY) - rect.top;

    const { scale: s, tx, ty } = appState.view;
    const next = clampScale(s * factor);
    if (next === s) return;

    const px = (mx - origin.x - tx) / s;
    const py = (my - origin.y - ty) / s;

    appState.view.scale = next;
    appState.view.tx = mx - origin.x - next * px;
    appState.view.ty = my - origin.y - next * py;
    appState.viewTouched = true;
    applyView();
}

/**
 * Centre the view on the loaded job rather than on the bed.
 *
 * Previously a stub that just called fitView(), so the button did nothing
 * useful once a job was loaded off-centre.
 */
function centerJob() {
    const { canvasContainer } = elements;
    const origin = getBedLayoutOrigin();
    if (!appState.svgData || !canvasContainer || !origin) {
        fitView();
        return;
    }

    const place = getJobPlacement();
    if (!place) {
        fitView();
        return;
    }

    const padding = 60;
    const availW = canvasContainer.clientWidth - padding * 2;
    const availH = canvasContainer.clientHeight - padding * 2;
    if (availW <= 0 || availH <= 0) return;

    // Zoom to the job, but never past 1:1 and never below the fit-whole-bed scale.
    const jobW = Math.max(place.w, 1);
    const jobH = Math.max(place.h, 1);
    const scale = clampScale(Math.min(availW / jobW, availH / jobH, 1));

    // Job centre in bed coordinates (SVG y-down, matching renderWorkspace).
    const cx = place.x + jobW / 2;
    const cy = place.y + jobH / 2;

    appState.view.scale = scale;
    appState.view.tx = canvasContainer.clientWidth / 2 - origin.x - scale * cx;
    appState.view.ty = canvasContainer.clientHeight / 2 - origin.y - scale * cy;
    appState.viewTouched = true;
    applyView();
}

/**
 * Where the job sits on the bed, in bed coordinates (SVG y-down).
 *
 * Single source of truth for placement - renderWorkspace(), centerJob() and
 * drag-to-place all read it. It used to be duplicated in renderWorkspace, and
 * placement logic drifting between two copies is what put the workspace preview
 * and the emitted G-code in different places (see the custom-origin fix).
 *
 * @returns {{x: number, y: number, w: number, h: number}|null}
 */
function getJobPlacement() {
    const data = appState.svgData;
    if (!data || !data.dimensions) return null;

    const w = data.dimensions.width;
    const h = data.dimensions.height;
    let x = 0;
    let y = BED_H_MM - h;

    switch (appState.originMode) {
        case 'top-left':     x = 0;                    y = 0;                    break;
        case 'top-right':    x = BED_W_MM - w;         y = 0;                    break;
        case 'bottom-right': x = BED_W_MM - w;         y = BED_H_MM - h;         break;
        case 'center':       x = (BED_W_MM - w) / 2;   y = (BED_H_MM - h) / 2;   break;
        case 'custom':
            x = Math.max(0, Math.min(appState.originX, BED_W_MM - w));
            y = Math.max(0, Math.min(BED_H_MM - appState.originY - h, BED_H_MM - h));
            break;
        default:             x = 0;                    y = BED_H_MM - h;
    }
    return { x, y, w, h };
}

/**
 * U2: wheel zoom and drag panning on the workspace.
 */
function setupPanZoom() {
    const { canvasContainer } = elements;
    if (!canvasContainer) return;

    canvasContainer.addEventListener('wheel', (e) => {
        e.preventDefault();
        // Normalise across deltaMode (lines vs pixels) so a trackpad and a
        // mouse wheel feel roughly the same.
        const unit = e.deltaMode === 1 ? 16 : 1;
        const factor = Math.exp(-e.deltaY * unit * 0.0015);
        zoomBy(factor, e.clientX, e.clientY);
    }, { passive: false });

    let panning = false;
    let lastX = 0;
    let lastY = 0;
    let pointerId = null;

    canvasContainer.addEventListener('pointerdown', (e) => {
        // Left button only, and not when a job drag has claimed the event.
        if (e.button !== 0 || e.defaultPrevented) return;
        panning = true;
        pointerId = e.pointerId;
        lastX = e.clientX;
        lastY = e.clientY;
        canvasContainer.classList.add('is-panning');
        canvasContainer.setPointerCapture(pointerId);
    });

    canvasContainer.addEventListener('pointermove', (e) => {
        if (!panning || e.pointerId !== pointerId) return;
        appState.view.tx += e.clientX - lastX;
        appState.view.ty += e.clientY - lastY;
        lastX = e.clientX;
        lastY = e.clientY;
        appState.viewTouched = true;
        applyView();
    });

    const endPan = (e) => {
        if (!panning || (pointerId !== null && e.pointerId !== pointerId)) return;
        panning = false;
        canvasContainer.classList.remove('is-panning');
        if (pointerId !== null && canvasContainer.hasPointerCapture(pointerId)) {
            canvasContainer.releasePointerCapture(pointerId);
        }
        pointerId = null;
    };
    canvasContainer.addEventListener('pointerup', endPan);
    canvasContainer.addEventListener('pointercancel', endPan);

    // Keyboard zoom, so the workspace is not mouse-only.
    canvasContainer.setAttribute('tabindex', '0');
    canvasContainer.addEventListener('keydown', (e) => {
        if (e.key === '+' || e.key === '=') { e.preventDefault(); zoomBy(1.2); }
        else if (e.key === '-' || e.key === '_') { e.preventDefault(); zoomBy(1 / 1.2); }
        else if (e.key === '0') { e.preventDefault(); fitView(); }
    });
}

/**
 * U4: drag the job on the bed to place it, switching to custom origin.
 */
function setupDragToPlace() {
    const layer = elements.svgLayer;
    if (!layer) return;

    let dragging = false;
    let startX = 0;
    let startY = 0;
    let startOriginX = 0;
    let startOriginY = 0;
    let pointerId = null;

    layer.addEventListener('pointerdown', (e) => {
        if (e.button !== 0 || !appState.svgData) return;
        // Claim the event so setupPanZoom's handler ignores it.
        e.preventDefault();
        e.stopPropagation();

        const place = getJobPlacement();
        if (!place) return;

        dragging = true;
        pointerId = e.pointerId;
        startX = e.clientX;
        startY = e.clientY;

        // Seed custom coordinates from wherever the job currently sits, so the
        // first drag from a preset origin does not jump.
        startOriginX = place.x;
        startOriginY = BED_H_MM - place.y - place.h;

        layer.classList.add('is-dragging');
        layer.setPointerCapture(pointerId);
    });

    layer.addEventListener('pointermove', (e) => {
        if (!dragging || e.pointerId !== pointerId) return;

        const place = getJobPlacement();
        if (!place) return;

        // 1 bed pixel is 1 mm, so screen delta / scale converts straight to mm.
        const s = appState.view.scale || 1;
        const dxMm = (e.clientX - startX) / s;
        const dyMm = (e.clientY - startY) / s;

        // Screen Y is down; origin Y is measured up from the bed's bottom edge.
        const maxX = Math.max(0, BED_W_MM - place.w);
        const maxY = Math.max(0, BED_H_MM - place.h);
        appState.originX = Math.max(0, Math.min(startOriginX + dxMm, maxX));
        appState.originY = Math.max(0, Math.min(startOriginY - dyMm, maxY));

        switchToCustomOrigin();
        renderWorkspace(appState.svgData);
        updateOriginMarker();
    });

    const endDrag = (e) => {
        if (!dragging || (pointerId !== null && e.pointerId !== pointerId)) return;
        dragging = false;
        layer.classList.remove('is-dragging');
        if (pointerId !== null && layer.hasPointerCapture(pointerId)) {
            layer.releasePointerCapture(pointerId);
        }
        pointerId = null;
    };
    layer.addEventListener('pointerup', endDrag);
    layer.addEventListener('pointercancel', endDrag);
}

/**
 * Flip the origin control to "custom" and sync its inputs to appState.
 */
function switchToCustomOrigin() {
    if (appState.originMode !== 'custom') {
        appState.originMode = 'custom';
        if (elements.originInputs) {
            elements.originInputs.forEach(i => { i.checked = (i.value === 'custom'); });
        }
        updateCustomOriginVisibility();
    }
    if (elements.originX) elements.originX.value = appState.originX.toFixed(1);
    if (elements.originY) elements.originY.value = appState.originY.toFixed(1);
}

/**
 * Enable or disable job dragging depending on whether a job is loaded.
 * @param {boolean} enabled
 */
function setDragToPlaceEnabled(enabled) {
    if (elements.svgLayer) elements.svgLayer.classList.toggle('is-draggable', enabled);
    if (elements.dragHint) elements.dragHint.hidden = !enabled;
}


/**
 * Show/hide loading state
 */
function showLoading(show) {
    // Both buttons are disabled while a request is in flight. This used to be
    // one-way - showLoading(false) did nothing - which left the export button
    // permanently disabled after the first generation.
    const busy = Boolean(show);
    const hasFile = Boolean(appState.svgData);

    if (elements.exportBtn) {
        elements.exportBtn.disabled = busy || !hasFile;
        elements.exportBtn.classList.toggle('is-busy', busy);
    }
    if (elements.previewBtn) {
        elements.previewBtn.disabled = busy || !hasFile;
    }
    if (elements.canvasContainer) {
        elements.canvasContainer.setAttribute('aria-busy', String(busy));
    }
    if (elements.loadingOverlay) {
        elements.loadingOverlay.hidden = !busy;
    }
    if (busy) hideError();
}

/**
 * Show error message
 * @param {string} message - Error message
 */
function showError(message) {
    console.error(message);

    const { errorBanner, errorBannerText } = elements;
    if (!errorBanner || !errorBannerText) {
        // Last resort only: an alert() is better than swallowing a failure that
        // may mean the operator is about to cut the wrong thing.
        alert(message);
        return;
    }
    errorBannerText.textContent = message;
    errorBanner.hidden = false;
}

/**
 * Dismiss the error banner.
 */
function hideError() {
    if (elements.errorBanner) elements.errorBanner.hidden = true;
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
