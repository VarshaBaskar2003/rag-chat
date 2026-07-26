import "./Header.css";

export default function Header({ activeCollection, messageCount, onClearHistory }) {
  return (
    <div className="header">
      {activeCollection ? (
        <div className="header__inner">
          <span>
            Chatting with:{" "}
            <strong className="header__doc-name">
              {activeCollection.replace(/_/g, " ")}
            </strong>
            {messageCount > 0 && (
              <span className="header__count">
                ({Math.floor(messageCount / 2)} questions asked)
              </span>
            )}
          </span>
          <button onClick={onClearHistory} className="header__clear-btn">
            Clear chat
          </button>
        </div>
      ) : (
        <span className="header__placeholder">
          Select a document to start chatting
        </span>
      )}
    </div>
  );
}