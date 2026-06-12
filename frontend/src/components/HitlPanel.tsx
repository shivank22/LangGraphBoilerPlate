import { useState } from "react";

interface ActionRequest {
  name?: string;
  args?: Record<string, unknown>;
  description?: string;
}

interface Props {
  interruptPayload: Record<string, unknown>;
  onSubmit: (decision: string, editedArgs?: Record<string, unknown>, toolName?: string) => void;
  onApproveAll: () => void;
}

export function HitlPanel({ interruptPayload, onSubmit, onApproveAll }: Props) {
  const actionRequests = (interruptPayload.action_requests as ActionRequest[]) || [];
  const reviewConfigs = (interruptPayload.review_configs as Record<string, unknown>[]) || [];
  const request = actionRequests[0] || {};
  const toolName = request.name || "tool";
  const toolArgs = request.args || {};
  const description = request.description || "";
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

  return (
    <div className="panel">
      <h3>Approve tool call</h3>
      <p className="caption">
        The agent paused before running one tool. Approve, edit the arguments, or reject.
      </p>
      {error && <p style={{ color: "#f85149" }}>{error}</p>}
      <p>
        <strong>Tool:</strong> <code>{toolName}</code>
      </p>
      {description && <p className="caption">{description}</p>}
      <label className="caption">Arguments (edit before approving if needed):</label>
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
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" className="btn-primary" onClick={handleSubmit}>
          Submit decision
        </button>
        <button type="button" className="btn-secondary" onClick={onApproveAll}>
          Approve all for this conversation
        </button>
      </div>
    </div>
  );
}
