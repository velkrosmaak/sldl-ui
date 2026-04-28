import html
import json
import queue
import shutil
import subprocess
import threading
from pathlib import Path

from flask import Flask, Response, jsonify, render_template_string, request


SOULSEEK_USERNAME = "your_username"
SOULSEEK_PASSWORD = "your_password"
OUTPUT_PATH = str(Path.cwd() / "downloads")
HOST = "127.0.0.1"
PORT = 5000


app = Flask(__name__)

state_lock = threading.Lock()
app_state = {
    "last_search": "",
    "output": [],
    "running": False,
    "listeners": set(),
}


HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PulseDL</title>
  <style>
    :root {
      --bg: #f4efe7;
      --bg-accent: rgba(245, 166, 35, 0.16);
      --panel: rgba(255, 252, 247, 0.84);
      --panel-strong: rgba(255, 248, 239, 0.95);
      --line: rgba(89, 63, 40, 0.14);
      --text: #24160d;
      --muted: #775a45;
      --accent: #d95d39;
      --accent-strong: #b64727;
      --accent-soft: rgba(217, 93, 57, 0.14);
      --ok: #18794e;
      --shadow: 0 28px 70px rgba(86, 50, 28, 0.16);
      --radius: 24px;
      --radius-sm: 14px;
      --mono: "SFMono-Regular", "SF Mono", Consolas, "Liberation Mono", Menlo, monospace;
      --sans: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: var(--sans);
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(255, 255, 255, 0.92), transparent 32%),
        radial-gradient(circle at bottom right, var(--bg-accent), transparent 28%),
        linear-gradient(135deg, #f9f4ec 0%, #f2e6d6 50%, #eadbc8 100%);
    }

    .shell {
      width: min(980px, calc(100vw - 32px));
      margin: 32px auto;
      padding: 28px;
      border: 1px solid rgba(255, 255, 255, 0.55);
      border-radius: var(--radius);
      background: var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(16px);
    }

    .hero {
      display: grid;
      gap: 10px;
      margin-bottom: 24px;
    }

    .eyebrow {
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--accent);
    }

    h1 {
      margin: 0;
      font-size: clamp(2rem, 5vw, 3.8rem);
      line-height: 0.94;
      font-weight: 800;
      max-width: 10ch;
    }

    .subcopy {
      margin: 0;
      max-width: 56ch;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.55;
    }

    .search-panel {
      border: 1px solid var(--line);
      border-radius: calc(var(--radius) - 6px);
      background: var(--panel-strong);
      padding: 20px;
    }

    .controls {
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 12px;
      align-items: center;
    }

    .search-input {
      width: 100%;
      border: 1px solid rgba(89, 63, 40, 0.18);
      background: #fffdfa;
      border-radius: 16px;
      padding: 16px 18px;
      font-size: 1rem;
      color: var(--text);
      outline: none;
      transition: box-shadow 180ms ease, border-color 180ms ease, transform 180ms ease;
    }

    .search-input:focus {
      border-color: rgba(217, 93, 57, 0.42);
      box-shadow: 0 0 0 5px rgba(217, 93, 57, 0.12);
      transform: translateY(-1px);
    }

    .btn {
      appearance: none;
      border: 0;
      border-radius: 16px;
      padding: 15px 18px;
      font-size: 0.98rem;
      font-weight: 700;
      cursor: pointer;
      transition: transform 180ms ease, box-shadow 180ms ease, opacity 180ms ease;
      min-width: 118px;
    }

    .btn:hover {
      transform: translateY(-1px);
    }

    .btn:disabled {
      cursor: wait;
      opacity: 0.7;
      transform: none;
    }

    .btn-primary {
      background: linear-gradient(135deg, #e06c44 0%, #c34a29 100%);
      color: white;
      box-shadow: 0 16px 32px rgba(195, 74, 41, 0.25);
    }

    .btn-secondary {
      background: white;
      color: var(--text);
      border: 1px solid rgba(89, 63, 40, 0.14);
    }

    .status-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      margin-top: 16px;
      color: var(--muted);
      font-size: 0.95rem;
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.86);
      border: 1px solid rgba(89, 63, 40, 0.09);
    }

    .status-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #c49b84;
      transition: background 180ms ease, box-shadow 180ms ease;
    }

    .status-dot.running {
      background: var(--ok);
      box-shadow: 0 0 0 6px rgba(24, 121, 78, 0.12);
    }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin-top: 18px;
    }

    .meta-card {
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: rgba(255, 255, 255, 0.72);
      padding: 16px;
      min-height: 88px;
    }

    .meta-label {
      font-size: 0.8rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--accent);
      margin-bottom: 10px;
    }

    .meta-value {
      font-size: 1rem;
      color: var(--text);
      word-break: break-word;
    }

    .output-panel {
      margin-top: 18px;
      border: 1px solid rgba(36, 22, 13, 0.08);
      border-radius: 18px;
      overflow: hidden;
      background: #1f1712;
    }

    .output-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      background: rgba(255, 255, 255, 0.05);
      color: #f8dfcb;
      font-size: 0.92rem;
    }

    pre {
      margin: 0;
      padding: 18px;
      min-height: 320px;
      max-height: 54vh;
      overflow: auto;
      font-family: var(--mono);
      font-size: 0.92rem;
      line-height: 1.55;
      color: #f9eee6;
      white-space: pre-wrap;
      word-break: break-word;
      scroll-behavior: smooth;
    }

    .empty {
      color: #d7b8a2;
    }

    @media (max-width: 760px) {
      .shell {
        width: min(100vw - 20px, 980px);
        margin: 10px auto;
        padding: 18px;
      }

      .controls {
        grid-template-columns: 1fr;
      }

      .btn {
        width: 100%;
      }

      .meta-grid {
        grid-template-columns: 1fr;
      }

      pre {
        min-height: 260px;
        max-height: 48vh;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">Soulseek Frontend</div>
      <h1>Search and pull tracks with live command output.</h1>
      <p class="subcopy">Type a query, kick off <code>sldl</code>, and watch the terminal stream update in real time while the page stays focused on the latest output.</p>
    </section>

    <section class="search-panel">
      <form id="search-form" class="controls">
        <input id="search-input" class="search-input" name="query" type="text" placeholder="Artist, album, track, or mix" autocomplete="off" required>
        <button id="search-button" class="btn btn-primary" type="submit">Search</button>
        <button id="clear-button" class="btn btn-secondary" type="button">Clear</button>
      </form>

      <div class="status-row">
        <div class="status-badge">
          <span id="status-dot" class="status-dot"></span>
          <span id="status-text">Idle</span>
        </div>
        <div id="hint-text">The output panel follows live command output automatically.</div>
      </div>

      <div class="meta-grid">
        <div class="meta-card">
          <div class="meta-label">Last Search</div>
          <div id="last-search" class="meta-value">No search run yet.</div>
        </div>
        <div class="meta-card">
          <div class="meta-label">Download Path</div>
          <div class="meta-value">{{ output_path }}</div>
        </div>
      </div>

      <section class="output-panel">
        <div class="output-head">
          <span>Live `sldl` output</span>
          <span id="line-count">0 lines</span>
        </div>
        <pre id="output" class="empty">Waiting for a search.</pre>
      </section>
    </section>
  </main>

  <script>
    const form = document.getElementById("search-form");
    const input = document.getElementById("search-input");
    const searchButton = document.getElementById("search-button");
    const clearButton = document.getElementById("clear-button");
    const lastSearch = document.getElementById("last-search");
    const output = document.getElementById("output");
    const lineCount = document.getElementById("line-count");
    const statusDot = document.getElementById("status-dot");
    const statusText = document.getElementById("status-text");

    function renderState(data) {
      const lines = Array.isArray(data.output) ? data.output : [];
      output.textContent = lines.length ? lines.join("") : "Waiting for a search.";
      output.classList.toggle("empty", lines.length === 0);
      lastSearch.textContent = data.last_search || "No search run yet.";
      lineCount.textContent = `${lines.length} line${lines.length === 1 ? "" : "s"}`;
      statusDot.classList.toggle("running", Boolean(data.running));
      statusText.textContent = data.running ? "Running" : "Idle";
      output.scrollTop = output.scrollHeight;
      searchButton.disabled = Boolean(data.running);
    }

    async function refreshState() {
      const response = await fetch("/state");
      const data = await response.json();
      renderState(data);
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const query = input.value.trim();
      if (!query) {
        input.focus();
        return;
      }

      searchButton.disabled = true;
      const response = await fetch("/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query })
      });

      const data = await response.json();
      renderState(data);

      if (!response.ok) {
        alert(data.error || "Unable to start search.");
      }
    });

    clearButton.addEventListener("click", () => {
      input.value = "";
      input.focus();
    });

    const events = new EventSource("/events");
    events.onmessage = (event) => {
      const data = JSON.parse(event.data);
      renderState(data);
    };

    events.onerror = () => {
      statusText.textContent = "Reconnecting";
    };

    refreshState();
  </script>
