/**
 * G-Code Generator for OKU Desk Laser
 * Converts SVG paths to machine-readable G-code
 * 
 * Firmware: Smoothieware (modified for Oku Desk)
 * Note: Original Python script mentions "grbl 0.9g mod" but firmware is Smoothieware
 * 
 * @version 0.2.2
 */

class GCodeGenerator {
    constructor() {
        // Constants
        this.DPI = 96.0;
        this.MM_PER_INCH = 25.4;
        this.BED_W = 500;
        this.BED_H = 285;
        this.RAPID_SPEED = 7000; // G0 speed (mm/min)
        this.S_MAX = 255; // Power scale (0-255, matching Python script: power% × 2.55)
        this.ZERO_MOVE_THRESHOLD = 0.005; // Minimum move distance (mm)
        
        // State
        this.resetState();
    }

    /**
     * Reset internal state for new generation
     */
    resetState() {
        this.estimatedTime = 0; // minutes
        this.bounds = { 
            minX: Infinity, 
            maxX: -Infinity, 
            minY: Infinity, 
            maxY: -Infinity 
        };
        // Offset to shift negative coordinates to positive (machine requires 0-500, 0-285)
        this.offsetX = 0;
        this.offsetY = 0;
    }

    /**
     * Generate complete G-code from jobs
     * @param {Array} jobs - Array of job objects with paths
     * @param {number} svgW - SVG width in mm
     * @param {number} svgH - SVG height in mm
     * @param {number} globalTravelSpeed - Travel speed for G0 moves
     * @param {string} originMode - Job origin on bed (bottom-left, bottom-right, top-left, top-right, center)
     * @returns {string} Complete G-code string
     */
    generate(jobs, svgW, svgH, globalTravelSpeed, originMode = 'bottom-left') {
        // WARNING: this method is NOT used to produce the G-code that gets
        // downloaded/sent to the laser (that is generated server-side, see
        // generateViaBackend() in app.js and gcode_service.py). It lacks
        // <g transform="..."> handling (extractPaths()'s parentTransform is
        // never applied) and several path commands (A/Q/S/T), so it will
        // silently produce WRONG geometry on real-world SVGs (e.g. anything
        // exported from Inkscape, which wraps content in transformed groups).
        // Do not wire this back into the production download path without
        // first reaching feature parity with the backend generator.
        if (!jobs || !Array.isArray(jobs)) {
            throw new Error('Invalid jobs parameter');
        }
        
        this.resetState();
        this.originMode = originMode || 'bottom-left';
        
        const enabledJobs = jobs.filter(j => j && j.enabled);
        if (enabledJobs.length === 0) {
            return this.emptyGCode();
        }

        // Validate SVG dimensions
        if (!svgH || svgH <= 0) {
            console.warn('Invalid SVG height, using default 285mm');
            svgH = this.BED_H;
        }

        // Phase 1: Analyze - Calculate bounds and estimate time
        enabledJobs.forEach(job => {
            if (!job.paths || !Array.isArray(job.paths)) return;
            
            job.paths.forEach(p => {
                if (!p || !p.d) return;
                try {
                    const points = this.pathToPoints(p.d);
                    this.updateBounds(points, svgH);
                } catch (err) {
                    console.warn('Error parsing path:', err);
                }
            });
        });

        // Validate bounds
        if (!this.hasValidBounds()) {
            console.warn('No valid bounds calculated, using defaults');
            this.bounds = { minX: 0, maxX: 0, minY: 0, maxY: 0 };
        }

        // Calculate offsets based on origin selection (anchor within bed)
        const w = Math.max(0, this.bounds.maxX - this.bounds.minX);
        const h = Math.max(0, this.bounds.maxY - this.bounds.minY);

        // Base shift to bring min corner to (0,0)
        this.offsetX = -this.bounds.minX;
        this.offsetY = -this.bounds.minY;

        const extraX = Math.max(0, this.BED_W - w);
        const extraY = Math.max(0, this.BED_H - h);

        switch ((this.originMode || 'bottom-left').toLowerCase()) {
            case 'bottom-right':
                this.offsetX += extraX;
                break;
            case 'top-left':
                this.offsetY += extraY;
                break;
            case 'top-right':
                this.offsetX += extraX;
                this.offsetY += extraY;
                break;
            case 'center':
                this.offsetX += extraX / 2;
                this.offsetY += extraY / 2;
                break;
            default:
                // bottom-left
                break;
        }
        
        // Apply offset to bounds
        this.bounds.minX += this.offsetX;
        this.bounds.maxX += this.offsetX;
        this.bounds.minY += this.offsetY;
        this.bounds.maxY += this.offsetY;

        // Phase 2: Generate G-code
        const gcode = [];
        
        // Metadata header
        gcode.push(...this.makeMetaHeader(enabledJobs[0], globalTravelSpeed));
        
        // Initialization - Safe start sequence (matches Python script exactly)
        gcode.push('M5 ; Turn laser off', 'G21 ; Units in mm', ''); // M5=laser off, G21=mm units

        // Process each enabled job
        enabledJobs.forEach(job => {
            // Match Python script: int(math.ceil(laser_power * 2.55))
            const powerVal = Math.ceil(job.power * 2.55);
            const speed = Math.max(10, Math.min(6000, job.speed || 1000)); // Clamp speed
            
            for (let pass = 0; pass < (job.passes || 1); pass++) {
                if (job.passes > 1) {
                    gcode.push(`; --- Job: ${job.color} | Pass ${pass + 1}/${job.passes} ---`);
                }
                
                gcode.push(`F${speed}`);
                
                // Generate all paths for this pass
                const pathCommands = [];
                job.paths.forEach(p => {
                    if (!p || !p.d) return;
                    try {
                        const points = this.pathToPoints(p.d);
                        pathCommands.push(...this.pointsToGCode(points, powerVal, speed, svgH));
                    } catch (err) {
                        console.warn('Error generating G-code for path:', err);
                    }
                });
                
                gcode.push(...pathCommands);
                // Note: M5 already added at end of each path by pointsToGCode
            }
        });

        // Footer - Return to origin (matches Python script)
        gcode.push('G0 X0 Y0');
        gcode.push('');
        gcode.push('M5 ; Turn laser off');
        
        // Join with newlines (matches Python: each line + "\n" separately)
        return gcode.join('\n');
    }

