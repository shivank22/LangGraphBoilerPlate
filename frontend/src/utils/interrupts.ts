export function isHitlInterrupt(payload: unknown): boolean {
  return (
    typeof payload === "object" &&
    payload !== null &&
    Array.isArray((payload as Record<string, unknown>).action_requests) &&
    ((payload as Record<string, unknown>).action_requests as unknown[]).length > 0
  );
}

export function isUserInputInterrupt(payload: unknown): boolean {
  if (payload === null || payload === undefined) return false;
  if (typeof payload === "string") return true;
  if (typeof payload !== "object") return false;
  const record = payload as Record<string, unknown>;
  if (Array.isArray(record.action_requests) && record.action_requests.length > 0) {
    return false;
  }
  return record.type === "user_input" || "question" in record;
}

export function userInputPayloadFromInterrupt(
  payload: unknown,
): Record<string, unknown> | string {
  if (typeof payload === "string") return payload;
  if (typeof payload === "object" && payload !== null) {
    return payload as Record<string, unknown>;
  }
  return { question: "Please provide your answer:" };
}

/** HITL panel payload — only when the agent checkpoint reports a HITL interrupt. */
export function resolveHitlPayload(pendingInterrupt: unknown): Record<string, unknown> | null {
  if (pendingInterrupt && isHitlInterrupt(pendingInterrupt)) {
    return pendingInterrupt as Record<string, unknown>;
  }
  return null;
}

export function hitlRequestFromPayload(payload: unknown): {
  toolName: string;
  args: Record<string, unknown>;
  description: string;
} | null {
  if (!isHitlInterrupt(payload)) return null;
  const requests =
    ((payload as Record<string, unknown>).action_requests as Record<string, unknown>[]) || [];
  const req = requests[0] || {};
  return {
    toolName: String(req.name || "tool"),
    args: (req.args as Record<string, unknown>) || {},
    description: String(req.description || ""),
  };
}

/** One-line summary of what the agent is waiting to approve. */
export function hitlSummaryFromPayload(payload: unknown): string {
  const req = hitlRequestFromPayload(payload);
  if (!req) return "Approval required";
  const { toolName, args } = req;
  if (toolName === "write_file" || toolName === "edit_file") {
    const path = String(args.file_path || "");
    return path ? `Approve ${toolName} → ${path}` : `Approve ${toolName}`;
  }
  if (toolName === "call_authenticated_api") {
    const method = String(args.method || "GET").toUpperCase();
    const url = String(args.url || "");
    return url ? `Approve API call → ${method} ${url}` : "Approve API call";
  }
  return `Approve ${toolName}`;
}

/** Match a tool call to the active HITL interrupt (handles batched same-name calls). */
export function callMatchesHitlInterrupt(
  call: Record<string, unknown>,
  pendingInterrupt: unknown,
): boolean {
  const req = hitlRequestFromPayload(pendingInterrupt);
  if (!req) return false;
  if (String(call.name || "") !== req.toolName) return false;
  const callArgs = (call.args as Record<string, unknown>) || {};
  const reqArgs = req.args || {};
  const callPath = String(callArgs.file_path || "");
  const reqPath = String(reqArgs.file_path || "");
  if (callPath && reqPath) return callPath === reqPath;
  return JSON.stringify(callArgs) === JSON.stringify(reqArgs);
}

/** User-input panel payload — only when the agent checkpoint reports an ask_user interrupt. */
export function resolveUserInputPayload(
  pendingInterrupt: unknown,
): Record<string, unknown> | string | null {
  if (pendingInterrupt && isUserInputInterrupt(pendingInterrupt)) {
    return userInputPayloadFromInterrupt(pendingInterrupt);
  }
  return null;
}
