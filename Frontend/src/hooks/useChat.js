import { useState, useEffect } from "react";
import { queryDocument, saveMessage, loadHistory, clearHistoryDB } from "../api/ragApi";

export function useChat() {
  const [activeCollection, setActiveCollection] = useState(null);
  const [loading, setLoading] = useState(false);
  const [chatHistories, setChatHistories] = useState(() => {
    const saved = localStorage.getItem("rag_chat_histories");
    return saved ? JSON.parse(saved) : {};
  });

  const [sessionId] = useState(() => {
    const saved = localStorage.getItem("rag_session_id");
    if (saved) return saved;
    const newId = `session_${Date.now()}`;
    localStorage.setItem("rag_session_id", newId);
    return newId;
  });

  // Persist chat histories to localStorage on every change
  useEffect(() => {
    localStorage.setItem("rag_chat_histories", JSON.stringify(chatHistories));
  }, [chatHistories]);

  // Current document's messages
  const currentMessages = activeCollection
    ? chatHistories[activeCollection] || []
    : [];

  const addMessage = (collectionName, message) => {
    setChatHistories((prev) => ({
      ...prev,
      [collectionName]: [...(prev[collectionName] || []), message],
    }));
  };

  const handleUploadSuccess = (collectionName) => {
    setActiveCollection(collectionName);
    setChatHistories((prev) => ({
      ...prev,
      [collectionName]: prev[collectionName] || [],
    }));
  };

  const handleSelectDocument = async (collectionName) => {
    setActiveCollection(collectionName);
    try {
      const history = await loadHistory(sessionId, collectionName);
      setChatHistories((prev) => ({
        ...prev,
        [collectionName]: history.map((m) => ({
          role: m.role,
          content: m.content,
          sources: m.sources,
        })),
      }));
    } catch (error) {
      console.error("Failed to load history:", error);
    }
  };

  const handleSend = async (question) => {
    if (!activeCollection) {
      alert("Please select a document first.");
      return;
    }

    addMessage(activeCollection, { role: "user", content: question });
    await saveMessage(sessionId, activeCollection, "user", question);
    setLoading(true);

    const targetCollection = activeCollection;

    try {
      const result = await queryDocument(question, targetCollection);
      addMessage(targetCollection, {
        role: "assistant",
        content: result.answer,
        sources: result.sources,
      });
      await saveMessage(
        sessionId,
        targetCollection,
        "assistant",
        result.answer,
        result.sources
      );
    } catch (error) {
      addMessage(targetCollection, {
        role: "assistant",
        content: `Error: ${error.response?.data?.detail || "Something went wrong."}`,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleClearHistory = async () => {
    if (activeCollection) {
      setChatHistories((prev) => ({ ...prev, [activeCollection]: [] }));
      await clearHistoryDB(sessionId, activeCollection);
    }
  };

  // Return everything components need
  return {
    activeCollection,
    currentMessages,
    loading,
    sessionId,
    handleUploadSuccess,
    handleSelectDocument,
    handleSend,
    handleClearHistory,
  };
}