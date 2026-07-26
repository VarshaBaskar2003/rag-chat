import { useEffect, useRef } from "react";
import "./ChatWindow.css";

export default function ChatWindow({ messages }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="chat-window">
      {messages.length === 0 && (
        <div className="chat-window__empty">
          <p>👋 Select a document from the sidebar and ask me anything about it.</p>
        </div>
      )}
      {messages.map((msg, index) => (
        <div
          key={index}
          className={`chat-message chat-message--${msg.role}`}
        >
          <div className="chat-message__bubble">
            <p className="chat-message__text">{msg.content}</p>
          </div>

          {msg.sources && msg.sources.length > 0 && (
            <div className="chat-message__sources">
              <span className="chat-message__sources-label">📎 Sources: </span>
              {msg.sources.map((s, i) => (
                <span key={i} className="chat-message__source-chip">
                  Page {s.page}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}