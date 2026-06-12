export function parseJsonRecursively(content: unknown): unknown {
  if (typeof content === "object" && content !== null) {
    if (Array.isArray(content)) return content.map(parseJsonRecursively);
    const obj: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(content)) {
      obj[k] = parseJsonRecursively(v);
    }
    return obj;
  }
  if (typeof content === "string") {
    const trimmed = content.trim();
    if (!trimmed) return content;
    try {
      const parsed = JSON.parse(trimmed);
      return parseJsonRecursively(parsed);
    } catch {
      return content;
    }
  }
  return content;
}

export function skillNameFromCall(call: Record<string, unknown>): string | null {
  if (call.name !== "read_file") return null;
  const args = (call.args as Record<string, unknown>) || {};
  const path = String(args.file_path || "").replace(/\\/g, "/");
  const parts = path.split("/").filter(Boolean);
  if (!parts.length || !parts[parts.length - 1].toUpperCase().startsWith("SKILL")) return null;
  const idx = parts.indexOf("skills");
  if (idx >= 0 && idx + 1 < parts.length) return parts[idx + 1];
  return null;
}

export function truncate(text: string, limit = 72): string {
  const normalized = text.split(/\s+/).join(" ");
  return normalized.length <= limit ? normalized : `${normalized.slice(0, limit - 1)}…`;
}
