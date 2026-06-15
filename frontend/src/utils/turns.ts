import type { MessageOut } from "../api/types";

export interface TurnMessage {
  index: number;
  message: MessageOut;
}

export interface MessageTurn {
  messages: TurnMessage[];
}

export function groupMessageTurns(messages: MessageOut[]): MessageTurn[] {
  const turns: MessageTurn[] = [];
  let index = 0;

  while (index < messages.length) {
    if (messages[index].role !== "user") {
      const orphanMessages: TurnMessage[] = [];
      while (index < messages.length && messages[index].role !== "user") {
        orphanMessages.push({ index, message: messages[index] });
        index += 1;
      }
      if (orphanMessages.length > 0) {
        turns.push({ messages: orphanMessages });
      }
      continue;
    }

    const turnMessages: TurnMessage[] = [{ index, message: messages[index] }];
    index += 1;
    while (index < messages.length && messages[index].role !== "user") {
      turnMessages.push({ index, message: messages[index] });
      index += 1;
    }
    turns.push({ messages: turnMessages });
  }

  return turns;
}

export function turnHasAnyToolCalls(turnMessages: MessageOut[]): boolean {
  return turnMessages.some(
    (message) =>
      message.role === "assistant" &&
      Array.isArray(message.tool_calls) &&
      message.tool_calls.length > 0,
  );
}

/** Split a turn so tool activity renders before the final assistant reply. */
export function splitTurnForRender(turnMessages: TurnMessage[]): {
  before: TurnMessage[];
  after: TurnMessage[];
} {
  const visible = turnMessages.filter((entry) => entry.message.role !== "tool");

  let lastToolCallerIdx = -1;
  visible.forEach((entry, i) => {
    if (
      entry.message.role === "assistant" &&
      Array.isArray(entry.message.tool_calls) &&
      entry.message.tool_calls.length > 0
    ) {
      lastToolCallerIdx = i;
    }
  });

  if (lastToolCallerIdx === -1) {
    const userEnd = visible.findIndex((entry) => entry.message.role !== "user");
    if (userEnd === -1) {
      return { before: visible, after: [] };
    }
    return {
      before: visible.slice(0, userEnd),
      after: visible.slice(userEnd),
    };
  }

  return {
    before: visible.slice(0, lastToolCallerIdx + 1),
    after: visible.slice(lastToolCallerIdx + 1),
  };
}

export function shouldRenderMessageBubble(message: MessageOut): boolean {
  if (message.role === "tool") return false;
  if (message.role === "user") return true;
  if (message.role === "assistant") {
    const hasContent = Boolean(message.content?.trim());
    const hasToolCalls =
      Array.isArray(message.tool_calls) && message.tool_calls.length > 0;
    return hasContent || !hasToolCalls;
  }
  return true;
}