    /**
     * Check if bounds are valid
     */
    hasValidBounds() {
        return isFinite(this.bounds.minX) && 
               isFinite(this.bounds.maxX) && 
               isFinite(this.bounds.minY) && 
               isFinite(this.bounds.maxY) &&
               this.bounds.maxX >= this.bounds.minX &&
               this.bounds.maxY >= this.bounds.minY;
    }

    /**
     * Convert SVG path string to array of points
     * Supports: M, L, H, V, Z, C (cubic bezier approximated)
     * @param {string} d - SVG path data string
     * @returns {Array} Array of {x, y, cmd} objects
     */
    pathToPoints(d) {
        if (!d || typeof d !== 'string') return [];
        
        const ops = d.match(/[a-df-z][^a-df-z]*/gi) || [];
        const points = [];
        let current = { x: 0, y: 0 };
        let start = { x: 0, y: 0 };
        let isRelative = false;

        ops.forEach(opStr => {
            if (!opStr) return;
            
            const type = opStr[0];
            isRelative = type === type.toLowerCase();
            const typeUpper = type.toUpperCase();
            const args = opStr.slice(1).trim().split(/[\s,]+/)
                .map(parseFloat)
                .filter(n => !isNaN(n));

            switch (typeUpper) {
                case 'M': // Move
                    if (args.length >= 2) {
                        current = {
                            x: isRelative ? current.x + args[0] : args[0],
                            y: isRelative ? current.y + args[1] : args[1]
                        };
                        start = { ...current };
                        points.push({ ...current, cmd: 'M' });
                    }
                    break;

                case 'L': // Line
                    for (let i = 0; i < args.length; i += 2) {
                        if (i + 1 < args.length) {
                            current = {
                                x: isRelative ? current.x + args[i] : args[i],
                                y: isRelative ? current.y + args[i + 1] : args[i + 1]
                            };
                            points.push({ ...current, cmd: 'L' });
                        }
                    }
                    break;

                case 'H': // Horizontal line
                    args.forEach(x => {
                        current.x = isRelative ? current.x + x : x;
                        points.push({ ...current, cmd: 'L' });
                    });
                    break;

                case 'V': // Vertical line
                    args.forEach(y => {
                        current.y = isRelative ? current.y + y : y;
                        points.push({ ...current, cmd: 'L' });
                    });
                    break;

                case 'Z': // Close path
                    current = { ...start };
                    points.push({ ...current, cmd: 'L' });
                    break;

                case 'C': // Cubic Bezier - approximate with line segments
                    if (args.length >= 6) {
                        const bezierPoints = this.approximateCubicBezier(
                            current,
                            { x: args[0], y: args[1] },
                            { x: args[2], y: args[3] },
                            { x: args[4], y: args[5] },
                            isRelative
                        );
                        points.push(...bezierPoints);
                        current = bezierPoints[bezierPoints.length - 1];
                    }
                    break;

                // TODO: Add S, Q, T, A (smooth curves, quadratic, arcs)
                default:
                    // NOTE: this command is silently skipped AND (cx, cy) is not
                    // advanced, so every subsequent point in this path is wrong too.
                    // This function is only used for the time ESTIMATE (see
                    // estimateTime()/updateStats()), not for production G-code
                    // download (see generateViaBackend() in app.js) - so this only
                    // makes the on-screen time estimate inaccurate, it does not
                    // affect the actual cut. Kept non-throwing for that reason.
                    console.warn(`Unsupported path command: ${typeUpper} - time estimate will be inaccurate for this path`);
            }
        });

        return points;
    }

