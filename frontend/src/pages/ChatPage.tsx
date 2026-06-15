import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  deleteThread,
  generateTitle,
  getConfig,
  getThreadState,
  listThreads,
  streamChat,
  streamResume,
} from "../api/client";
import type {
  HistoryResponse,
  MessageOut,
  SkillPhase,
  SkillProgress as SkillProgressType,
  StreamDoneEvent,
  ThreadInfo,
  UiMode,
} from "../api/types";
import { AgentActivityBundle } from "../components/AgentActivityBundle";
import { AgentEmptyState } from "../components/AgentEmptyState";
import { HitlPanel } from "../components/HitlPanel";
import { MessageBubble } from "../components/MessageBubble";
import { Sidebar } from "../components/Sidebar";
import { SkillBadge, SkillProgress } from "../components/SkillProgress";
import { TurnToolList } from "../components/TurnToolList";
import { UserInputPanel } from "../components/UserInputPanel";
import {
  groupMessageTurns,
  shouldRenderMessageBubble,
  splitTurnForRender,
  turnHasAnyToolCalls,
} from "../utils/turns";
import { resolveHitlPayload, resolveUserInputPayload, hitlSummaryFromPayload } from "../utils/interrupts";
import { turnHasRenderableToolCards } from "../utils/toolActivity";

function newThreadId(): string {
  return crypto.randomUUID();
}

function buildToolResultIndex(messages: MessageOut[]): Map<string, MessageOut> {
  const index = new Map<string, MessageOut>();
  for (const msg of messages) {
    if (msg.role === "tool" && msg.tool_call_id) {
      index.set(msg.tool_call_id, msg);
    }
  }
  return index;
}

type ThreadSnapshot = HistoryResponse | StreamDoneEvent;

function applyThreadState(
  state: ThreadSnapshot,
  setters: {
    setMessages: (messages: MessageOut[]) => void;
    setPendingInterrupt: (payload: unknown) => void;
    setUiMode: (mode: UiMode) => void;
    setRunHash: (hash: string | null) => void;
    setProgress: (progress: SkillProgressType | null) => void;
    setPhases: (phases: SkillPhase[]) => void;
  },
) {
  setters.setMessages(state.messages);
  setters.setUiMode(state.ui_mode ?? "idle");
  if (state.run_hash) setters.setRunHash(state.run_hash);
  setters.setProgress(state.progress ?? null);
  setters.setPhases(state.phases ?? []);
  if (state.interrupted && state.interrupt_payload != null) {
    setters.setPendingInterrupt(state.interrupt_payload);
  } else {
    setters.setPendingInterrupt(null);
  }
}

