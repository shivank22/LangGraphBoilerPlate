import { useEffect, useRef, useState } from "react";
import type { MessageOut, ToolStatus } from "../api/types";
import {
  describeToolCall,
  describeToolResult,
  getToolStatus,
  isHitlTool,
  parseToolResult,
} from "../utils/toolActivity";

interface Props {
  call: Record<string, unknown>;
  resultMessage?: MessageOut;
  hitlTools: string[];
  callId: string;
  displayStatus?: ToolStatus;
}

function StatusIcon({ status }: { status: ToolStatus }) {
  if (status === "running") {
    return <span className="tool-status-spinner" aria-hidden="true" />;
  }
  if (status === "queued") {
    return <span className="tool-status-icon tool-status-queued" aria-hidden="true">◷</span>;
  }
  if (status === "error") {
    return <span className="tool-status-icon tool-status-error" aria-hidden="true">✕</span>;
  }
  return <span className="tool-status-icon tool-status-success" aria-hidden="true">✓</span>;
}

export function ToolActivityCard({
  call,
  resultMessage,
  hitlTools,
  callId,
  displayStatus,
}: Props) {
  const toolName = String(call.name || "tool");
  const description = describeToolCall(call);
  const resultData = resultMessage ? parseToolResult(resultMessage.content) : null;
  const status = displayStatus ?? getToolStatus(resultMessage, resultData);
  const runningLabel = status === "queued" ? "Queued — waiting for prior approvals" : "Running…";
  const resultSummary =
    resultData !== null ? describeToolResult(toolName, resultData) : runningLabel;

  const [expanded, setExpanded] = useState(status === "running" || status === "error");
  const manualOverride = useRef(false);
  const prevStatus = useRef(status);

  useEffect(() => {
    if (prevStatus.current !== status) {
      manualOverride.current = false;
      prevStatus.current = status;
    }
    if (manualOverride.current) return;

    if (status === "running" || status === "error") {
      setExpanded(true);
      return;
    }
    const timer = window.setTimeout(() => setExpanded(false), 500);
    return () => window.clearTimeout(timer);
  }, [status]);

  const toggle = () => {
    manualOverride.current = true;
    setExpanded((v) => !v);
  };

  return (
    <div
      className="tool-disclosure"
      data-status={status}
      data-call-id={callId}
    >
      <button type="button" className="tool-disclosure-header" onClick={toggle}>
        <span className={`tool-chevron ${expanded ? "open" : ""}`} aria-hidden="true">
          ▶
        </span>
        <StatusIcon status={status} />
        <span className="tool-disclosure-name">{toolName}</span>
        {isHitlTool(toolName, hitlTools) && <span className="hitl-badge">HITL</span>}
        <span className="tool-disclosure-summary">{description}</span>
        {status === "completed" && (
          <span className="tool-disclosure-result">{resultSummary}</span>
        )}
        {status === "queued" && (
          <span className="tool-disclosure-result tool-disclosure-queued">{runningLabel}</span>
        )}
      </button>
      <div className={`tool-disclosure-body ${expanded ? "open" : ""}`}>
        <div className="tool-disclosure-inner">
          <div className="tool-section">
            <div className="tool-section-label">Input</div>
            <pre className="json-block">{JSON.stringify(call.args || {}, null, 2)}</pre>
          </div>
          {status === "running" || status === "queued" ? (
            <div className="tool-section tool-running-hint">
              {status === "running" ? <span className="tool-status-spinner" /> : null}
              {status === "queued" ? runningLabel : "Executing…"}
            </div>
          ) : resultData !== null ? (
            <div className="tool-section">
              <div className="tool-section-label">Output</div>
              <pre className="json-block">
                {typeof resultData === "object"
                  ? JSON.stringify(resultData, null, 2)
                  : String(resultData)}
              </pre>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
