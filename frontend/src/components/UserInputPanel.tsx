import { useState } from "react";
import { userInputPayloadFromInterrupt } from "../utils/interrupts";

interface Props {
  interruptPayload: Record<string, unknown> | string;
  onSubmit: (answer: string) => void;
  nested?: boolean;
  submitting?: boolean;
}

export function UserInputPanel({
  interruptPayload,
  onSubmit,
  nested = false,
  submitting = false,
}: Props) {
  const payload = userInputPayloadFromInterrupt(interruptPayload);
  const record =
    typeof payload === "object" ? payload : { question: String(payload) };
  const question = String(record.question || "Please provide your answer:");
  const dropdownValues = (record.dropdown_values as string[]) || [];
  const [answer, setAnswer] = useState(dropdownValues[0] || "");

  return (
    <div className={`activity-panel-content${nested ? " activity-panel-nested" : ""}`}>
      {!nested && <h3>Your input is needed</h3>}
      <p className="user-input-question">{question}</p>
      {dropdownValues.length > 0 ? (
        <select
          className="user-input-field"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
        >
          {dropdownValues.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      ) : (
        <textarea
          className="user-input-field user-input-textarea"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="Type your answer…"
          rows={3}
        />
      )}
      <button
        type="button"
        className="btn-primary user-input-submit"
        onClick={() => onSubmit(answer)}
        disabled={!answer.trim() || submitting}
      >
        {submitting ? "Submitting…" : "Submit answer"}
      </button>
    </div>
  );
}
