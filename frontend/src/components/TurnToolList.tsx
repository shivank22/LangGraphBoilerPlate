import type { ReactNode } from "react";
import type { MessageOut, UiMode } from "../api/types";
import type { TurnMessage } from "../utils/turns";
import { skillNameFromCall } from "../utils/message";
import {
  getToolDisplayStatus,
  parseToolResult,
  shouldHideToolCallForHitl,
  shouldShowToolActivity,
} from "../utils/toolActivity";
import { ToolActivityCard } from "./ToolActivityCard";

interface Props {
  turnMessages: TurnMessage[];
  toolResults: Map<string, MessageOut>;
  shownToolIds: Set<string>;
  hitlTools: string[];
  showAllToolActivity: boolean;
  agentUiMode: UiMode;
  pendingInterrupt?: unknown;
  onSkillDetected?: (skill: string) => void;
}

export function TurnToolList({
  turnMessages,
  toolResults,
  shownToolIds,
  hitlTools,
  showAllToolActivity,
  agentUiMode,
  pendingInterrupt,
  onSkillDetected,
}: Props) {
  const cards: ReactNode[] = [];

  turnMessages.forEach(({ index: messageIndex, message: msg }) => {
    if (msg.role !== "assistant") return;
    (msg.tool_calls || []).forEach((call, callIndex) => {
      const callRecord = call as Record<string, unknown>;
      const toolName = String(callRecord.name || "tool");
      const skill = skillNameFromCall(callRecord);
      if (skill) onSkillDetected?.(skill);
      if (!shouldShowToolActivity(toolName, hitlTools, showAllToolActivity)) return;

      const callId = String(callRecord.id || `${messageIndex}_${callIndex}`);
      const resultMessage = callId ? toolResults.get(callId) : undefined;
      const hideForHitl =
        agentUiMode === "hitl" &&
        !resultMessage &&
        shouldHideToolCallForHitl(callRecord, pendingInterrupt);
      const hideForAskUser = agentUiMode === "user_input" && toolName === "ask_user" && !resultMessage;
      if (hideForHitl || hideForAskUser) return;

      if (callId) shownToolIds.add(callId);

      const resultData = resultMessage ? parseToolResult(resultMessage.content) : null;
      const displayStatus = getToolDisplayStatus(
        callRecord,
        resultMessage,
        resultData,
        hitlTools,
        agentUiMode === "hitl" ? pendingInterrupt : undefined,
      );

      cards.push(
        <ToolActivityCard
          key={`${messageIndex}-${callIndex}-${callId}`}
          call={callRecord}
          resultMessage={resultMessage}
          hitlTools={hitlTools}
          callId={callId}
          displayStatus={displayStatus}
        />,
      );
    });
  });

  if (!cards.length) return null;

  return <div className="tool-disclosure-group">{cards}</div>;
}
