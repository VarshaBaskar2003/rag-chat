import { useState, useEffect } from "react";
import { uploadPDF, pingServer } from "../api/ragApi";
import "./FileUpload.css";

export default function FileUpload({ onUploadSuccess }) {
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  // Auto-hide message after 4 seconds
  useEffect(() => {
    if (message?.type === "success") {
      const timer = setTimeout(() => setMessage(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [message]);

  const processFile = async (file) => {
    if (!file) return;

    if (!file.name.endsWith(".pdf")) {
      setMessage({ text: "Only PDF files are supported.", type: "error" });
      return;
    }

    setUploading(true);

    // Step 1 — wake the server first
    setMessage({
      text: "⏳ Waking up server... (first request may take 60s)",
      type: "loading",
    });
    await pingServer();

    // Step 2 — now upload
    setMessage({
      text: "📤 Uploading and indexing PDF...",
      type: "loading",
    });

    try {
      const result = await uploadPDF(file);
      setMessage({
        text: `✅ Indexed ${result.chunk_count} chunks successfully`,
        type: "success",
      });
      onUploadSuccess(result.collection_name);
    } catch (error) {
      setMessage({
        text: `❌ ${error.response?.data?.detail || "Upload failed. Try again."}`,
        type: "error",
      });
    } finally {
      setUploading(false);
    }
  };

  const handleFileChange = (e) => {
    processFile(e.target.files[0]);
    e.target.value = "";
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => setDragOver(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    processFile(e.dataTransfer.files[0]);
  };

  return (
    <div className="file-upload">
      <p className="file-upload__label">Upload a PDF</p>

      <label
        className={`file-upload__dropzone 
          ${dragOver ? "file-upload__dropzone--active" : ""} 
          ${uploading ? "file-upload__dropzone--disabled" : ""}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept=".pdf"
          onChange={handleFileChange}
          disabled={uploading}
          className="file-upload__input"
        />
        <span className="file-upload__icon">
          {uploading ? "⏳" : "📎"}
        </span>
        <span className="file-upload__hint">
          {uploading ? "Please wait..." : "Click or drag PDF here"}
        </span>
      </label>

      {message && (
        <div className={`file-upload__message file-upload__message--${message.type}`}>
          {message.text}
        </div>
      )}
    </div>
  );
}