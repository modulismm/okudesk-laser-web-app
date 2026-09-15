#!/usr/bin/env python3
"""
Backend API pour OKU Desk Laser Interface
Expose les scripts Python Inkscape comme API REST

Usage:
    python app.py
"""

from flask import Flask, request, jsonify, send_file, send_from_directory, abort
from flask_cors import CORS
import sys
import os
import tempfile
import json
import base64
from pathlib import Path

# Add nomadtech scripts to path
nomadtech_path = Path(__file__).parent.parent.parent / 'nomadtech'
sys.path.insert(0, str(nomadtech_path))

app = Flask(__name__, static_folder=None)  # We'll serve frontend manually
CORS(app)  # Allow frontend to call API

# Serve frontend files (optional - can also open index.html directly)
# In hosted mode, serve the "nice" UI from the main project frontend/
FRONTEND_PATH = Path(__file__).parent.parent.parent / 'frontend'

DONATE_URL = os.environ.get('DONATE_URL', 'https://buymeacoffee.com/bootlessbear')
GITLAB_URL = os.environ.get('GITLAB_URL', 'https://gitlab.com/Bootlessbear/okudesk-laser-web-app')
# Raster enabled by default, can be disabled with ENABLE_RASTER=0
_env_raster = os.environ.get('ENABLE_RASTER', '').strip().lower()
ENABLE_RASTER = _env_raster not in ('0', 'false', 'no')

@app.route('/frontend/<path:filename>')
def serve_frontend(filename):
    """Serve frontend static files"""
    return send_from_directory(str(FRONTEND_PATH), filename)

@app.route('/app')
def serve_frontend_app():
    """Serve the main frontend app"""
    return send_from_directory(str(FRONTEND_PATH), 'index.html')

@app.route('/')
def root_redirect():
    """Convenience: serve the app at root."""
    return send_from_directory(str(FRONTEND_PATH), 'index.html')

@app.route('/<path:filename>')
def serve_frontend_root_files(filename):
    """
    Serve frontend assets at the root (e.g. /style.css, /app.js),
    so the UI can be hosted cleanly behind Nginx.
    """
    if filename.startswith('api/'):
        abort(404)
    return send_from_directory(str(FRONTEND_PATH), filename)

@app.route('/api/config', methods=['GET'])
def config():
    return jsonify({
        'donate_url': DONATE_URL,
        'gitlab_url': GITLAB_URL,
        'raster_enabled': ENABLE_RASTER,
        'raster_url': '/raster',
        'machine': {
            'work_area_mm': {'w': 500, 'h': 285, 'z': 50},
            'total_mm': {'w': 720, 'h': 505, 'z': 185},
            'laser_w': 7.5,
            'accuracy_mm': 0.1,
            'power_w': 100
        }
    })

@app.route('/api', methods=['GET'])
def api_info():
    """API info"""
    return jsonify({
        'name': 'OKU Desk Laser API',
        'version': '0.1.0',
        'status': 'running',
        'endpoints': {
            'config': '/api/config',
            'health': '/api/health',
            'generate_vector': '/api/generate-vector',
            'generate_vector_advanced': '/api/generate-vector-advanced',
            'validate_svg': '/api/validate-svg',
            'generate_raster': '/api/generate-raster' if ENABLE_RASTER else '(disabled)',
            'raster_ui': '/raster' if ENABLE_RASTER else '(disabled)'
        },
        'frontend': 'Open / (web app)'
    })

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'message': 'OKU Desk API is running',
        'version': '0.1.0'
    })

