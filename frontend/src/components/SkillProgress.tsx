import type { SkillPhase, SkillProgress as SkillProgressType } from "../api/types";

const STATUS_ICONS: Record<string, string> = {
  completed: "✓",
  in_progress: "▶",
  waiting: "⏸",
  pending: "○",
};

function hasStarted(progress: SkillProgressType): boolean {
  const phases = progress.phases || {};
  return Object.values(phases).some((p) => p?.status !== "pending");
}

interface Props {
  progress: SkillProgressType;
  phases: SkillPhase[];
}

export function SkillProgress({ progress, phases }: Props) {
  if (!progress.skill || !phases.length || !hasStarted(progress)) return null;

  const phaseStates = progress.phases || {};

  return (
    <div className="skill-progress">
      <strong>Skill progress:</strong> <code>{progress.skill}</code>
      {phases.map((phase) => {
        const state = phaseStates[phase.id] || {};
        const status = state.status || "pending";
        const icon = STATUS_ICONS[status] || STATUS_ICONS.pending;
        const className =
          status === "completed"
            ? "phase-completed"
            : status === "in_progress"
              ? "phase-in-progress"
              : status === "waiting"
                ? "phase-waiting"
                : "phase-pending";
        return (
          <div key={phase.id} className={className}>
            {icon} {phase.label}
            {state.detail ? ` — ${state.detail}` : ""}
          </div>
        );
      })}
    </div>
  );
}

export function SkillBadge({ skillName }: { skillName: string }) {
  return <div className="skill-badge">Using skill: {skillName}</div>;
}