export function ChatPage() {
  const [threadId, setThreadId] = useState(() => {
    const stored = localStorage.getItem("thread_id");
    if (stored) return stored;
    const id = newThreadId();
    localStorage.setItem("thread_id", id);
    return id;
  });
  const [threads, setThreads] = useState<ThreadInfo[]>([]);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [uiMode, setUiMode] = useState<UiMode>("idle");
  const [pendingInterrupt, setPendingInterrupt] = useState<unknown>(null);
  const [, setRunHash] = useState<string | null>(null);
  const [progress, setProgress] = useState<SkillProgressType | null>(null);
  const [phases, setPhases] = useState<SkillPhase[]>([]);
  const [hitlTools, setHitlTools] = useState<string[]>(["call_authenticated_api"]);
  const [bearerToken, setBearerToken] = useState("");
  const [gitlabToken, setGitlabToken] = useState("");
  const [showToolActivity, setShowToolActivity] = useState(
    () => localStorage.getItem("show_tool_activity") !== "false",
  );
  const [hitlAutoApprove, setHitlAutoApprove] = useState(
    () => localStorage.getItem(`hitl_auto_${threadId}`) === "true",
  );
  const [showThreadInfo, setShowThreadInfo] = useState(false);
  const titleGenerated = useRef<Set<string>>(new Set());
  const skipTypingBeforeIndex = useRef(0);
  const messagesRef = useRef(messages);
  const shownToolIds = useRef(new Set<string>());
  const autoDrainingRef = useRef(false);

  messagesRef.current = messages;

  const stateSetters = useMemo(
    () => ({
      setMessages,
      setPendingInterrupt,
      setUiMode,
      setRunHash,
      setProgress,
      setPhases,
    }),
    [],
  );

  const creds = useMemo(
    () => ({
      bearer_token: bearerToken || undefined,
      gitlab_token: gitlabToken || undefined,
    }),
    [bearerToken, gitlabToken],
  );

  const refreshThreads = useCallback(async () => {
    try {
      const list = await listThreads();
      setThreads(list);
    } catch {
      setThreads([]);
    }
  }, []);

  const streamHandlers = useMemo(
    () => ({
      onStart: (hash: string) => setRunHash(hash),
      onProgress: (data: { progress: SkillProgressType; phases: SkillPhase[] }) => {
        setProgress(data.progress);
        setPhases(data.phases);
      },
      onMessages: (streamed: MessageOut[]) => {
        setMessages(streamed);
      },
      onInterrupt: (data: { interrupt_payload: unknown; ui_mode: UiMode }) => {
        setPendingInterrupt(data.interrupt_payload);
        setUiMode(data.ui_mode);
      },
      onDone: (done: StreamDoneEvent) => {
        applyThreadState(done, stateSetters);
      },
    }),
    [stateSetters],
  );

  const drainAutoApprovals = useCallback(
    async (start: StreamDoneEvent): Promise<void> => {
      let current = start;
      let loops = 0;
      while (hitlAutoApprove && (current.ui_mode ?? "idle") === "hitl" && loops < 20) {
        loops += 1;
        const done = await streamResume(
          threadId,
          { decision: "approve" },
          creds,
          streamHandlers,
        );
        if (!done) return;
        applyThreadState(done, stateSetters);
        current = done;
      }
    },
    [creds, hitlAutoApprove, streamHandlers, stateSetters, threadId],
  );

  const syncThreadState = useCallback(
    async (id: string) => {
      try {
        const snapshot = await getThreadState(id);
        applyThreadState(snapshot, stateSetters);
        skipTypingBeforeIndex.current = snapshot.messages.length;

        if (
          hitlAutoApprove &&
          (snapshot.ui_mode ?? "idle") === "hitl" &&
          !autoDrainingRef.current
        ) {
          autoDrainingRef.current = true;
          setLoading(true);
          try {
            await drainAutoApprovals(snapshot as StreamDoneEvent);
            const refreshed = await getThreadState(id);
            applyThreadState(refreshed, stateSetters);
            skipTypingBeforeIndex.current = refreshed.messages.length;
          } finally {
            autoDrainingRef.current = false;
            setLoading(false);
          }
        }
      } catch {
        setMessages([]);
        skipTypingBeforeIndex.current = 0;
        setPendingInterrupt(null);
        setUiMode("idle");
        setProgress(null);
        setPhases([]);
      }
    },
    [drainAutoApprovals, hitlAutoApprove, stateSetters],
  );

  useEffect(() => {
    localStorage.setItem(`hitl_auto_${threadId}`, String(hitlAutoApprove));
    localStorage.setItem("show_tool_activity", String(showToolActivity));
  }, [threadId, hitlAutoApprove, showToolActivity]);

  useEffect(() => {
    getConfig()
      .then((c) => setHitlTools(c.hitl_tools))
      .catch(() => {});
    refreshThreads();
    syncThreadState(threadId);
  }, [threadId, refreshThreads, syncThreadState]);

  useEffect(() => {
    const onFocus = () => {
      if (uiMode === "hitl" || uiMode === "user_input") {
        void syncThreadState(threadId);
      }
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [threadId, uiMode, syncThreadState]);

  const toolResults = useMemo(() => buildToolResultIndex(messages), [messages]);

  const maybeGenerateTitle = async (id: string, msgs: MessageOut[]) => {
    if (titleGenerated.current.has(id)) return;
    const humans = msgs.filter((m) => m.role === "user");
    const ais = msgs.filter((m) => m.role === "assistant" && m.content);
    if (!humans.length || !ais.length) return;
    titleGenerated.current.add(id);
    try {
      await generateTitle(id, humans[0].content, ais[ais.length - 1].content);
      refreshThreads();
    } catch {
      titleGenerated.current.delete(id);
    }
  };

  const handleStreamDone = async (done: StreamDoneEvent) => {
    applyThreadState(done, stateSetters);
    if (done.ui_mode === "hitl" && hitlAutoApprove) {
      await drainAutoApprovals(done);
      await syncThreadState(threadId);
    }
    await maybeGenerateTitle(threadId, messagesRef.current);
    await refreshThreads();
  };

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;
    setLoading(true);
    setUiMode("running");
    setPendingInterrupt(null);
    const optimistic: MessageOut = { role: "user", content: text };
    skipTypingBeforeIndex.current = messages.length + 1;
    setMessages((prev) => [...prev, optimistic]);
    setInput("");

    try {
      const done = await streamChat(threadId, text, creds, streamHandlers);
      if (done) await handleStreamDone(done);
    } catch (err) {
      console.error(err);
      await syncThreadState(threadId);
    } finally {
      setLoading(false);
    }
  };

  const handleResume = async (body: Record<string, unknown>) => {
    setLoading(true);
    setUiMode("running");
    setPendingInterrupt(null);
    try {
      const done = await streamResume(threadId, body, creds, streamHandlers);
      if (done) await handleStreamDone(done);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
      await syncThreadState(threadId);
    }
  };

  const handleHitlSubmit = (
    decision: string,
    editedArgs?: Record<string, unknown>,
    toolName?: string,
  ) => {
    if (decision === "edit") {
      handleResume({ decision: "edit", edited_args: editedArgs, tool_name: toolName });
    } else {
      handleResume({ decision });
    }
  };

  const handleApproveAll = () => {
    setHitlAutoApprove(true);
    handleResume({ decision: "approve" });
  };

  const handleNewConversation = () => {
    const id = newThreadId();
    localStorage.setItem("thread_id", id);
    setThreadId(id);
    setMessages([]);
    setPendingInterrupt(null);
    setUiMode("idle");
    setRunHash(null);
    setProgress(null);
    setPhases([]);
    setHitlAutoApprove(false);
    shownToolIds.current.clear();
    skipTypingBeforeIndex.current = 0;
  };

  const handleSelectThread = (id: string) => {
    localStorage.setItem("thread_id", id);
    setThreadId(id);
    setPendingInterrupt(null);
    setUiMode("idle");
    setRunHash(null);
    setProgress(null);
    setPhases([]);
    setHitlAutoApprove(localStorage.getItem(`hitl_auto_${id}`) === "true");
    shownToolIds.current.clear();
    syncThreadState(id);
  };

  const handleDeleteThread = async (id: string) => {
    await deleteThread(id);
    titleGenerated.current.delete(id);
    await refreshThreads();
    if (id === threadId) handleNewConversation();
  };

  const messageTurns = groupMessageTurns(messages);
  const lastTurn = messageTurns[messageTurns.length - 1];

  const showProgress =
    progress &&
    progress.skill &&
    phases.length > 0 &&
    Object.values(progress.phases || {}).some((p) => p?.status !== "pending");

  const hasLiveTools =
    loading &&
    messages.some(
      (m) => m.role === "assistant" && m.tool_calls && m.tool_calls.length > 0,
    );

  const lastAssistantIndex = messages.reduce(
    (acc, m, i) => (m.role === "assistant" ? i : acc),
    -1,
  );

  const agentPaused = uiMode === "hitl" || uiMode === "user_input";
  const pendingHitl = uiMode === "hitl";
  const pendingAsk = uiMode === "user_input";
  const hitlPayload = pendingHitl ? resolveHitlPayload(pendingInterrupt) : null;
  const userInputPayload = pendingAsk ? resolveUserInputPayload(pendingInterrupt) : null;
  const showChatInput = !loading && uiMode === "idle";
  const showPauseDock = agentPaused && (hitlPayload || userInputPayload);

  return (
    <div className="app-layout chat-page">
      <Sidebar
        threads={threads}
        activeThreadId={threadId}
        bearerToken={bearerToken}
        gitlabToken={gitlabToken}
        hitlAutoApprove={hitlAutoApprove}
        showToolActivity={showToolActivity}
        onNewConversation={handleNewConversation}
        onSelectThread={handleSelectThread}
        onDeleteThread={handleDeleteThread}
        onBearerTokenChange={setBearerToken}
        onGitlabTokenChange={setGitlabToken}
        onHitlAutoApproveChange={setHitlAutoApprove}
        onShowToolActivityChange={setShowToolActivity}
      />
      <div className="main-content">
        <div className="chat-header">
          <h1>DICE Agent</h1>
          <button
            type="button"
            className="icon-btn"
            onClick={() => setShowThreadInfo(!showThreadInfo)}
            title="Conversation details"
          >
            i
          </button>
        </div>
        {showThreadInfo && (
          <div className="panel">
            <strong>Thread id</strong>
            <pre className="json-block">{threadId}</pre>
            <strong>UI mode</strong>
            <pre className="json-block">{uiMode}</pre>
          </div>
        )}

        <div className="message-list">
          {messages.length === 0 && !loading && (
            <AgentEmptyState onSuggestion={(text) => sendMessage(text)} />
          )}
          {messageTurns.map((turn, turnIndex) => {
            const isLastTurn = turn === lastTurn;
            const turnMessages = turn.messages.map((entry) => entry.message);
            const hasToolCalls = turnHasAnyToolCalls(turnMessages);
            const showTurnProgress = isLastTurn && showProgress && progress;
            const showTurnHitl = isLastTurn && pendingHitl;
            const showTurnAsk = isLastTurn && pendingAsk;
            const hasRenderableTools = turnHasRenderableToolCards(
              turn.messages,
              toolResults,
              hitlTools,
              showToolActivity,
              showTurnHitl ? pendingInterrupt : undefined,
              showTurnAsk,
            );
            const showActivityBundle =
              hasToolCalls ||
              hasRenderableTools ||
              showTurnProgress ||
              showTurnHitl ||
              showTurnAsk;
            const { before, after } = splitTurnForRender(turn.messages);

            const renderBubble = ({ index, message: msg }: (typeof turn.messages)[0]) => {
              if (!shouldRenderMessageBubble(msg)) return null;
              return (
                <MessageBubble
                  key={`msg-${index}`}
                  message={msg}
                  animateTyping={
                    index === lastAssistantIndex &&
                    index >= skipTypingBeforeIndex.current &&
                    !!msg.content
                  }
                />
              );
            };

            const pauseSection =
              isLastTurn && agentPaused ? (
                <div
                  className={`activity-bundle-section activity-pause-boundary activity-pause-first${
                    showTurnProgress ? " activity-bundle-section-divided" : ""
                  }`}
                >
                  <div className="activity-pause-label">
                    {showTurnAsk
                      ? "Paused — waiting for your input"
                      : hitlPayload
                        ? hitlSummaryFromPayload(hitlPayload)
                        : "Paused — approval required"}
                  </div>
                  {showTurnHitl && hitlPayload ? (
                    <p className="caption">Use the approval panel below to continue.</p>
                  ) : showTurnAsk && userInputPayload ? (
                    <p className="caption">Use the input panel below to continue.</p>
                  ) : null}
                </div>
              ) : null;

            const activityBundle = showActivityBundle ? (
              <AgentActivityBundle
                key="activity"
                title="Agent activity"
                subtitle={
                  showTurnHitl
                    ? "Approval required"
                    : showTurnAsk
                      ? "Your input needed"
                      : showTurnProgress && progress?.skill
                        ? String(progress.skill)
                        : undefined
                }
              >
                {pauseSection}
                {showTurnProgress && (
                  <div
                    className={`activity-bundle-section${
                      pauseSection ? " activity-bundle-section-divided" : ""
                    }`}
                  >
                    {progress?.skill && (
                      <SkillBadge skillName={String(progress.skill)} />
                    )}
                    <SkillProgress progress={progress!} phases={phases} nested />
                  </div>
                )}
                {hasRenderableTools && (
                  <div
                    className={`activity-bundle-section${
                      showTurnProgress || pauseSection ? " activity-bundle-section-divided" : ""
                    }`}
                  >
                    <TurnToolList
                      turnMessages={turn.messages}
                      toolResults={toolResults}
                      shownToolIds={shownToolIds.current}
                      hitlTools={hitlTools}
                      showAllToolActivity={showToolActivity}
                      agentUiMode={isLastTurn ? uiMode : "idle"}
                      pendingInterrupt={showTurnHitl ? pendingInterrupt : undefined}
                    />
                  </div>
                )}
              </AgentActivityBundle>
            ) : null;

            return (
              <div
                key={`turn-${turn.messages[0]?.index ?? turnIndex}`}
                className="message-turn"
              >
                {before.map(renderBubble)}
                {activityBundle}
                {after.map(renderBubble)}
              </div>
            );
          })}
          {loading && !hasLiveTools && (
            <div className="bubble-row bot">
              <div className="bubble-avatar bot-avatar" aria-hidden="true">
                👾
              </div>
              <div className="bubble bot typing-bubble">
                <span className="typing-dots">
                  <span />
                  <span />
                  <span />
                </span>
              </div>
            </div>
          )}
        </div>

        {showPauseDock && (
          <div className="chat-pause-dock">
            {hitlPayload ? (
              <HitlPanel
                key={hitlSummaryFromPayload(hitlPayload)}
                interruptPayload={hitlPayload}
                submitting={loading}
                onSubmit={handleHitlSubmit}
                onApproveAll={handleApproveAll}
              />
            ) : userInputPayload ? (
              <UserInputPanel
                key={
                  typeof userInputPayload === "string"
                    ? userInputPayload
                    : String(
                        (userInputPayload as Record<string, unknown>).question || "",
                      )
                }
                interruptPayload={userInputPayload}
                submitting={loading}
                onSubmit={(answer) => handleResume({ answer })}
              />
            ) : null}
          </div>
        )}

        {showChatInput && (
          <form
            className="chat-input-area"
            onSubmit={(e) => {
              e.preventDefault();
              sendMessage(input);
            }}
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Message the agent..."
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim()}>
              Send
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