@app.route('/api/generate-vector', methods=['POST'])
def generate_vector():
    """
    Generate vector G-code from SVG
    
    Request body:
    {
        "svg_content": "<svg>...</svg>",
        "speed": 600,
        "power": 80.0,
        "passes": 1
    }
    
    Returns:
    {
        "gcode": "...",
        "filename": "output.gco"
    }
    """
    try:
        data = request.json
        
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        svg_content = data.get('svg_content')
        speed = data.get('speed', 1000)
        power = data.get('power', 100.0)
        passes = data.get('passes', 1)
        origin = data.get('origin', 'bottom-left')
        
        if not svg_content:
            return jsonify({'error': 'svg_content is required'}), 400
        
        # Validate inputs
        speed = max(10, min(6000, int(speed)))
        power = max(1.0, min(100.0, float(power)))
        passes = max(1, min(500, int(passes)))
        origin = str(origin or 'bottom-left').strip().lower()
        if origin not in ('bottom-left', 'bottom-right', 'top-left', 'top-right', 'center'):
            origin = 'bottom-left'
        
        # Save SVG to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.svg', delete=False, encoding='utf-8') as f:
            f.write(svg_content)
            svg_path = f.name
        
        try:
            # Import the gcode service
            from gcode_service import generate_vector_gcode
            
            # Generate G-code
            gcode_content = generate_vector_gcode(
                svg_path=svg_path,
                speed=speed,
                power=power,
                passes=passes,
                origin=origin,
            )
            
            return jsonify({
                'success': True,
                'gcode': gcode_content,
                'filename': 'output.gco',
                'size': len(gcode_content)
            })
            
        except ImportError as e:
            import traceback
            return jsonify({
                'error': 'G-code service not yet implemented',
                'details': str(e),
                'note': 'The gcode_service.py needs to be implemented to wrap the Inkscape Python scripts',
                'traceback': traceback.format_exc() if app.debug else None
            }), 501
            
        except NotImplementedError as e:
            return jsonify({
                'error': 'G-code generation not yet implemented',
                'details': str(e),
                'status': 'coming_soon',
                'note': 'This feature requires adapting the Inkscape Python scripts to work standalone. See inkex_wrapper.py for the wrapper structure.'
            }), 501
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc() if app.debug else None
            print(f"Error generating G-code: {e}")
            if app.debug:
                print(error_trace)
            
            return jsonify({
                'error': 'G-code generation failed',
                'details': str(e),
                'traceback': error_trace
            }), 500
            
        finally:
            # Cleanup temp file
            if os.path.exists(svg_path):
                os.unlink(svg_path)
        
    except Exception as e:
        return jsonify({
            'error': 'Request processing failed',
            'details': str(e)
        }), 500

