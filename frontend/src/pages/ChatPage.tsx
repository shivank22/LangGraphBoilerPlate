import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  deleteThread,
  generateTitle,
  getConfig,
  getHistory,
  listThreads,
  streamChat,
  streamResume,
} from "../api/client";
import type {
  MessageOut,
  SkillPhase,
  SkillProgress as SkillProgressType,
  ThreadInfo,
} from "../api/types";
import { AgentEmptyState } from "../components/AgentEmptyState";
import { HitlPanel } from "../components/HitlPanel";
import { MessageBubble } from "../components/MessageBubble";
import { Sidebar } from "../components/Sidebar";
import { SkillBadge, SkillProgress } from "../components/SkillProgress";
import { UserInputPanel } from "../components/UserInputPanel";
import { skillNameFromCall } from "../utils/message";

function newThreadId(): string {
  return crypto.randomUUID();
}

function isHitlInterrupt(payload: unknown): boolean {
  return (
    typeof payload === "object" &&
    payload !== null &&
    Array.isArray((payload as Record<string, unknown>).action_requests) &&
    ((payload as Record<string, unknown>).action_requests as unknown[]).length > 0
  );
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

export function ChatPage() {
  const [threadId, setThreadId] = useState(() => localStorage.getItem("thread_id") || newThreadId());
  const [threads, setThreads] = useState<ThreadInfo[]>([]);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingInterrupt, setPendingInterrupt] = useState<unknown>(null);
  const [, setRunHash] = useState<string | null>(null);
  const [progress, setProgress] = useState<SkillProgressType | null>(null);
  const [phases, setPhases] = useState<SkillPhase[]>([]);
  const [hitlTools, setHitlTools] = useState<string[]>(["call_authenticated_api"]);
  const [bearerToken, setBearerToken] = useState("");
  const [gitlabToken, setGitlabToken] = useState("");
  const [showToolActivity, setShowToolActivity] = useState(false);
  const [hitlAutoApprove, setHitlAutoApprove] = useState(
    () => localStorage.getItem(`hitl_auto_${threadId}`) === "true",
  );
  const [skillBadgeShown, setSkillBadgeShown] = useState(false);
  const [showThreadInfo, setShowThreadInfo] = useState(false);
  const titleGenerated = useRef<Set<string>>(new Set());
  const skipTypingBeforeIndex = useRef(0);

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

  const loadHistory = useCallback(async (id: string) => {
    try {
      const hist = await getHistory(id);
      setMessages(hist);
      skipTypingBeforeIndex.current = hist.length;
    } catch {
      setMessages([]);
      skipTypingBeforeIndex.current = 0;
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("thread_id", threadId);
    localStorage.setItem(`hitl_auto_${threadId}`, String(hitlAutoApprove));
  }, [threadId, hitlAutoApprove]);

  useEffect(() => {
    getConfig()
      .then((c) => setHitlTools(c.hitl_tools))
      .catch(() => {});
    refreshThreads();
    loadHistory(threadId);
  }, [threadId, refreshThreads, loadHistory]);

  const toolResults = useMemo(() => buildToolResultIndex(messages), [messages]);
  const shownToolIds = useRef(new Set<string>());

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

  const streamHandlers = useMemo(
    () => ({
      onStart: (hash: string) => setRunHash(hash),
      onProgress: (data: { progress: SkillProgressType; phases: SkillPhase[] }) => {
        setProgress(data.progress);
        setPhases(data.phases);
      },
      onMessages: (streamed: MessageOut[]) => setMessages(streamed),
    }),
    [],
  );

  const drainAutoApprovals = async (initialInterrupt: unknown): Promise<unknown> => {
    let current = initialInterrupt;
    let loops = 0;
    while (hitlAutoApprove && isHitlInterrupt(current) && loops < 20) {
      loops += 1;
      const done = await streamResume(
        threadId,
        { decision: "approve" },
        creds,
        streamHandlers,
      );
      if (!done?.interrupted) return null;
      current = done.interrupt_payload;
      if (done.messages) setMessages(done.messages);
    }
    return current;
  };

  const handleStreamDone = async (done: {
    messages: MessageOut[];
    interrupted: boolean;
    interrupt_payload?: unknown;
    run_hash?: string;
  }) => {
    setMessages(done.messages);
    if (done.run_hash) setRunHash(done.run_hash);

    let interrupt = done.interrupt_payload;
    if (done.interrupted && isHitlInterrupt(interrupt) && hitlAutoApprove) {
      interrupt = await drainAutoApprovals(interrupt);
    }
    setPendingInterrupt(interrupt ?? null);
    await maybeGenerateTitle(threadId, done.messages);
    await refreshThreads();
  };

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;
    setLoading(true);
    setSkillBadgeShown(false);
    setPendingInterrupt(null);
    const optimistic: MessageOut = { role: "user", content: text };
    skipTypingBeforeIndex.current = messages.length + 1;
    setMessages((prev) => [...prev, optimistic]);
    setInput("");

    try {
      const done = await streamChat(threadId, text, creds, {
        ...streamHandlers,
        onInterrupt: (payload) => setPendingInterrupt(payload),
      });
      if (done) await handleStreamDone(done);
    } catch (err) {
      console.error(err);
      await loadHistory(threadId);
    } finally {
      setLoading(false);
    }
  };

  const handleResume = async (body: Record<string, unknown>) => {
    setLoading(true);
    setPendingInterrupt(null);
    try {
      const done = await streamResume(threadId, body, creds, streamHandlers);
      if (done) await handleStreamDone(done);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
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
    setThreadId(id);
    setMessages([]);
    setPendingInterrupt(null);
    setRunHash(null);
    setProgress(null);
    setPhases([]);
    setHitlAutoApprove(false);
    shownToolIds.current.clear();
    skipTypingBeforeIndex.current = 0;
  };

  const handleSelectThread = (id: string) => {
    setThreadId(id);
    setPendingInterrupt(null);
    setRunHash(null);
    setProgress(null);
    setPhases([]);
    setHitlAutoApprove(localStorage.getItem(`hitl_auto_${id}`) === "true");
    shownToolIds.current.clear();
    loadHistory(id);
  };

  const handleDeleteThread = async (id: string) => {
    await deleteThread(id);
    titleGenerated.current.delete(id);
    await refreshThreads();
    if (id === threadId) handleNewConversation();
  };

  const lastHumanIndex = messages.reduce(
    (acc, m, i) => (m.role === "user" ? i : acc),
    -1,
  );

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

  return (
    <div className="app-layout">
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
        <div className="card chat-header">
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
          </div>
        )}

        <div className="card message-list">
          {messages.length === 0 && !loading && (
            <AgentEmptyState onSuggestion={(text) => sendMessage(text)} />
          )}
          {messages.map((msg, index) => {
            const shown = shownToolIds.current;
            const elements = [
              <MessageBubble
                key={`msg-${index}`}
                message={msg}
                messageIndex={index}
                toolResults={toolResults}
                shownToolIds={shown}
                hitlTools={hitlTools}
                showAllToolActivity={showToolActivity}
                skillBadgeShown={skillBadgeShown}
                onSkillBadgeShown={() => setSkillBadgeShown(true)}
                animateTyping={
                  index === lastAssistantIndex &&
                  index >= skipTypingBeforeIndex.current &&
                  !!msg.content
                }
              />,
            ];
            if (index === lastHumanIndex && showProgress && progress) {
              const skillFromCalls = messages
                .flatMap((m) => m.tool_calls || [])
                .map((c) => skillNameFromCall(c as Record<string, unknown>))
                .find(Boolean);
              if (skillFromCalls && !skillBadgeShown) {
                elements.push(<SkillBadge key="badge" skillName={skillFromCalls} />);
              }
              elements.push(
                <SkillProgress key="progress" progress={progress} phases={phases} />,
              );
            }
            return elements;
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

        {pendingInterrupt !== null && !loading && (
          <>
            {isHitlInterrupt(pendingInterrupt) && !hitlAutoApprove ? (
              <HitlPanel
                interruptPayload={pendingInterrupt as Record<string, unknown>}
                onSubmit={handleHitlSubmit}
                onApproveAll={handleApproveAll}
              />
            ) : !isHitlInterrupt(pendingInterrupt) ? (
              <UserInputPanel
                interruptPayload={pendingInterrupt as Record<string, unknown>}
                onSubmit={(answer) => handleResume({ answer })}
              />
            ) : null}
          </>
        )}

        {pendingInterrupt === null && (
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
