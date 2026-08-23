"""
Multi-Domain Data Analysis Agent — Web Frontend Backend

A Flask web app that lets users upload any CSV, sends it through a Langflow
pipeline (domain classification -> RAG retrieval -> grounded analysis ->
PDF report generation), and displays the results in the browser.

Setup:
    1. Copy .env.example to .env and fill in your own values
    2. pip install -r requirements.txt
    3. Make sure Langflow is running (langflow run) with the flow imported
       from langflow_flow.json
    4. python app.py
    5. Open http://127.0.0.1:5000
"""

from flask import Flask, request, jsonify, send_from_directory, render_template_string
import requests
import os
import glob
import json as json_lib
import re
import tempfile
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ---------------- CONFIG — set these in a .env file, never hardcode ----------------
LANGFLOW_URL = os.environ.get("LANGFLOW_URL", "http://localhost:7860")
LANGFLOW_API_KEY = os.environ.get("LANGFLOW_API_KEY")
FLOW_ID = os.environ.get("FLOW_ID")
READ_FILE_COMPONENT_ID = os.environ.get("READ_FILE_COMPONENT_ID")
REPORTS_DIR = os.environ.get("REPORTS_DIR", "./reports")
# -------------------------------------------------------------------------------

if not LANGFLOW_API_KEY or not FLOW_ID or not READ_FILE_COMPONENT_ID:
    print(
        "WARNING: One or more required environment variables are missing "
        "(LANGFLOW_API_KEY, FLOW_ID, READ_FILE_COMPONENT_ID). "
        "Copy .env.example to .env and fill them in."
    )

os.makedirs(REPORTS_DIR, exist_ok=True)


HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Multi-Domain Data Analysis Agent</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: #0f0f1a; color: #eee; max-width: 720px; margin: 60px auto; padding: 0 20px; }
  h1 { font-size: 1.6rem; margin-bottom: 4px; }
  p.sub { color: #999; margin-top: 0; }
  .card { background: #1a1a2e; border: 1px solid #2a2a40; border-radius: 12px; padding: 28px; margin-top: 24px; }
  input[type=file] { color: #eee; }
  button { background: #6c5ce7; color: white; border: none; padding: 10px 20px; border-radius: 8px; font-size: 1rem; cursor: pointer; margin-top: 16px; }
  button:disabled { background: #444; cursor: not-allowed; }
  #status { margin-top: 16px; color: #aaa; white-space: pre-wrap; }
  .result { margin-top: 20px; }
  .result h3 { color: #a29bfe; margin-bottom: 4px; }
  ul { padding-left: 20px; }
  a.download { display: inline-block; margin-top: 16px; background: #00b894; color: white; padding: 10px 18px; border-radius: 8px; text-decoration: none; }
</style>
</head>
<body>
  <h1>Multi-Domain Data Analysis Agent</h1>
  <p class="sub">Upload any CSV — the agent detects the domain, retrieves relevant knowledge, and generates a report.</p>

  <div class="card">
    <input type="file" id="csvFile" accept=".csv" />
    <br>
    <button id="submitBtn" onclick="runAnalysis()">Analyze</button>
    <div id="status"></div>
    <div id="result" class="result"></div>
  </div>

<script>
async function runAnalysis() {
  const fileInput = document.getElementById('csvFile');
  const status = document.getElementById('status');
  const result = document.getElementById('result');
  const btn = document.getElementById('submitBtn');

  if (!fileInput.files.length) {
    status.textContent = "Please choose a CSV file first.";
    return;
  }

  btn.disabled = true;
  result.innerHTML = "";
  status.textContent = "Uploading file...";

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  try {
    const resp = await fetch('/analyze', { method: 'POST', body: formData });
    status.textContent = "Running pipeline (this can take 2-4 minutes)...";
    const data = await resp.json();

    if (data.error) {
      status.textContent = "Error: " + data.error;
      btn.disabled = false;
      return;
    }

    status.textContent = "Done!";
    let html = `<h3>Domain: ${(data.domain || "unknown").toUpperCase()}</h3>`;
    html += `<p>${data.summary}</p>`;
    html += `<h3>Key Insights</h3><ul>${(data.key_insights || []).map(i => `<li>${i}</li>`).join('')}</ul>`;
    html += `<h3>Risk Areas</h3><ul>${(data.risk_areas || []).map(i => `<li>${i}</li>`).join('')}</ul>`;
    html += `<h3>Recommendations</h3><ul>${(data.recommendations || []).map(i => `<li>${i}</li>`).join('')}</ul>`;
    if (data.pdf_filename) {
      html += `<a class="download" href="/download/${data.pdf_filename}">Download PDF Report</a>`;
    }
    result.innerHTML = html;
  } catch (e) {
    status.textContent = "Request failed: " + e;
  }
  btn.disabled = false;
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@app.route("/analyze", methods=["POST"])
def analyze():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    uploaded_file = request.files["file"]
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    os.close(tmp_fd)
    uploaded_file.save(tmp_path)

    headers = {"x-api-key": LANGFLOW_API_KEY}

    # 1. Upload file to Langflow's file storage
    try:
        with open(tmp_path, "rb") as f:
            upload_resp = requests.post(
                f"{LANGFLOW_URL}/api/v2/files/",
                headers=headers,
                files={"file": (uploaded_file.filename, f, "text/csv")},
            )
        upload_resp.raise_for_status()
        upload_data = upload_resp.json()
        server_path = upload_data.get("path")
        if not server_path:
            return jsonify({"error": f"Upload succeeded but no path returned: {upload_data}"}), 500
    except Exception as e:
        return jsonify({"error": f"File upload to Langflow failed: {e}"}), 500
    finally:
        os.remove(tmp_path)

    # 2. Snapshot existing PDFs so we can find the NEW one after this run
    before_files = set(glob.glob(os.path.join(REPORTS_DIR, "*.pdf")))

    # 3. Run the flow with the uploaded file swapped into the Read File component
    run_payload = {
        "output_type": "chat",
        "input_type": "chat",
        "input_value": "Analyze this dataset.",
        "tweaks": {
            READ_FILE_COMPONENT_ID: {
                "path": [server_path]
            }
        }
    }

    try:
        run_resp = requests.post(
            f"{LANGFLOW_URL}/api/v1/run/{FLOW_ID}",
            headers={**headers, "Content-Type": "application/json"},
            json=run_payload,
            timeout=600,
        )
        run_resp.raise_for_status()
        run_data = run_resp.json()
    except Exception as e:
        return jsonify({"error": f"Flow run failed: {e}"}), 500

    # 4. Extract the Analysis Agent's JSON output from the run response
    analysis_text = None
    try:
        outputs = run_data.get("outputs", [])
        for output_group in outputs:
            for out in output_group.get("outputs", []):
                results = out.get("results", {})
                message = results.get("message", {})
                text = message.get("text") or message.get("data", {}).get("text")
                if text and '"summary"' in text:
                    analysis_text = text
    except Exception:
        pass

    parsed = {"summary": "N/A", "key_insights": [], "risk_areas": [], "recommendations": [], "domain": "unknown"}

    if analysis_text:
        cleaned = analysis_text.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        try:
            parsed_json = json_lib.loads(cleaned.strip())
            parsed.update(parsed_json)
        except Exception:
            pass

    # 5. Find the newly created PDF
    after_files = set(glob.glob(os.path.join(REPORTS_DIR, "*.pdf")))
    new_files = after_files - before_files
    pdf_filename = None
    if new_files:
        pdf_filename = os.path.basename(sorted(new_files)[-1])

    if pdf_filename:
        match = re.search(r"report_([a-zA-Z0-9_]+)_\d{8}_\d{6}\.pdf", pdf_filename)
        if match:
            parsed["domain"] = match.group(1)

    parsed["pdf_filename"] = pdf_filename
    return jsonify(parsed)


@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(REPORTS_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
