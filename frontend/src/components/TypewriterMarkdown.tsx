import { MarkdownContent } from "./MarkdownContent";
import { useAcceleratingTypewriter } from "../hooks/useAcceleratingTypewriter";

interface Props {
  text: string;
  active: boolean;
}

export function TypewriterMarkdown({ text, active }: Props) {
  const { displayed, isTyping } = useAcceleratingTypewriter(text, active);

  return (
    <span className="typewriter-text">
      <MarkdownContent content={displayed} />
      {isTyping && <span className="typewriter-cursor" aria-hidden="true" />}
    </span>
  );
}
