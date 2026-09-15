/**
 * SVG Parser for OKU Desk Laser Interface
 * Extracts paths from SVG files and groups them by stroke color
 * 
 * @version 0.2.1
 */

class SVGParser {
    constructor() {
        this.DPI = 96.0;
        this.MM_PER_INCH = 25.4;
    }

    /**
     * Parse SVG file and extract job data
     * @param {File} file - SVG file object
     * @returns {Promise<Object>} Parsed SVG data with dimensions and jobs
     */
    async parseSVG(file) {
        if (!file || !file.name.endsWith('.svg')) {
            throw new Error('Invalid file: expected SVG file');
        }

        const text = await file.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(text, 'image/svg+xml');

        // Check for parsing errors
        const parserError = doc.querySelector('parsererror');
        if (parserError) {
            throw new Error('SVG parsing error: ' + parserError.textContent);
        }

        const svg = doc.querySelector('svg');
        if (!svg) {
            throw new Error('No SVG element found in file');
        }

        // Get dimensions
        const dimensions = this.getDimensions(svg);

        // Extract paths recursively. `stats` records shapes that were found but
        // could not be assigned a colour, so the UI can explain a empty result.
        const stats = { uncoloured: 0, classStyled: 0 };
        const paths = this.extractPaths(svg, null, stats);

        return {
            element: svg,
            svgString: text,
            dimensions: dimensions,
            jobs: this.groupPathsByColor(paths),
            stats: {
                uncoloured: stats.uncoloured,
                classStyled: stats.classStyled,
                // Neither parser implements a CSS cascade, so a file that styles
                // its shapes through a <style> block resolves to no colours.
                hasStyleBlock: Boolean(svg.querySelector('style'))
            }
        };
    }

    /**
     * Get SVG dimensions in mm
     * @param {SVGElement} svg - SVG root element
     * @returns {Object} {width, height} in mm
     */
    getDimensions(svg) {
        let widthStr = svg.getAttribute('width');
        let heightStr = svg.getAttribute('height');
        const viewBox = svg.getAttribute('viewBox');

        // Parse viewBox if dimensions not specified
        if (viewBox) {
            const vb = viewBox.split(/[\s,]+/).map(parseFloat).filter(n => !isNaN(n));
            if (vb.length >= 4) {
                // viewBox format: "x y width height"
                if (!widthStr) widthStr = String(vb[2]);
                if (!heightStr) heightStr = String(vb[3]);
            }
        }

        const width = this.toMM(widthStr || '100');
        const height = this.toMM(heightStr || '100');

        return { width, height };
    }

    /**
     * Convert value string to millimeters
     * @param {string|number} valStr - Value with optional unit
     * @returns {number} Value in millimeters
     */
    toMM(valStr) {
        if (typeof valStr === 'number') return valStr;
        if (!valStr) return 0;

        const val = parseFloat(valStr);
        if (isNaN(val)) return 0;

        const str = String(valStr).toLowerCase().trim();

        // Handle percentages (would need parent context, simplified here)
        if (str.includes('%')) {
            // For now, treat as pixels (will need parent size for real %)
            return val * (this.MM_PER_INCH / this.DPI);
        }

        // Handle units
        if (str.includes('mm')) return val;
        if (str.includes('cm')) return val * 10;
        if (str.includes('in')) return val * this.MM_PER_INCH;
        if (str.includes('pt')) return val * (this.MM_PER_INCH / 72);
        if (str.includes('pc')) return val * (this.MM_PER_INCH / 6);
        if (str.includes('px')) return val * (this.MM_PER_INCH / this.DPI);

        // Default: assume pixels if no unit specified
        return val * (this.MM_PER_INCH / this.DPI);
    }

