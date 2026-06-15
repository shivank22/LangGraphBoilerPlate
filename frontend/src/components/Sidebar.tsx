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
      <div className="sidebar-inner">
        <button type="button" className="sidebar-btn-primary" onClick={onNewConversation}>
          + New conversation
        </button>

        <div className="sidebar-divider" />

        <div className="sidebar-section">
          <span className="caption">API Authentication</span>
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

        <div className="sidebar-divider" />

        <div className="sidebar-section">
          <span className="caption">Tool approvals</span>
          <div className="toggle-row">
            <input
              type="checkbox"
              id="hitl-auto"
              checked={hitlAutoApprove}
              onChange={(e) => onHitlAutoApproveChange(e.target.checked)}
            />
            <label htmlFor="hitl-auto">Auto-approve gated tools (this conversation)</label>
          </div>
        </div>

        <div className="sidebar-divider" />

        <div className="sidebar-section">
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

        <div className="sidebar-divider" />

        <div className="sidebar-section sidebar-section-grow">
          <span className="caption">Previous conversations</span>
          {threads.length === 0 ? (
            <span className="caption sidebar-empty">No saved conversations yet.</span>
          ) : (
            <div className="thread-list">
              {threads.map((t) => {
                const isActive = t.thread_id === activeThreadId;
                return (
                  <div key={t.thread_id} className="thread-item">
                    <button
                      type="button"
                      className={`thread-btn ${isActive ? "active" : ""}`}
                      onClick={() => onSelectThread(t.thread_id)}
                    >
                      {(isActive ? "▶  " : "   ") + t.label}
                    </button>
                    <button
                      type="button"
                      className="thread-delete-btn"
                      onClick={() => onDeleteThread(t.thread_id)}
                      title="Delete this conversation"
                      aria-label="Delete conversation"
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
