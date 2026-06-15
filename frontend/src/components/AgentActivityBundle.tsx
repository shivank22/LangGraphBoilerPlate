import type { ReactNode } from "react";

interface Props {
  title: string;
  subtitle?: string;
  children: ReactNode;
}

export function AgentActivityBundle({ title, subtitle, children }: Props) {
  return (
    <div className="agent-activity-bundle">
      <div className="agent-activity-bundle-header">
        <span className="agent-activity-bundle-title">{title}</span>
        {subtitle && <span className="agent-activity-bundle-subtitle">{subtitle}</span>}
      </div>
      <div className="agent-activity-bundle-body">{children}</div>
    </div>
  );
}
