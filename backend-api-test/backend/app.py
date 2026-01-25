#!/usr/bin/env python3
"""
Backend API pour OKU Desk Laser Interface
Expose les scripts Python Inkscape comme API REST

Usage:
    python app.py
"""

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import sys
import os
import tempfile
import json
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

@app.route('/api/config', methods=['GET'])
def config():
    return jsonify({
        'donate_url': DONATE_URL,
        'gitlab_url': GITLAB_URL,
        'machine': {
            'work_area_mm': {'w': 500, 'h': 285, 'z': 50},
            'total_mm': {'w': 720, 'h': 505, 'z': 185},
            'laser_w': 7.5,
            'accuracy_mm': 0.1,
            'power_w': 100
        }
    })

@app.route('/', methods=['GET'])
def index():
    """Root endpoint - API info"""
    return jsonify({
        'name': 'OKU Desk Laser API',
        'version': '0.1.0',
        'status': 'running',
        'endpoints': {
            'health': '/api/health',
            'generate_vector': '/api/generate-vector',
            'generate_vector_advanced': '/api/generate-vector-advanced',
            'validate_svg': '/api/validate-svg',
            'generate_raster': '/api/generate-raster (coming soon)'
        },
        'frontend': 'Open frontend/index.html in a browser'
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

        if not svg_content:
            return jsonify({'error': 'svg_content is required'}), 400

        if origin not in ('bottom-left', 'bottom-right', 'top-left', 'top-right', 'center'):
            origin = 'bottom-left'

        # Save SVG to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.svg', delete=False, encoding='utf-8') as f:
            f.write(svg_content)
            svg_path = f.name

        try:
            from gcode_service import generate_vector_gcode_advanced
            gcode_content = generate_vector_gcode_advanced(svg_path=svg_path, jobs=jobs, origin=origin)
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
    Generate raster G-code from image
    
    Request body:
    {
        "image_data": "base64...",
        "speed": 1796,
        "power": 100.0
    }
    """
    return jsonify({
        'error': 'Raster generation not yet implemented',
        'status': 'coming_soon'
    }), 501

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
    import socket
    
    # Trouver un port disponible (évite conflit avec AirPlay sur macOS)
    def find_free_port(start_port=5001, max_attempts=10):
        for port in range(start_port, start_port + max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', port))
                    return port
            except OSError:
                continue
        return 5001  # Fallback
    
    PORT = find_free_port(5001)
    
    print("=" * 50)
    print("OKU Desk API Server")
    print("=" * 50)
    print(f"Backend API: http://localhost:{PORT}")
    print(f"API Info:   http://localhost:{PORT}/")
    print(f"Health:     http://localhost:{PORT}/api/health")
    print(f"Frontend:   http://localhost:{PORT}/app")
    print("=" * 50)
    print("\nEndpoints:")
    print("  GET  /                    - API info")
    print("  GET  /api/health          - Health check")
    print("  POST /api/generate-vector - Generate vector G-code")
    print("  POST /api/validate-svg    - Validate SVG")
    print("  POST /api/generate-raster - Generate raster G-code (coming soon)")
    print(f"\nStarting server on port {PORT}...\n")
    print("💡 Tip: Ouvre http://localhost:{PORT}/app dans un navigateur".format(PORT=PORT))
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=PORT, debug=True)
