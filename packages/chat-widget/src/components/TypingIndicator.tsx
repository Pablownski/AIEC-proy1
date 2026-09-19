export interface TypingIndicatorProps {
  agentName: string;
}

export function TypingIndicator({ agentName }: TypingIndicatorProps) {
  return (
    <div className="agichat-typing" role="status" aria-live="polite">
      <span className="agichat-typing__dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      {agentName} está escribiendo...
    </div>
  );
}