    /**
     * Approximate cubic Bezier curve with line segments
     * @param {Object} p0 - Start point
     * @param {Object} p1 - Control point 1
     * @param {Object} p2 - Control point 2
     * @param {Object} p3 - End point
     * @param {boolean} isRelative - Whether coordinates are relative
     * @returns {Array} Array of points approximating the curve
     */
    approximateCubicBezier(p0, p1, p2, p3, isRelative) {
        const points = [];
        const segments = 8; // Number of line segments to approximate
        
        // Adjust for relative coordinates
        const cp1 = isRelative ? { x: p0.x + p1.x, y: p0.y + p1.y } : p1;
        const cp2 = isRelative ? { x: p0.x + p2.x, y: p0.y + p2.y } : p2;
        const end = isRelative ? { x: p0.x + p3.x, y: p0.y + p3.y } : p3;

        for (let i = 1; i <= segments; i++) {
            const t = i / segments;
            const point = this.bezierPoint(p0, cp1, cp2, end, t);
            points.push({ ...point, cmd: 'L' });
        }

        return points;
    }

    /**
     * Calculate point on cubic Bezier curve at parameter t
     */
    bezierPoint(p0, p1, p2, p3, t) {
        const mt = 1 - t;
        const mt2 = mt * mt;
        const mt3 = mt2 * mt;
        const t2 = t * t;
        const t3 = t2 * t;

        return {
            x: mt3 * p0.x + 3 * mt2 * t * p1.x + 3 * mt * t2 * p2.x + t3 * p3.x,
            y: mt3 * p0.y + 3 * mt2 * t * p1.y + 3 * mt * t2 * p2.y + t3 * p3.y
        };
    }

