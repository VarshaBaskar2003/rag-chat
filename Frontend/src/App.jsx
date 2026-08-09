import "./App.css";
import Sidebar from "./components/SideBar";
import Header from "./components/Header";
import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";
import { useChat } from "./hooks/useChat";

export default function App() {
  const {
    activeCollection,
    currentMessages,
    loading,
    handleUploadSuccess,
    handleSelectDocument,
    handleSend,
    handleClearHistory,
  } = useChat();

  return (
    <div className="app">
      <Sidebar
        activeCollection={activeCollection}
        onUploadSuccess={handleUploadSuccess}
        onSelectDocument={handleSelectDocument}
      />
      <div className="app__main">
        <Header
          activeCollection={activeCollection}
          messageCount={currentMessages.length}
          onClearHistory={handleClearHistory}
        />
        <ChatWindow messages={currentMessages} />
        <ChatInput onSend={handleSend} disabled={loading} />
      </div>
    </div>
  );
}