const SUGGESTIONS = [
  "Discover resources for application AA312312",
  "Build a migration recommendation",
  "What skills can you run?",
];

interface Props {
  onSuggestion: (text: string) => void;
}

export function AgentEmptyState({ onSuggestion }: Props) {
  return (
    <div className="agent-empty">
      <div className="agent-empty-avatar">
        <span className="agent-empty-emoji">👾</span>
        <span className="agent-empty-shadow" />
      </div>
      <h2 className="agent-empty-title">Hi, I'm the DICE Agent</h2>
      <p className="agent-empty-sub">
        Ask me about application discovery or migration recommendations — or try one of
        these:
      </p>
      <div className="agent-empty-suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" className="suggestion-chip" onClick={() => onSuggestion(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