    /**
     * Convert points array to G-code commands
     * @param {Array} points - Array of {x, y, cmd} objects
     * @param {number} power - Laser power (0-S_MAX)
     * @param {number} speed - Feed rate (mm/min)
     * @param {number} svgHeight - SVG height for Y-axis flip
     * @returns {Array} Array of G-code command strings
     */
    pointsToGCode(points, power, speed, svgHeight) {
        if (!points || points.length === 0) return [];
        
        const lines = [];
        let last = null;
        let laserOn = false;
        let firstMovePoint = null; // Track first M point to avoid redundant close

        points.forEach((pt, idx) => {
            // Convert to machine coordinates (flip Y-axis) and apply offset
            const mx = pt.x + this.offsetX;
            const my = (svgHeight - pt.y) + this.offsetY;

            // Skip zero-length moves (Smoothieware doesn't like them)
            if (last && 
                Math.abs(mx - last.x) < this.ZERO_MOVE_THRESHOLD && 
                Math.abs(my - last.y) < this.ZERO_MOVE_THRESHOLD) {
                // If this is the last point and it's the same as first, skip it (path close)
                if (idx === points.length - 1 && firstMovePoint &&
                    Math.abs(mx - firstMovePoint.x) < this.ZERO_MOVE_THRESHOLD &&
                    Math.abs(my - firstMovePoint.y) < this.ZERO_MOVE_THRESHOLD) {
                    return; // Skip redundant close
                }
                if (pt.cmd !== 'M') {
                    return; // Skip zero-length L moves
                }
            }

            if (pt.cmd === 'M') {
                // Rapid move - ALWAYS turn off laser before G0 (safety)
                if (laserOn) {
                    lines.push('M5');
                    laserOn = false;
                }
                lines.push(`G0 X${this.fmt(mx)} Y${this.fmt(my)}`);
                if (last) {
                    this.addTime(last, { x: mx, y: my }, this.RAPID_SPEED);
                }
                // Track first move point
                if (firstMovePoint === null) {
                    firstMovePoint = { x: mx, y: my };
                }
            } else if (pt.cmd === 'L') {
                // Work move - turn on laser if needed (only once per path)
                if (!laserOn) {
                    lines.push(`M3 S${power}`);
                    laserOn = true;
                }
                
                // Check if this is a redundant return to start (last point = first point)
                if (idx === points.length - 1 && firstMovePoint &&
                    Math.abs(mx - firstMovePoint.x) < this.ZERO_MOVE_THRESHOLD &&
                    Math.abs(my - firstMovePoint.y) < this.ZERO_MOVE_THRESHOLD) {
                    // Skip redundant close - we're already at start from G0
                    return;
                }
                
                lines.push(`G1 X${this.fmt(mx)} Y${this.fmt(my)}`);
                if (last) {
                    this.addTime(last, { x: mx, y: my }, speed);
                }
            }

            last = { x: mx, y: my };
        });

        // Turn off laser at end of path (before next G0 if any)
        // This ensures laser is off during rapid moves between paths
        if (laserOn) {
            lines.push('M5');
        }

        return lines;
    }

    /**
     * Update global bounds with machine coordinates
     */
    updateBounds(points, svgH) {
        if (!points || points.length === 0) return;
        
        points.forEach(p => {
            const mx = p.x;
            const my = svgH - p.y;
            
            this.bounds.minX = Math.min(this.bounds.minX, mx);
            this.bounds.maxX = Math.max(this.bounds.maxX, mx);
            this.bounds.minY = Math.min(this.bounds.minY, my);
            this.bounds.maxY = Math.max(this.bounds.maxY, my);
        });
    }

    /**
     * Add time estimate for a move
     */
    addTime(p1, p2, speed) {
        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        this.estimatedTime += dist / speed; // minutes
    }

    /**
     * Format coordinate number (matches Python format)
     * Rounds to 4 decimals and strips trailing zeros
     */
    fmt(n) {
        if (typeof n !== 'number' || isNaN(n)) return '0';
        
        const val = Math.round(n * 10000) / 10000;
        let s = val.toFixed(4);
        return s.replace(/\.?0+$/, '');
    }

