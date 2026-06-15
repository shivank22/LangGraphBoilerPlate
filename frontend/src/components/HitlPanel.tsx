import { useState } from "react";
import { hitlSummaryFromPayload } from "../utils/interrupts";

interface ActionRequest {
  name?: string;
  args?: Record<string, unknown>;
  description?: string;
}

interface Props {
  interruptPayload: Record<string, unknown>;
  onSubmit: (decision: string, editedArgs?: Record<string, unknown>, toolName?: string) => void;
  onApproveAll: () => void;
  nested?: boolean;
  submitting?: boolean;
}

export function HitlPanel({
  interruptPayload,
  onSubmit,
  onApproveAll,
  nested = false,
  submitting = false,
}: Props) {
  const actionRequests = (interruptPayload.action_requests as ActionRequest[]) || [];
  const reviewConfigs = (interruptPayload.review_configs as Record<string, unknown>[]) || [];
  const request = actionRequests[0] || {};
  const toolName = request.name || "tool";
  const toolArgs = request.args || {};
  const description = request.description || "";
  const summary = hitlSummaryFromPayload(interruptPayload);
  const config = reviewConfigs[0] || {};
  const allowed = (
    (config.allowed_decisions as string[]) || ["approve", "edit", "reject"]
  ).filter((d) => d !== "respond");

  const [editedArgsJson, setEditedArgsJson] = useState(JSON.stringify(toolArgs, null, 2));
  const [choice, setChoice] = useState(allowed[0] || "approve");
  const [error, setError] = useState("");

  const handleSubmit = () => {
    if (choice === "edit") {
      try {
        const args = JSON.parse(editedArgsJson);
        onSubmit("edit", args, toolName);
      } catch (e) {
        setError(`Edited arguments are not valid JSON: ${e}`);
        return;
      }
    } else {
      onSubmit(choice);
    }
  };

  const handleQuickApprove = () => onSubmit("approve");

  return (
    <div className={`activity-panel-content${nested ? " activity-panel-nested" : ""}`}>
      {!nested && <h3>Approve tool call</h3>}
      <p className="hitl-summary">{summary}</p>
      {!nested && (
        <p className="caption">
          The agent paused before running this tool. Each gated tool needs your approval.
        </p>
      )}
      {error && <p style={{ color: "#f85149" }}>{error}</p>}
      {description && <p className="caption">{description}</p>}
      <div className="hitl-quick-actions">
        <button
          type="button"
          className="btn-primary"
          onClick={handleQuickApprove}
          disabled={submitting}
        >
          {submitting ? "Approving…" : "Approve"}
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={onApproveAll}
          disabled={submitting}
        >
          Auto-approve all
        </button>
      </div>
      <details className="hitl-details">
        <summary>Edit arguments or reject</summary>
        <p>
          <strong>Tool:</strong> <code>{toolName}</code>
        </p>
        <label className="caption">Arguments:</label>
        <textarea value={editedArgsJson} onChange={(e) => setEditedArgsJson(e.target.value)} />
        <div style={{ margin: "12px 0" }}>
          {allowed.map((opt) => (
            <label key={opt} style={{ marginRight: 16 }}>
              <input
                type="radio"
                name="hitl-choice"
                value={opt}
                checked={choice === opt}
                onChange={() => setChoice(opt)}
              />{" "}
              {opt}
            </label>
          ))}
        </div>
        <button
          type="button"
          className="btn-secondary"
          onClick={handleSubmit}
          disabled={submitting}
        >
          {submitting ? "Submitting…" : "Submit decision"}
        </button>
      </details>
    </div>
  );
}
