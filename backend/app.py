#!/usr/bin/env python3
"""
Backend API pour OKU Desk Laser Interface
Expose les scripts Python Inkscape comme API REST
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import sys
import os
import tempfile
import json
from pathlib import Path

# Add nomadtech scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'nomadtech'))

app = Flask(__name__)
CORS(app)  # Allow frontend to call API

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'OKU Desk API is running'})

@app.route('/api/generate-vector', methods=['POST'])
def generate_vector():
    """
    Generate vector G-code from SVG
    Expects: { "svg_content": "...", "speed": 600, "power": 80, "passes": 1 }
    Returns: G-code file download
    """
    try:
        data = request.json
        svg_content = data.get('svg_content')
        speed = data.get('speed', 1000)
        power = data.get('power', 100)
        passes = data.get('passes', 1)
        
        if not svg_content:
            return jsonify({'error': 'svg_content is required'}), 400
        
        # Save SVG to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.svg', delete=False) as f:
            f.write(svg_content)
            svg_path = f.name
        
        # Create temp output file
        output_path = svg_path.replace('.svg', '.gco')
        
        # Import and use the Python script
        # Note: This requires adapting the Inkscape extension to work standalone
        # For now, this is a skeleton showing the architecture
        
        # TODO: Adapt 2.1_Nomadtech-OkuDesk_Contornos.py to work without Inkscape
        # This would involve:
        # 1. Creating a mock inkex.extension class
        # 2. Parsing SVG with lxml instead of Inkscape's internal representation
        # 3. Calling the gcode generation logic
        
        return jsonify({
            'error': 'Not yet implemented - needs adaptation of Python scripts',
            'svg_path': svg_path,
            'output_path': output_path
        }), 501
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-raster', methods=['POST'])
def generate_raster():
    """
    Generate raster G-code from image
    Expects: { "image_data": "base64...", "speed": 1796, "power": 100 }
    """
    # Similar structure for raster generation
    return jsonify({'error': 'Not yet implemented'}), 501

if __name__ == '__main__':
    print("Starting OKU Desk API server...")
    print("Frontend should connect to: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