    /**
     * Recursively extract paths from SVG element tree
     * @param {Element} element - SVG element to traverse
     * @param {Object} parentTransform - Accumulated transform (for future use)
     * @returns {Array} Array of path objects with 'd' and 'color'
     */
    extractPaths(element, parentTransform = null, stats = null) {
        if (!element || !element.children) return [];

        const paths = [];
        const children = Array.from(element.children);

        children.forEach(child => {
            const tag = child.tagName.toLowerCase();

            // Definitions are not drawings. A <clipPath> or <defs> shape is
            // never rendered, so cutting it would burn invisible geometry.
            if (SVGParser.NON_RENDERED_CONTAINERS.includes(tag)) return;

            if (SVGParser.SHAPE_TAGS.includes(tag)) {
                const color = this.getStrokeColor(child);
                const d = this.elementToPathData(child);
                if (color && d) {
                    paths.push({ d: d, color: color, originalElement: child });
                } else if (d && stats) {
                    // A drawable shape with no resolvable colour cannot be
                    // assigned to a job. Counted so the UI can say why rather
                    // than reporting a bare "no paths found".
                    stats.uncoloured += 1;
                    if (child.getAttribute('class')) stats.classStyled += 1;
                }
                return;
            }

            // Recurse through every other container: <g>, <a>, <switch>,
            // nested <svg>, and anything else an editor emits. Limiting this to
            // <g> is why shapes in other wrappers were invisible, while the
            // backend walked the whole tree and saw them.
            paths.push(...this.extractPaths(child, parentTransform, stats));
        });

        return paths;
    }

    /**
     * Group paths by stroke color into jobs
     * @param {Array} flatPaths - Array of path objects
     * @returns {Array} Array of job objects
     */
    groupPathsByColor(flatPaths) {
        if (!flatPaths || flatPaths.length === 0) return [];

        const groups = new Map();

        flatPaths.forEach(p => {
            if (!p || !p.color) return;

            const c = p.color;
            if (!groups.has(c)) {
                // Smart defaults based on color
                const isRed = c === '#ff0000' || c === '#f00' || c.toLowerCase() === 'red';
                groups.set(c, {
                    color: c,
                    paths: [],
                    enabled: true,
                    speed: isRed ? 600 : 2000, // Red often = cut (slower)
                    power: isRed ? 80 : 40,    // Red often = cut (higher power)
                    passes: 1
                });
            }
            groups.get(c).paths.push(p);
        });

        return Array.from(groups.values());
    }

    /**
     * Get stroke color from element (checks attribute and style)
     * @param {Element} el - SVG element
     * @returns {string|null} Normalized hex color or null
     */
    getStrokeColor(el) {
        // Mirrors gcode_service._element_color(): stroke wins, fill is the
        // fallback, and both resolve up the tree. Keep the two in step - a
        // colour this reports but the backend cannot resolve produces a job
        // that silently cuts nothing.
        const stroke = this.inheritedPaint(el, 'stroke');
        if (stroke) return this.normalizeColor(stroke);

        const fill = this.inheritedPaint(el, 'fill');
        if (fill) return this.normalizeColor(fill);

        return null;
    }

    /**
     * An element's own stroke/fill, from the attribute or its style attribute.
     * @param {Element} el
     * @param {string} prop - 'stroke' or 'fill'
     * @returns {string|null}
     */
    ownPaint(el, prop) {
        let value = el.getAttribute(prop);
        if (!value || value === 'none') {
            const style = el.getAttribute('style') || '';
            const match = style.match(new RegExp('(?:^|;)\\s*' + prop + '\\s*:\\s*([^;]+)'));
            value = match ? match[1].trim() : null;
        }
        if (!value || value === 'none') return null;
        return value;
    }

    /**
     * Resolve stroke/fill the way SVG does - walking up to the nearest ancestor
     * that sets it. Editors routinely put stroke on a parent <g> and leave the
     * shapes bare; reading only the element itself finds no colour at all.
     *
     * @param {Element} el
     * @param {string} prop - 'stroke' or 'fill'
     * @returns {string|null}
     */
    inheritedPaint(el, prop) {
        let node = el;
        let depth = 0;
        while (node && depth < 64) {
            const value = this.ownPaint(node, prop);
            if (value) return value;
            node = node.parentElement;
            depth += 1;
        }
        return null;
    }

