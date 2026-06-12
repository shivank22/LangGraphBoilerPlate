import { useState } from "react";

interface Props {
  interruptPayload: Record<string, unknown> | string;
  onSubmit: (answer: string) => void;
}

export function UserInputPanel({ interruptPayload, onSubmit }: Props) {
  const payload =
    typeof interruptPayload === "object" && interruptPayload !== null
      ? interruptPayload
      : { question: String(interruptPayload) };
  const question = String(payload.question || "Please provide your answer:");
  const dropdownValues = (payload.dropdown_values as string[]) || [];
  const [answer, setAnswer] = useState(dropdownValues[0] || "");

  return (
    <div className="panel">
      <h3>Your input is needed</h3>
      <p className="caption">The agent paused to collect your answer before continuing.</p>
      {dropdownValues.length > 0 ? (
        <select
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          style={{
            width: "100%",
            padding: 8,
            background: "#0d1117",
            color: "#fafafa",
            border: "1px solid #30363d",
            borderRadius: 6,
          }}
        >
          {dropdownValues.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      ) : (
        <input
          type="text"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder={question}
          style={{
            width: "100%",
            padding: 8,
            background: "#0d1117",
            color: "#fafafa",
            border: "1px solid #30363d",
            borderRadius: 6,
          }}
        />
      )}
      <p className="caption" style={{ marginTop: 8 }}>
        {question}
      </p>
      <button
        type="button"
        className="btn-primary"
        style={{ marginTop: 12 }}
        onClick={() => onSubmit(answer)}
        disabled={!answer.trim()}
      >
        Submit answer
      </button>
    </div>
  );
}
