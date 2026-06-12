import type { MessageOut, ToolStatus } from "../api/types";
import { truncate } from "./message";

export function isHitlTool(toolName: string, hitlTools: string[]): boolean {
  return hitlTools.includes(toolName);
}

export function shouldShowToolActivity(
  toolName: string,
  hitlTools: string[],
  showAll: boolean,
): boolean {
  return isHitlTool(toolName, hitlTools) || showAll;
}

function parseContent(content: unknown): unknown {
  if (typeof content === "object" && content !== null) return content;
  if (typeof content === "string") {
    const text = content.trim();
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }
  return content;
}

export function describeToolCall(call: Record<string, unknown>): string {
  const name = String(call.name || "tool");
  const args = (call.args as Record<string, unknown>) || {};
  if (typeof args !== "object") return name;

  if (name === "call_authenticated_api") {
    const method = String(args.method || "GET").toUpperCase();
    const url = String(args.url || "");
    return url ? `${method} ${url}` : method;
  }
  if (name === "ask_user") return truncate(String(args.question || "User input"));
  if (name === "load_application_questionnaire" || name === "save_questionnaire_answer") {
    return args.aa_code ? `AA ${args.aa_code}` : name;
  }
  if (name === "build_discovery_artifact") {
    return args.aa_code ? `AA ${args.aa_code}` : "discovery JSON";
  }
  if (name === "load_migration_scores") {
    return args.aa_code ? `scores AA ${args.aa_code}` : "migration scores";
  }
  if (name === "load_target_inventory") return "target inventory";
  if (name === "build_migration_recommendation") {
    return `min_score=${args.min_score ?? 0.7}`;
  }
  if (name === "read_file" || name === "write_file" || name === "edit_file") {
    return truncate(String(args.file_path || ""));
  }
  const keys = Object.keys(args);
  if (keys.length) return `${keys[0]}=${truncate(String(args[keys[0]]))}`;
  return name;
}

export function describeToolResult(toolName: string, data: unknown): string {
  if (typeof data === "object" && data !== null) {
    const d = data as Record<string, unknown>;
    if (d.error) return `Error: ${truncate(String(d.error))}`;
    if (toolName === "call_authenticated_api" && d.status_code !== undefined) {
      return `HTTP ${d.status_code}`;
    }
    if (toolName === "save_questionnaire_answer" && d.unanswered_count !== undefined) {
      return `${d.answered_count ?? "?"} answered, ${d.unanswered_count} remaining`;
    }
    if (toolName === "build_discovery_artifact") {
      if (d.application_count !== undefined && d.server_count !== undefined) {
        return `${d.server_count} servers, ${d.application_count} applications`;
      }
    }
    if (toolName === "load_migration_scores") {
      if (d.valid_score_count !== undefined && d.total !== undefined) {
        return `${d.valid_score_count}/${d.total} valid scores`;
      }
    }
    if (toolName === "load_target_inventory") {
      if (d.available_count !== undefined && d.total !== undefined) {
        return `${d.available_count}/${d.total} clusters available`;
      }
    }
    if (toolName === "build_migration_recommendation" && d.eligible_count !== undefined) {
      return `${d.eligible_count} eligible for migration`;
    }
    if (toolName === "load_application_questionnaire") {
      return `${d.answered_count ?? 0}/${d.total ?? 0} answered`;
    }
  }
  return truncate(String(data));
}

export function toolStatusLine(
  toolName: string,
  data: unknown,
  hitlTools: string[],
): { status: string; color: string } {
  if (data === null || data === undefined) return { status: "Requested", color: "#888" };
  if (typeof data === "object" && data !== null && (data as Record<string, unknown>).error) {
    return { status: "Executed · Error", color: "#c0392b" };
  }
  if (isHitlTool(toolName, hitlTools)) {
    return { status: "Approved · Executed", color: "#2e7d4f" };
  }
  return { status: "Executed", color: "#4c8bf5" };
}

export function parseToolResult(content: string): unknown {
  return parseContent(content);
}

export function getToolStatus(
  resultMessage: MessageOut | undefined,
  resultData: unknown,
): ToolStatus {
  if (!resultMessage) return "running";
  if (
    typeof resultData === "object" &&
    resultData !== null &&
    (resultData as Record<string, unknown>).error
  ) {
    return "error";
  }
  return "completed";
}
