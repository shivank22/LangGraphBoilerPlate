import type { MessageOut } from "../api/types";
import { parseJsonRecursively } from "../utils/message";
import { MarkdownContent } from "./MarkdownContent";
import { TypewriterMarkdown } from "./TypewriterMarkdown";

const USER_AVATAR = "🧑‍💻";
const BOT_AVATAR = "👾";

interface Props {
  message: MessageOut;
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
    return (
      <div className="assistant-block">
        {text && (
          <div className="bubble-row bot prose-row">
            <div className="bubble-avatar bot-avatar" aria-hidden="true">
              {BOT_AVATAR}
            </div>
            <div className="assistant-prose">
              {isPlainText ? (
                animateTyping ? (
                  <TypewriterMarkdown text={String(parsed)} active={animateTyping} />
                ) : (
                  <MarkdownContent content={String(parsed)} />
                )
              ) : (
                <div className="bubble bot">
                  <div className="bubble-content">
                    <StructuredContent data={parsed} />
                  </div>
                </div>
              )}
            </div>
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
