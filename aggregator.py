import os
import base64
import requests
import logging
from flask import Flask, Response, jsonify

app = Flask(__name__)
logger = logging.getLogger(__name__)

def fetch_subscription(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content = response.text.strip()
        # Ensure it's base64 encoded
        try:
            decoded = base64.b64decode(content).decode('utf-8')
            return decoded
        except Exception:
            # If not base64, assume it's raw links
            return content
    except Exception as e:
        logger.error(f"Error fetching subscription from {url}: {e}")
        return ""

@app.route('/sub/<sub_id>')
def get_subscription(sub_id):
    de_panel = os.environ.get('DE_PANEL_URL', '').rstrip('/')
    nl_panel = os.environ.get('NL_PANEL_URL', '').rstrip('/')

    if not de_panel or not nl_panel:
        return jsonify({"error": "Panel URLs not configured"}), 500

    # 3x-ui standard sub path is /sub/{sub_id}
    # Wait, the 3X-UI subscription link is typically just the panel URL + /sub/ + sub_id,
    # but the panel URLs provided might include some base path.
    # From prompt:
    # DE_PANEL_URL=http://212.113.116.26:2053/NyD6HvK953uSYACZDV
    # NL_PANEL_URL=http://138.124.119.185:2053/WeDcmxaFwu3dFgvw8o
    # Actually, in 3x-ui, the sub link is <panel_url>/sub/<subId> or just <ip>:<port>/sub/<subId>.
    # Usually it's <ip>:<port>/<path>/sub/<subId> if the sub path is relative.
    # Wait, 3x-ui sub URL is <domain>:<port>/sub/<subId> usually.
    # Let's assume the provided panel URL is the base for the panel, and the sub path is /sub/
    # If the user provided: DE_PANEL_URL=http://212.113.116.26:2053/NyD6HvK953uSYACZDV
    # Then maybe the sub link is http://212.113.116.26:2053/sub/<sub_id> or http://212.113.116.26:2053/NyD6HvK953uSYACZDV/sub/<sub_id>.
    # I will try to use the base URL from the panel URL without the secret path for /sub/ if possible,
    # but in 3x-ui, the sub URI can be customized. Default is `/sub/`.

    # We will assume the standard format is base_ip:port/sub/sub_id.
    # Let's extract the base URL from the panel URL.
    from urllib.parse import urlparse

    de_parsed = urlparse(de_panel)
    nl_parsed = urlparse(nl_panel)

    de_sub_url = f"{de_parsed.scheme}://{de_parsed.netloc}/sub/{sub_id}"
    nl_sub_url = f"{nl_parsed.scheme}://{nl_parsed.netloc}/sub/{sub_id}"

    de_links = fetch_subscription(de_sub_url)
    nl_links = fetch_subscription(nl_sub_url)

    combined_links = f"{de_links}\n{nl_links}".strip()

    if not combined_links:
        return Response("Not found", status=404)

    encoded = base64.b64encode(combined_links.encode('utf-8')).decode('utf-8')

    return Response(encoded, mimetype='text/plain')

@app.route('/sub/test')
def test():
    return "OK"

def start_aggregator(port=8080):
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
