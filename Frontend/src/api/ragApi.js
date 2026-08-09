import axios from "axios";

// In production: uses VITE_API_URL environment variable set in Netlify
// In development: falls back to localhost
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const uploadPDF = async (file) => {
  const formData = new FormData();
  formData.append("file", file);
  const response = await axios.post(`${API_BASE}/upload`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

export const queryDocument = async (question, collectionName) => {
  const response = await axios.post(`${API_BASE}/query`, {
    question: question,
    collection_name: collectionName,
  });
  return response.data;
};

export const getDocuments = async () => {
  const response = await axios.get(`${API_BASE}/documents`);
  return response.data;
};

export const deleteDocument = async (collectionName) => {
  const response = await axios.delete(`${API_BASE}/documents/${collectionName}`);
  return response.data;
};

export const saveMessage = async (sessionId, collectionName, role, content, sources = []) => {
  await axios.post(`${API_BASE}/history`, {
    session_id: sessionId,
    collection_name: collectionName,
    role,
    content,
    sources,
  });
};

export const loadHistory = async (sessionId, collectionName) => {
  const response = await axios.get(`${API_BASE}/history/${sessionId}/${collectionName}`);
  return response.data;
};

export const clearHistoryDB = async (sessionId, collectionName) => {
  await axios.delete(`${API_BASE}/history/${sessionId}/${collectionName}`);
};