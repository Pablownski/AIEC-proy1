import { DamianAvatar } from "./DamianAvatar";
import type { AvatarState } from "./damian-sprites";

export interface ChatHeaderProps {
  agentName: string;
  description?: string;
  avatarUrl?: string;
  avatarState?: AvatarState;
}

export function ChatHeader({ agentName, description, avatarUrl, avatarState = "idle" }: ChatHeaderProps) {
  return (
    <header className="agichat-header">
      {avatarUrl ? <img
        className="agichat-header__avatar"
        src={avatarUrl}
        alt=""
        aria-hidden="true"
      /> : <DamianAvatar name={agentName} state={avatarState} />}
      <div className="agichat-header__text">
        <p className="agichat-header__name">{agentName}</p>
        {description && <p className="agichat-header__description">{description}</p>}
      </div>
    </header>
  );
}
