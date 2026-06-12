import type { MessageOut } from "../api/types";
import { parseJsonRecursively, skillNameFromCall } from "../utils/message";
import { shouldShowToolActivity } from "../utils/toolActivity";
import { ToolActivityCard } from "./ToolActivityCard";
import { TypewriterText } from "./TypewriterText";

const USER_AVATAR = "🧑‍💻";
const BOT_AVATAR = "👾";

interface Props {
  message: MessageOut;
  messageIndex: number;
  toolResults: Map<string, MessageOut>;
  shownToolIds: Set<string>;
  hitlTools: string[];
  showAllToolActivity: boolean;
  skillBadgeShown: boolean;
  onSkillBadgeShown: () => void;
  animateTyping?: boolean;
}

function StructuredContent({ data }: { data: unknown }) {
  if (typeof data === "object" && data !== null && !Array.isArray(data)) {
    const obj = data as Record<string, unknown>;
    return (
      <div>
        {"uuid" in obj && <h4>Directory: {String(obj.uuid)}</h4>}
        {"result" in obj && typeof obj.result === "object" && obj.result !== null && (
          <div>
            {(obj.result as Record<string, unknown>).exit_code === 0 ? (
              <p style={{ color: "var(--success)" }}>Execution succeeded</p>
            ) : (
              <p style={{ color: "var(--danger)" }}>
                Execution failed (exit code{" "}
                {String((obj.result as Record<string, unknown>).exit_code)})
              </p>
            )}
          </div>
        )}
        <pre className="json-block">{JSON.stringify(data, null, 2)}</pre>
      </div>
    );
  }
  if (Array.isArray(data)) {
    return (
      <div>
        <strong>List Content:</strong>
        <ol>
          {data.map((item, i) => (
            <li key={i}>{String(item)}</li>
          ))}
        </ol>
      </div>
    );
  }
  return <span>{String(data)}</span>;
}

export function MessageBubble({
  message,
  messageIndex,
  toolResults,
  shownToolIds,
  hitlTools,
  showAllToolActivity,
  skillBadgeShown,
  onSkillBadgeShown,
  animateTyping = false,
}: Props) {
  if (message.role === "user") {
    const content = parseJsonRecursively(message.content);
    return (
      <div className="bubble-row user">
        <div className="bubble user">
          <div className="bubble-content">{String(content)}</div>
        </div>
        <div className="bubble-avatar user-avatar" aria-hidden="true">
          {USER_AVATAR}
        </div>
      </div>
    );
  }

  if (message.role === "assistant") {
    const text = message.content || "";
    const parsed = text ? parseJsonRecursively(text.trim()) : "";
    const isPlainText = typeof parsed === "string" || typeof parsed === "number";
    const toolCalls = message.tool_calls || [];
    const visibleTools = toolCalls.filter((call) => {
      const toolName = String((call as Record<string, unknown>).name || "tool");
      return shouldShowToolActivity(toolName, hitlTools, showAllToolActivity);
    });

    return (
      <div className="assistant-block">
        {text && (
          <div className="bubble-row bot">
            <div className="bubble-avatar bot-avatar" aria-hidden="true">
              {BOT_AVATAR}
            </div>
            <div className="bubble bot">
              <div className="bubble-content">
                {isPlainText ? (
                  <TypewriterText
                    text={String(parsed)}
                    active={animateTyping}
                  />
                ) : (
                  <StructuredContent data={parsed} />
                )}
              </div>
            </div>
          </div>
        )}
        {visibleTools.length > 0 && (
          <div className="tool-disclosure-group">
            {toolCalls.map((call, callIndex) => {
              const callRecord = call as Record<string, unknown>;
              const toolName = String(callRecord.name || "tool");
              const skill = skillNameFromCall(callRecord);
              if (skill && !skillBadgeShown) {
                onSkillBadgeShown();
              }
              if (!shouldShowToolActivity(toolName, hitlTools, showAllToolActivity)) {
                return null;
              }
              const callId = String(callRecord.id || `${messageIndex}_${callIndex}`);
              const resultMessage = callId ? toolResults.get(callId) : undefined;
              if (callId) shownToolIds.add(callId);
              return (
                <ToolActivityCard
                  key={`${messageIndex}-${callIndex}-${callId}`}
                  call={callRecord}
                  resultMessage={resultMessage}
                  hitlTools={hitlTools}
                  callId={callId}
                />
              );
            })}
          </div>
        )}
      </div>
    );
  }

  if (message.role === "tool") {
    return null;
  }

  return null;
}
