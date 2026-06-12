import type {
  ChatResponse,
  ConfigResponse,
  Credentials,
  MessageOut,
  StreamDoneEvent,
  StreamProgressEvent,
  ThreadInfo,
} from "./types";

const API_BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function getConfig(): Promise<ConfigResponse> {
  return request("/config");
}

export async function listThreads(): Promise<ThreadInfo[]> {
  const data = await request<{ threads: ThreadInfo[] }>("/threads");
  return data.threads;
}

export async function getHistory(threadId: string): Promise<MessageOut[]> {
  const data = await request<{ messages: MessageOut[] }>(`/chat/${threadId}/history`);
  return data.messages;
}

export async function deleteThread(threadId: string): Promise<void> {
  await request(`/chat/${threadId}`, { method: "DELETE" });
}

export async function generateTitle(
  threadId: string,
  userMessage: string,
  assistantReply: string,
): Promise<string> {
  const data = await request<{ title: string }>(`/threads/${threadId}/title/generate`, {
    method: "POST",
    body: JSON.stringify({ user_message: userMessage, assistant_reply: assistantReply }),
  });
  return data.title;
}

export interface StreamHandlers {
  onStart?: (runHash: string) => void;
  onProgress?: (data: StreamProgressEvent) => void;
  onMessages?: (messages: MessageOut[]) => void;
  onInterrupt?: (payload: unknown) => void;
  onDone?: (data: StreamDoneEvent) => void;
  onError?: (error: Error) => void;
}

async function consumeSse(
  path: string,
  body: Record<string, unknown>,
  handlers: StreamHandlers,
): Promise<StreamDoneEvent | null> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    throw new Error(`Stream failed: HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let doneEvent: StreamDoneEvent | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const lines = part.split("\n");
      let event = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) event = line.slice(7);
        if (line.startsWith("data: ")) data = line.slice(6);
      }
      if (!data) continue;
      const parsed = JSON.parse(data);
      if (event === "start") handlers.onStart?.(parsed.run_hash);
      if (event === "progress") handlers.onProgress?.(parsed);
      if (event === "messages") handlers.onMessages?.(parsed.messages);
      if (event === "interrupt") handlers.onInterrupt?.(parsed.interrupt_payload);
      if (event === "done") {
        doneEvent = parsed as StreamDoneEvent;
        handlers.onDone?.(doneEvent);
      }
    }
  }
  return doneEvent;
}

export async function streamChat(
  threadId: string,
  message: string,
  creds: Credentials,
  handlers: StreamHandlers,
): Promise<StreamDoneEvent | null> {
  return consumeSse(
    `/chat/${threadId}/stream`,
    { message, ...creds },
    handlers,
  );
}

export async function streamResume(
  threadId: string,
  body: Record<string, unknown>,
  creds: Credentials,
  handlers: StreamHandlers,
): Promise<StreamDoneEvent | null> {
  return consumeSse(`/chat/${threadId}/resume/stream`, { ...body, ...creds }, handlers);
}

export async function chatBlocking(
  threadId: string,
  message: string,
  creds: Credentials,
): Promise<ChatResponse> {
  return request(`/chat/${threadId}`, {
    method: "POST",
    body: JSON.stringify({ message, ...creds }),
  });
}

export async function resumeBlocking(
  threadId: string,
  body: Record<string, unknown>,
  creds: Credentials,
): Promise<ChatResponse> {
  return request(`/chat/${threadId}/resume`, {
    method: "POST",
    body: JSON.stringify({ ...body, ...creds }),
  });
}
