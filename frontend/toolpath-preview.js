/**
 * Toolpath Preview for OKU Desk Laser
 * Renders the *emitted G-code* as an overlay on the machine bed.
 *
 * This deliberately parses the G-code the backend returned rather than the
 * source SVG: the point of the preview is to show what the machine will really
 * do, including cut ordering, per-pass direction alternation and rapid moves.
 * A preview drawn from the SVG would show the intent, not the result, and would
 * hide exactly the class of bug this is meant to expose.
 *
 * Bed coordinates are Y-up with the origin bottom-left; SVG user space is
 * Y-down, so every emitted point is flipped with `BED_H - y`.
 *
 * @version 0.3.0
 */

class ToolpathPreview {
    constructor() {
        this.BED_W = 500;
        this.BED_H = 285;
        this.SVG_NS = 'http://www.w3.org/2000/svg';
        // Matches GCodeGenerator.ZERO_MOVE_THRESHOLD - sub-micron moves are noise.
        this.ZERO_MOVE_THRESHOLD = 0.005;
    }

    /**
     * Parse a G-code program into drawable segments.
     *
     * Handles the dialect gcode_service.py emits: G0 rapids, G1 cuts, M3 S<power>
     * to enable the laser, M5 to disable it. Coordinates are modal - an axis
     * omitted from a move keeps its previous value - and the raster path emits
     * `G1X12.3P<hex>` with no space after the letter, so spacing is optional.
     *
     * The machine starts at the origin, so the opening move off (0,0) counts as
     * real travel (see the matching fix in tests/benchmark_toolpath.py).
     *
     * @param {string} text - Raw G-code
     * @returns {{segments: Array, cutLength: number, rapidLength: number, bounds: Object|null}}
     */
    parse(text) {
        const segments = [];
        let x = 0;
        let y = 0;
        let laserOn = false;
        let power = 0;
        let cutLength = 0;
        let rapidLength = 0;
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        let cutIndex = 0;

        const lines = String(text || '').split(/\r?\n/);

        for (const rawLine of lines) {
            // Strip comments; the `;$M ...` metadata header falls out here too.
            const line = rawLine.split(';')[0].trim();
            if (!line) continue;

            const upper = line.toUpperCase();

            // Laser gating, evaluated before motion so a power change on the
            // same line as a move applies to that move.
            if (/\bM0*5\b/.test(upper)) laserOn = false;
            if (/\bM0*[34]\b/.test(upper)) laserOn = true;

            const sMatch = upper.match(/\bS\s*(-?\d*\.?\d+)/);
            if (sMatch) {
                power = parseFloat(sMatch[1]);
                // S0 is an idiomatic "laser off" even without an M5.
                if (power === 0) laserOn = false;
            }

            const moveMatch = upper.match(/\bG\s*0*([01])\b/);
            if (!moveMatch) continue;

            const isRapid = moveMatch[1] === '0';
            const xMatch = upper.match(/\bX\s*(-?\d*\.?\d+)/);
            const yMatch = upper.match(/\bY\s*(-?\d*\.?\d+)/);
            if (!xMatch && !yMatch) continue;

            const nx = xMatch ? parseFloat(xMatch[1]) : x;
            const ny = yMatch ? parseFloat(yMatch[1]) : y;
            if (!Number.isFinite(nx) || !Number.isFinite(ny)) continue;

            const dist = Math.hypot(nx - x, ny - y);
            // A G1 with the laser off is a positioning move, not a cut.
            const isCut = !isRapid && laserOn;

            if (dist > this.ZERO_MOVE_THRESHOLD) {
                segments.push({
                    x1: x, y1: y, x2: nx, y2: ny,
                    cut: isCut,
                    power,
                    order: isCut ? cutIndex++ : -1
                });
                if (isCut) cutLength += dist; else rapidLength += dist;
            }

            if (isCut) {
                minX = Math.min(minX, x, nx);
                maxX = Math.max(maxX, x, nx);
                minY = Math.min(minY, y, ny);
                maxY = Math.max(maxY, y, ny);
            }

            x = nx;
            y = ny;
        }

        const bounds = Number.isFinite(minX)
            ? { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY }
            : null;

        return { segments, cutLength, rapidLength, bounds };
    }

    /**
     * Map a cut's position in the sequence to a colour, cool (first) to warm
     * (last), so the eye can follow the order the machine actually travels in.
     * @param {number} t - 0..1 position through the cut sequence
     * @returns {string} CSS colour
     */
    orderColor(t) {
        const clamped = Math.max(0, Math.min(1, t));
        const hue = 210 - (210 - 40) * clamped;
        return `hsl(${hue.toFixed(0)}, 85%, 62%)`;
    }

    /**
     * Build the SVG element showing the toolpath over the bed.
     *
     * @param {Object} parsed - Result of parse()
     * @param {Object} [options]
     * @param {boolean} [options.showRapids=true] - Draw non-cutting travel moves
     * @param {boolean} [options.showOrder=true] - Colour cuts by sequence
     * @returns {SVGElement}
     */
    buildSvg(parsed, options = {}) {
        const { showRapids = true, showOrder = true } = options;
        const { segments } = parsed;

        const svg = document.createElementNS(this.SVG_NS, 'svg');
        svg.setAttribute('viewBox', `0 0 ${this.BED_W} ${this.BED_H}`);
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', '100%');
        svg.setAttribute('class', 'toolpath-svg');

        const totalCuts = segments.reduce((n, s) => n + (s.cut ? 1 : 0), 0) || 1;

        const rapidGroup = document.createElementNS(this.SVG_NS, 'g');
        rapidGroup.setAttribute('class', 'toolpath-rapids');
        const cutGroup = document.createElementNS(this.SVG_NS, 'g');
        cutGroup.setAttribute('class', 'toolpath-cuts');

        for (const seg of segments) {
            const isRapid = !seg.cut;
            if (isRapid && !showRapids) continue;

            const line = document.createElementNS(this.SVG_NS, 'line');
            line.setAttribute('x1', String(seg.x1));
            line.setAttribute('y1', String(this.BED_H - seg.y1));
            line.setAttribute('x2', String(seg.x2));
            line.setAttribute('y2', String(this.BED_H - seg.y2));

            if (!isRapid && showOrder) {
                line.setAttribute('stroke', this.orderColor(seg.order / totalCuts));
            }
            // Rapids go in their own group so cuts always draw on top of travel.
            (isRapid ? rapidGroup : cutGroup).appendChild(line);
        }

        svg.appendChild(rapidGroup);
        svg.appendChild(cutGroup);
        return svg;
    }

    /**
     * Render a toolpath into a container, replacing whatever was there.
     *
     * @param {HTMLElement} container - Overlay layer inside .machine-bed
     * @param {string} gcode - Raw G-code text
     * @param {Object} [options] - Passed through to buildSvg()
     * @returns {Object} The parse result, for stats display
     */
    render(container, gcode, options = {}) {
        const parsed = this.parse(gcode);
        container.innerHTML = '';
        container.appendChild(this.buildSvg(parsed, options));
        return parsed;
    }

    /** Remove any rendered toolpath. */
    clear(container) {
        if (container) container.innerHTML = '';
    }
}
