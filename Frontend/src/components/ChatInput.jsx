import { useState } from "react";
import "./ChatInput.css";

export default function ChatInput({ onSend, disabled }) {
  const [question, setQuestion] = useState("");

  const handleSubmit = () => {
    if (!question.trim() || disabled) return;
    onSend(question.trim());
    setQuestion("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="chat-input">
      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask a question about your document... (Enter to send)"
        disabled={disabled}
        rows={2}
        className="chat-input__textarea"
      />
      <button
        onClick={handleSubmit}
        disabled={disabled || !question.trim()}
        className={`chat-input__button ${disabled || !question.trim() ? "chat-input__button--disabled" : ""}`}
      >
        {disabled ? "..." : "Send"}
      </button>
    </div>
  );
}