    /**
     * Generate metadata header block
     * Matches Python script: calculates meta_len by counting each line
     */
    makeMetaHeader(firstJob, travelSpeed) {
        const w = this.bounds.maxX - this.bounds.minX;
        const h = this.bounds.maxY - this.bounds.minY;
        
        const safeW = isFinite(w) && w > 0 ? w : 0;
        const safeH = isFinite(h) && h > 0 ? h : 0;
        const safeX = isFinite(this.bounds.minX) ? this.bounds.minX : 0;
        const safeY = isFinite(this.bounds.minY) ? this.bounds.minY : 0;

        // Build lines and count characters exactly like Python script
        // Python does: gcode.append(line) then gcode.append("\n") separately
        let metaLen = 0;
        const lines = [];
        
        // Helper to add line and count (line + \n)
        const addLine = (line) => {
            lines.push(line);
            metaLen += line.length + 1; // +1 for \n that will be added
        };
        
        // Placeholder for Meta untilchar (will be updated at end)
        const placeholder = ';$M Meta untilchar 000000';
        addLine(placeholder);
        
        // Frame size
        addLine(`;$M Frame X${safeW.toFixed(2)} Y${safeH.toFixed(2)}`);
        
        // Frame position
        addLine(`;$M Pos X${safeX.toFixed(2)} Y${safeY.toFixed(2)}`);
        
        // NumOps
        addLine(';$M NumOps 1');
        
        // Op
        addLine(';$M Op 0');
        
        // Type
        addLine(';$M Type Vector');
        
        // Speed
        addLine(`;$M Speed ${firstJob.speed || 1000}`);
        
        // Power
        addLine(`;$M Power ${(firstJob.power || 0).toFixed(1)}`);
        
        // Rep
        addLine(`;$M Rep ${firstJob.passes || 1}`);
        
        // Time
        addLine(`;$M Time ${Math.ceil(this.estimatedTime)}`);
        
        // Thumb start (minimal placeholder)
        addLine(';$M Thumb start X0 Y0');
        
        // Thumb end (Python adds \n\n after this, so we count 2 newlines)
        lines.push(';$M Thumb end');
        metaLen += ';$M Thumb end'.length + 2; // +2 for \n\n
        
        // Add empty line (the second \n comes from join)
        lines.push('');
        
        // Update first line with actual count
        lines[0] = `;$M Meta untilchar ${String(metaLen).padStart(6, '0')}`;
        
        // Return lines (without \n, will be added by generate())
        return lines;
    }

    /**
     * Estimate total job time (optimized - doesn't generate full G-code)
     */
    estimateTime(jobs, svgH, travelSpeed) {
        this.resetState();
        
        const enabledJobs = jobs.filter(j => j && j.enabled);
        if (enabledJobs.length === 0) return 0;

        enabledJobs.forEach(job => {
            if (!job.paths) return;

            // Accumulate this job's own contribution in a local variable, then
            // apply its passes multiplier and add it to the running total.
            // (Previously `this.estimatedTime *= passes` multiplied the SHARED
            // running total, compounding every prior job's time as well.)
            const before = this.estimatedTime;
            this.estimatedTime = 0;

            job.paths.forEach(p => {
                if (!p || !p.d) return;
                try {
                    const points = this.pathToPoints(p.d);
                    const speed = job.speed || 1000;

                    let last = null;
                    points.forEach(pt => {
                        const mx = pt.x;
                        const my = svgH - pt.y;

                        if (last && pt.cmd === 'L') {
                            this.addTime(last, { x: mx, y: my }, speed);
                        } else if (last && pt.cmd === 'M') {
                            this.addTime(last, { x: mx, y: my }, this.RAPID_SPEED);
                        }

                        last = { x: mx, y: my };
                    });
                } catch (err) {
                    console.warn('Error estimating time for path:', err);
                }
            });

            const jobTime = this.estimatedTime;
            this.estimatedTime = before + jobTime * (job.passes || 1);
        });

        return this.estimatedTime;
    }
    
    emptyGCode() {
        return "; No jobs enabled\nM5\nG21\n";
    }
}
