import { useEffect, useState } from "react";
import { getConfig } from "../api/client";
import type { ConfigResponse } from "../api/types";

export function InfoPage() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getConfig()
      .then(setConfig)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="info-page">Failed to load config: {error}</div>;
  if (!config) return <div className="info-page">Loading…</div>;

  return (
    <div className="info-page">
      <h1>Info</h1>
      <p className="caption">Runtime configuration and middleware details for this agent.</p>

      <h2>Model</h2>
      <div className="info-metrics">
        <div className="info-card">
          <div className="caption">Model</div>
          <strong>{config.model_name}</strong>
        </div>
        <div className="info-card">
          <div className="caption">Temperature</div>
          <strong>{config.temperature}</strong>
        </div>
      </div>

      <h2>Middleware</h2>
      <p className="caption">Applied in this order (outer wraps inner).</p>

      <div className="info-card">
        <h3>1. GuardrailMiddleware</h3>
        <ul>
          <li>
            <strong>Max model calls per run:</strong> {config.max_iterations}
          </li>
          <li>
            <strong>Max input characters:</strong> {config.max_input_chars}
          </li>
          <li>
            <strong>Blocklist:</strong> {config.guardrail_blocklist.join(", ") || "(none)"}
          </li>
        </ul>
      </div>

      <div className="info-card">
        <h3>2. LoggingMiddleware</h3>
        <ul>
          <li>Logs before/after every model call.</li>
          <li>Captures message count, latency, token usage, and response preview.</li>
          <li>
            <strong>Log level:</strong> {config.log_level}
          </li>
        </ul>
      </div>

      <div className="info-card">
        <h3>3. HumanInTheLoopMiddleware</h3>
        <ul>
          <li>Pauses the graph before executing any listed tool.</li>
          <li>UI surfaces Approve / Edit / Reject buttons.</li>
          <li>
            <strong>Gated tools:</strong> {config.hitl_tools.join(", ") || "(none)"}
          </li>
        </ul>
      </div>

      <h2>Persistence</h2>
      <div className="info-card">
        <ul>
          <li>
            <strong>Checkpointer:</strong> SqliteSaver
          </li>
          <li>
            <strong>Database path:</strong> {config.db_path}
          </li>
          <li>Every node execution writes a checkpoint keyed by thread_id.</li>
          <li>Conversations survive process restarts.</li>
        </ul>
      </div>

      <h2>FastAPI REST endpoints</h2>
      <div className="info-card">
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th align="left">Method</th>
              <th align="left">Path</th>
              <th align="left">Description</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>GET</td>
              <td>/health</td>
              <td>Liveness probe</td>
            </tr>
            <tr>
              <td>GET</td>
              <td>/config</td>
              <td>Runtime configuration</td>
            </tr>
            <tr>
              <td>GET</td>
              <td>/threads</td>
              <td>List conversations</td>
            </tr>
            <tr>
              <td>POST</td>
              <td>/chat/{"{thread_id}"}</td>
              <td>Send a message</td>
            </tr>
            <tr>
              <td>POST</td>
              <td>/chat/{"{thread_id}"}/stream</td>
              <td>Send a message (SSE)</td>
            </tr>
            <tr>
              <td>POST</td>
              <td>/chat/{"{thread_id}"}/resume</td>
              <td>Resume after HITL</td>
            </tr>
            <tr>
              <td>GET</td>
              <td>/chat/{"{thread_id}"}/history</td>
              <td>Load full history</td>
            </tr>
            <tr>
              <td>DELETE</td>
              <td>/chat/{"{thread_id}"}</td>
              <td>Delete a thread</td>
            </tr>
          </tbody>
        </table>
        <p className="caption">Interactive docs: http://localhost:8000/docs</p>
      </div>
    </div>
  );
}
