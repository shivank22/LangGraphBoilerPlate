import type { ThreadInfo } from "../api/types";

interface Props {
  threads: ThreadInfo[];
  activeThreadId: string;
  bearerToken: string;
  gitlabToken: string;
  hitlAutoApprove: boolean;
  showToolActivity: boolean;
  onNewConversation: () => void;
  onSelectThread: (threadId: string) => void;
  onDeleteThread: (threadId: string) => void;
  onBearerTokenChange: (value: string) => void;
  onGitlabTokenChange: (value: string) => void;
  onHitlAutoApproveChange: (value: boolean) => void;
  onShowToolActivityChange: (value: boolean) => void;
}

export function Sidebar({
  threads,
  activeThreadId,
  bearerToken,
  gitlabToken,
  hitlAutoApprove,
  showToolActivity,
  onNewConversation,
  onSelectThread,
  onDeleteThread,
  onBearerTokenChange,
  onGitlabTokenChange,
  onHitlAutoApproveChange,
  onShowToolActivityChange,
}: Props) {
  return (
    <aside className="sidebar">
      <button type="button" className="btn-primary" onClick={onNewConversation}>
        + New conversation
      </button>

      <div className="card">
        <div className="card-title">API Authentication</div>
        <label htmlFor="bearer-token">Bearer token</label>
        <input
          id="bearer-token"
          type="password"
          value={bearerToken}
          onChange={(e) => onBearerTokenChange(e.target.value)}
          placeholder="1234 for mock API"
        />
        <label htmlFor="gitlab-token">GitLab PAT</label>
        <input
          id="gitlab-token"
          type="password"
          value={gitlabToken}
          onChange={(e) => onGitlabTokenChange(e.target.value)}
          placeholder="Paste GitLab token here…"
        />
      </div>

      <div className="card">
        <div className="card-title">Tool settings</div>
        <div className="toggle-row">
          <input
            type="checkbox"
            id="hitl-auto"
            checked={hitlAutoApprove}
            onChange={(e) => onHitlAutoApproveChange(e.target.checked)}
          />
          <label htmlFor="hitl-auto">Auto-approve gated tools</label>
        </div>
        <div className="toggle-row">
          <input
            type="checkbox"
            id="show-tools"
            checked={showToolActivity}
            onChange={(e) => onShowToolActivityChange(e.target.checked)}
          />
          <label htmlFor="show-tools">Show all tool activity</label>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Conversations</div>
        {threads.length === 0 ? (
          <span className="caption">No saved conversations yet.</span>
        ) : (
          <div className="thread-list">
            {threads.map((t) => (
              <div key={t.thread_id} className="thread-item">
                <button
                  type="button"
                  className={t.thread_id === activeThreadId ? "active" : ""}
                  onClick={() => onSelectThread(t.thread_id)}
                >
                  {t.label}
                </button>
                <button
                  type="button"
                  className="delete-btn"
                  onClick={() => onDeleteThread(t.thread_id)}
                  title="Delete this conversation"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
