export interface MessageOut {
  role: "user" | "assistant" | "tool";
  content: string;
  tool_calls?: Array<Record<string, unknown>> | null;
  tool_name?: string | null;
  tool_call_id?: string | null;
}

export interface ChatResponse {
  thread_id: string;
  run_hash?: string | null;
  reply: string;
  messages: MessageOut[];
  interrupted: boolean;
  interrupt_payload?: unknown;
}

export interface ThreadInfo {
  thread_id: string;
  label: string;
  short_id: string;
}

export interface SkillPhase {
  id: string;
  label: string;
}

export interface SkillProgress {
  skill?: string;
  phases?: Record<string, { status: string; detail?: string }>;
  updated_at?: string;
  current_phase?: string;
}

export interface ConfigResponse {
  model_name: string;
  temperature: number;
  max_iterations: number;
  max_input_chars: number;
  guardrail_blocklist: string[];
  hitl_tools: string[];
  log_level: string;
  db_path: string;
}

export interface Credentials {
  bearer_token?: string;
  gitlab_token?: string;
}

export type ToolStatus = "running" | "queued" | "completed" | "error";

export type UiMode = "idle" | "running" | "hitl" | "user_input";

export interface HistoryResponse {
  thread_id: string;
  messages: MessageOut[];
  interrupted?: boolean;
  interrupt_payload?: unknown;
  ui_mode?: UiMode;
  run_hash?: string | null;
  progress?: SkillProgress | null;
  phases?: SkillPhase[];
}

export interface StreamDoneEvent {
  thread_id: string;
  run_hash: string;
  reply: string;
  messages: MessageOut[];
  interrupted: boolean;
  interrupt_payload?: unknown;
  ui_mode?: UiMode;
  progress?: SkillProgress | null;
  phases?: SkillPhase[];
}

export interface StreamInterruptEvent {
  interrupt_payload: unknown;
  ui_mode: UiMode;
}

export interface StreamProgressEvent {
  progress: SkillProgress;
  phases: SkillPhase[];
}
