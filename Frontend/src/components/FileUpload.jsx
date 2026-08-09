import { useState, useEffect } from "react";
import { uploadPDF } from "../api/ragApi";
import "./FileUpload.css";

export default function FileUpload({ onUploadSuccess }) {
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState(null); // { text, type: "success"|"error" }
  const [dragOver, setDragOver] = useState(false);

  // Auto-hide message after 4 seconds
  useEffect(() => {
    if (message) {
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
    setMessage({ text: "Indexing your document...", type: "loading" });

    try {
      const result = await uploadPDF(file);
      setMessage({
        text: `✅ Indexed ${result.chunk_count} chunks`,
        type: "success",
      });
      onUploadSuccess(result.collection_name);
    } catch (error) {
      setMessage({
        text: `❌ ${error.response?.data?.detail || "Upload failed"}`,
        type: "error",
      });
    } finally {
      setUploading(false);
    }
  };

  const handleFileChange = (e) => {
    processFile(e.target.files[0]);
    e.target.value = ""; // reset input so same file can be re-uploaded
  };

  // Drag and drop handlers
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

      {/* Drag and drop zone */}
      <label
        className={`file-upload__dropzone ${dragOver ? "file-upload__dropzone--active" : ""} ${uploading ? "file-upload__dropzone--disabled" : ""}`}
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
          {uploading ? "Uploading..." : "Click or drag PDF here"}
        </span>
      </label>

      {/* Status message — auto disappears after 4s */}
      {message && (
        <div className={`file-upload__message file-upload__message--${message.type}`}>
          {message.text}
        </div>
      )}
    </div>
  );
}