@app.route('/api/generate-vector-advanced', methods=['POST'])
def generate_vector_advanced():
    """
    Advanced: Generate vector G-code from SVG + ordered jobs.
    Request body:
    {
      "svg_content": "<svg...>",
      "origin": "bottom-left|bottom-right|top-left|top-right|center",
      "jobs": [{ "color": "#ff0000", "enabled": true, "speed": 600, "power": 80, "passes": 2 }, ...]
    }
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        svg_content = data.get('svg_content')
        origin = str(data.get('origin', 'bottom-left') or 'bottom-left').strip().lower()
        jobs = data.get('jobs') or []
        origin_x = data.get('origin_x')
        origin_y = data.get('origin_y')

        if not svg_content:
            return jsonify({'error': 'svg_content is required'}), 400

        if origin not in ('bottom-left', 'bottom-right', 'top-left', 'top-right', 'center', 'custom'):
            origin = 'bottom-left'

        # Validate custom origin coordinates
        if origin == 'custom':
            try:
                origin_x = float(origin_x) if origin_x is not None else None
                origin_y = float(origin_y) if origin_y is not None else None
                if origin_x is None or origin_y is None:
                    return jsonify({'error': 'origin_x and origin_y are required when origin is custom'}), 400
                if origin_x < 0 or origin_x > 500 or origin_y < 0 or origin_y > 285:
                    return jsonify({'error': 'origin_x must be 0-500, origin_y must be 0-285'}), 400
            except (ValueError, TypeError):
                return jsonify({'error': 'origin_x and origin_y must be valid numbers'}), 400

        # Save SVG to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.svg', delete=False, encoding='utf-8') as f:
            f.write(svg_content)
            svg_path = f.name

        try:
            from gcode_service import generate_vector_gcode_advanced
            gcode_content = generate_vector_gcode_advanced(
                svg_path=svg_path, 
                jobs=jobs, 
                origin=origin,
                origin_x=origin_x,
                origin_y=origin_y
            )
            return jsonify({
                'success': True,
                'gcode': gcode_content,
                'filename': 'oku-job.gco',
                'size': len(gcode_content)
            })
        finally:
            if os.path.exists(svg_path):
                os.unlink(svg_path)
    except Exception as e:
        import traceback
        return jsonify({
            'error': 'Advanced G-code generation failed',
            'details': str(e),
            'traceback': traceback.format_exc() if app.debug else None
        }), 500

@app.route('/api/generate-raster', methods=['POST'])
def generate_raster():
    """
    Generate raster G-code from image (prototype)

    Request body:
    {
        "image_base64": "data:image/png;base64,...",
        "speed": 1796,
        "power": 100.0,
        "passes": 1,
        "origin": "bottom-left|bottom-right|top-left|top-right|center",
        "mm_per_pixel": 0.1,
        "width_mm": 50.0,         // optional
        "height_mm": 30.0,        // optional
        "invert_image": false
    }
    """
    if not ENABLE_RASTER:
        return jsonify({
            'error': 'Raster disabled in this deployment',
            'status': 'disabled',
            'note': 'Raster is experimental. Use the separate raster prototype service.',
        }), 501
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        image_base64 = data.get('image_base64') or data.get('image_data')
        if not image_base64:
            return jsonify({'error': 'image_base64 is required'}), 400

        speed = data.get('speed', 1796)
        power = data.get('power', 100.0)
        passes = data.get('passes', 1)
        origin = str(data.get('origin', 'bottom-left') or 'bottom-left').strip().lower()
        mm_per_pixel = float(data.get('mm_per_pixel', 0.1))
        width_mm = data.get('width_mm', None)
        height_mm = data.get('height_mm', None)
        invert_image = bool(data.get('invert_image', False))
        shading = str(data.get('shading', 'grayscale') or 'grayscale')
        gamma = float(data.get('gamma', 1.0))
        levels = int(data.get('levels', 0))
        thumbnail_mode = str(data.get('thumbnail_mode', 'match-input') or 'match-input')
        thumbnail_contrast = float(data.get('thumbnail_contrast', 1.0))
        safe_mode = bool(data.get('safe_mode', False))

        if origin not in ('bottom-left', 'bottom-right', 'top-left', 'top-right', 'center'):
            origin = 'bottom-left'

        from gcode_service import generate_raster_gcode
        gcode_content = generate_raster_gcode(
            image_base64=image_base64,
            speed=int(speed),
            power=float(power),
            passes=int(passes),
            origin=origin,
            width_mm=float(width_mm) if width_mm is not None else None,
            height_mm=float(height_mm) if height_mm is not None else None,
            mm_per_pixel=mm_per_pixel,
            invert_image=invert_image,
            shading=shading,
            gamma=gamma,
            levels=levels,
            thumbnail_mode=thumbnail_mode,
            thumbnail_contrast=thumbnail_contrast,
            safe_mode=safe_mode,
        )

        return jsonify({
            'success': True,
            'gcode': gcode_content,
            'filename': 'oku-raster.gco',
            'size': len(gcode_content)
        })
    except ValueError as e:
        # Bad input, not a server fault: unreadable or unsupported image, empty
        # or non-base64 payload. _decode_image_data raises these with a message
        # written for the user, so pass it straight through.
        return jsonify({
            'error': str(e),
            'status': 'invalid-image',
        }), 400
    except ImportError as e:
        # Pillow and numpy are imported lazily inside gcode_service, so the app
        # starts fine without them and only raster requests fail. Without this
        # branch that surfaces as a generic 500, which is a slow thing to
        # diagnose from the UI. Listed in requirements.txt.
        return jsonify({
            'error': 'Raster dependencies are not installed on the server',
            'details': str(e),
            'hint': 'Raster needs Pillow and numpy. Install requirements.txt and restart.',
            'status': 'missing-dependency',
        }), 503
    except Exception as e:
        import traceback
        return jsonify({
            'error': 'Raster generation failed',
            'details': str(e),
            'traceback': traceback.format_exc() if app.debug else None
        }), 500


@app.route('/raster')
def serve_raster_tool():
    """Prototype raster tool (not linked from the main UI)."""
    if not ENABLE_RASTER:
        abort(404)
    return send_from_directory(str(FRONTEND_PATH), 'raster.html')

@app.route('/api/validate-svg', methods=['POST'])
def validate_svg():
    """
    Validate SVG content
    
    Request body:
    {
        "svg_content": "<svg>...</svg>"
    }
    """
    try:
        data = request.json
        svg_content = data.get('svg_content', '')
        
        if not svg_content:
            return jsonify({'valid': False, 'error': 'No SVG content'}), 400
        
        # Basic SVG validation
        from lxml import etree
        
        try:
            etree.fromstring(svg_content.encode('utf-8'))
            return jsonify({
                'valid': True,
                'message': 'SVG is well-formed'
            })
        except etree.XMLSyntaxError as e:
            return jsonify({
                'valid': False,
                'error': f'Invalid SVG: {str(e)}'
            }), 400
            
    except Exception as e:
        return jsonify({
            'valid': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # Prefer fixed PORT in hosted mode (Docker / Nginx)
    PORT = int(os.environ.get('PORT', '8000'))
    DEBUG = str(os.environ.get('DEBUG', '')).strip().lower() in ('1', 'true', 'yes')
    
    print("=" * 50)
    print("OKU Desk API Server")
    print("=" * 50)
    print(f"Backend API: http://localhost:{PORT}")
    print(f"API Info:   http://localhost:{PORT}/api")
    print(f"Health:     http://localhost:{PORT}/api/health")
    print(f"Frontend:   http://localhost:{PORT}/")
    print("=" * 50)
    print("\nEndpoints:")
    print("  GET  /api                 - API info")
    print("  GET  /api/config          - UI config (donate/gitlab)")
    print("  GET  /api/health          - Health check")
    print("  POST /api/generate-vector - Generate vector G-code")
    print("  POST /api/generate-vector-advanced - Generate vector G-code (ordered jobs)")
    print("  POST /api/validate-svg    - Validate SVG")
    print("  POST /api/generate-raster - Generate raster G-code (coming soon)")
    print(f"\nStarting server on port {PORT}...\n")
    print("💡 Tip: Ouvre http://localhost:{PORT}/ dans un navigateur".format(PORT=PORT))
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
