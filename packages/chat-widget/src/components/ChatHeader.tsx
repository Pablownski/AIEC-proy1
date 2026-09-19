export interface ChatHeaderProps {
  agentName: string;
  description?: string;
  avatarUrl?: string;
}

export function ChatHeader({ agentName, description, avatarUrl }: ChatHeaderProps) {
  return (
    <header className="agichat-header">
      <img
        className="agichat-header__avatar"
        src={avatarUrl ?? "/agichat-default-avatar.svg"}
        alt=""
        aria-hidden="true"
      />
      <div className="agichat-header__text">
        <p className="agichat-header__name">{agentName}</p>
        {description && <p className="agichat-header__description">{description}</p>}
      </div>
    </header>
  );
}
