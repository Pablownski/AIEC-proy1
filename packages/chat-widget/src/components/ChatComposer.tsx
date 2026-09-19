import { useState, type KeyboardEvent } from "react";

export interface ChatComposerProps {
  placeholder?: string;
  disabled?: boolean;
  onSend: (content: string) => void;
}

export function ChatComposer({ placeholder, disabled, onSend }: ChatComposerProps) {
  const [value, setValue] = useState("");

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form
      className="agichat-composer"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <label htmlFor="agichat-composer-input" className="agichat-visually-hidden">
        Escribe un mensaje
      </label>
      <textarea
        id="agichat-composer-input"
        className="agichat-composer__input"
        value={value}
        placeholder={placeholder ?? "Escribe un mensaje..."}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button
        type="submit"
        className="agichat-composer__send"
        aria-label="Enviar mensaje"
        disabled={disabled || !value.trim()}
      >
        Enviar
      </button>
    </form>
  );
}