</body>
</html>
"""


def snapshot_state():
    with state_lock:
        return {
            "last_search": app_state["last_search"],
            "output": list(app_state["output"]),
            "running": app_state["running"],
        }


def broadcast_state():
    payload = json.dumps(snapshot_state())
    with state_lock:
        listeners = list(app_state["listeners"])

    for listener in listeners:
        listener.put(payload)


def append_output(line):
    safe_line = line.replace("\r\n", "\n").replace("\r", "\n")
    with state_lock:
        app_state["output"].append(safe_line)
    broadcast_state()


def run_sldl_search(query):
    command = [
        "sldl",
        query,
        "--user",
        SOULSEEK_USERNAME,
        "--pass",
        SOULSEEK_PASSWORD,
        "-p",
        OUTPUT_PATH,
    ]

    if not shutil.which("sldl"):
        append_output("Error: `sldl` was not found in PATH. Install it before starting a search.\n")
        with state_lock:
            app_state["running"] = False
        broadcast_state()
        return

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:
        append_output(f"Failed to start sldl: {exc}\n")
        with state_lock:
            app_state["running"] = False
        broadcast_state()
        return

    assert process.stdout is not None
    for line in process.stdout:
        append_output(line)

    return_code = process.wait()
    append_output(f"\nProcess finished with exit code {return_code}.\n")

    with state_lock:
        app_state["running"] = False
    broadcast_state()


@app.get("/")
def index():
    return render_template_string(HTML, output_path=html.escape(OUTPUT_PATH))


@app.get("/state")
def get_state():
    return jsonify(snapshot_state())


@app.get("/events")
def events():
    listener = queue.Queue()
    with state_lock:
        app_state["listeners"].add(listener)

    def event_stream():
        try:
            yield f"data: {json.dumps(snapshot_state())}\n\n"
            while True:
                payload = listener.get()
                yield f"data: {payload}\n\n"
        finally:
            with state_lock:
                app_state["listeners"].discard(listener)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/search")
def start_search():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()

    if not query:
        return jsonify({"error": "Search query is required.", **snapshot_state()}), 400

    with state_lock:
        if app_state["running"]:
            return jsonify({"error": "A search is already running.", **snapshot_state()}), 409
        app_state["running"] = True
        app_state["last_search"] = query
        app_state["output"] = [f"$ sldl {query} --user {SOULSEEK_USERNAME} --pass ******** -p {OUTPUT_PATH}\n\n"]

    broadcast_state()
    worker = threading.Thread(target=run_sldl_search, args=(query,), daemon=True)
    worker.start()
    return jsonify(snapshot_state())


if __name__ == "__main__":
    Path(OUTPUT_PATH).mkdir(parents=True, exist_ok=True)
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