    /**
     * Normalize color string to hex format
     * @param {string} c - Color string (hex, rgb, named, etc.)
     * @returns {string|null} Normalized hex color (#rrggbb)
     */
    normalizeColor(c) {
        if (!c) return null;
        
        c = c.trim().toLowerCase();

        // Already hex
        if (c.startsWith('#')) {
            // Expand short hex (#f00 -> #ff0000)
            if (c.length === 4) {
                return '#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3];
            }
            return c;
        }

        // RGB/RGBA
        if (c.startsWith('rgb')) {
            const rgb = c.match(/\d+/g);
            if (rgb && rgb.length >= 3) {
                const r = parseInt(rgb[0]).toString(16).padStart(2, '0');
                const g = parseInt(rgb[1]).toString(16).padStart(2, '0');
                const b = parseInt(rgb[2]).toString(16).padStart(2, '0');
                return `#${r}${g}${b}`;
            }
        }

        // Named colors
        const namedColors = {
            'red': '#ff0000',
            'green': '#00ff00',
            'blue': '#0000ff',
            'black': '#000000',
            'white': '#ffffff',
            'yellow': '#ffff00',
            'cyan': '#00ffff',
            'magenta': '#ff00ff'
        };

        return namedColors[c] || c;
    }

    /**
     * Convert SVG element to path data string
     * @param {Element} element - SVG element
     * @returns {string|null} Path data string or null
     */
    elementToPathData(element) {
        if (!element) return null;

        const tag = element.tagName.toLowerCase();

        try {
            switch (tag) {
                case 'path':
                    return element.getAttribute('d') || null;

                case 'rect':
                    return this.rectToPath(element);

                case 'circle':
                    return this.circleToPath(element);

                case 'ellipse':
                    return this.ellipseToPath(element);

                case 'line':
                    return this.lineToPath(element);

                case 'polyline':
                case 'polygon':
                    return this.polyToPath(element, tag === 'polygon');

                default:
                    return null;
            }
        } catch (err) {
            console.warn(`Error converting ${tag} to path:`, err);
            return null;
        }
    }

    rectToPath(rect) {
        const x = parseFloat(rect.getAttribute('x') || 0);
        const y = parseFloat(rect.getAttribute('y') || 0);
        const w = parseFloat(rect.getAttribute('width') || 0);
        const h = parseFloat(rect.getAttribute('height') || 0);

        if (w <= 0 || h <= 0) return null;

        return `M ${x} ${y} L ${x + w} ${y} L ${x + w} ${y + h} L ${x} ${y + h} Z`;
    }

    circleToPath(circle) {
        const cx = parseFloat(circle.getAttribute('cx') || 0);
        const cy = parseFloat(circle.getAttribute('cy') || 0);
        const r = parseFloat(circle.getAttribute('r') || 0);

        if (r <= 0) return null;

        // Approximate circle with two arcs (simpler than full subdivision)
        return `M ${cx - r} ${cy} A ${r} ${r} 0 1 0 ${cx + r} ${cy} A ${r} ${r} 0 1 0 ${cx - r} ${cy} Z`;
    }

    ellipseToPath(ellipse) {
        const cx = parseFloat(ellipse.getAttribute('cx') || 0);
        const cy = parseFloat(ellipse.getAttribute('cy') || 0);
        const rx = parseFloat(ellipse.getAttribute('rx') || 0);
        const ry = parseFloat(ellipse.getAttribute('ry') || 0);

        if (rx <= 0 || ry <= 0) return null;

        return `M ${cx - rx} ${cy} A ${rx} ${ry} 0 1 0 ${cx + rx} ${cy} A ${rx} ${ry} 0 1 0 ${cx - rx} ${cy} Z`;
    }

    lineToPath(line) {
        const x1 = parseFloat(line.getAttribute('x1') || 0);
        const y1 = parseFloat(line.getAttribute('y1') || 0);
        const x2 = parseFloat(line.getAttribute('x2') || 0);
        const y2 = parseFloat(line.getAttribute('y2') || 0);

        return `M ${x1} ${y1} L ${x2} ${y2}`;
    }

    polyToPath(poly, close) {
        const pointsAttr = poly.getAttribute('points');
        if (!pointsAttr) return null;

        const pts = pointsAttr.trim().split(/[\s,]+/).map(parseFloat).filter(n => !isNaN(n));
        if (pts.length < 2) return null;

        let path = `M ${pts[0]} ${pts[1]}`;
        for (let i = 2; i < pts.length; i += 2) {
            if (i + 1 < pts.length) {
                path += ` L ${pts[i]} ${pts[i + 1]}`;
            }
        }
        if (close) path += ' Z';

        return path;
    }
}

SVGParser.SHAPE_TAGS = ['path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon'];
SVGParser.NON_RENDERED_CONTAINERS = [
    'defs', 'clippath', 'mask', 'symbol', 'marker', 'pattern',
    'metadata', 'title', 'desc', 'style', 'script'
];
