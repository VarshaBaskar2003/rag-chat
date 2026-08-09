import { useEffect, useState, useRef } from "react";
import axios from "axios";
import { getDocuments, deleteDocument } from "../api/ragApi";
import "./DocumentList.css";

const API_BASE = "https://rag-chat-thku.onrender.com";

export default function DocumentList({ activeCollection, onSelect }) {
  const [documents, setDocuments] = useState([]);
  const [menuOpen, setMenuOpen] = useState(null);
  const [serverStatus, setServerStatus] = useState("checking");
  const menuRef = useRef(null);

  // Check server status and fetch documents on mount
  useEffect(() => {
    const checkServerAndFetch = async () => {
      setServerStatus("checking");
      try {
        await axios.get(`${API_BASE}/`, { timeout: 120000 });
        setServerStatus("online");
        fetchDocuments();
      } catch {
        setServerStatus("offline");
      }
    };
    checkServerAndFetch();
  }, []);

  useEffect(() => {
    if (serverStatus === "online") {
      fetchDocuments();
    }
  }, [activeCollection, serverStatus]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const fetchDocuments = async () => {
    try {
      const docs = await getDocuments();
      setDocuments(docs);
    } catch (error) {
      console.error("Failed to fetch documents:", error);
    }
  };

  const handleDelete = async (e, collectionName) => {
    e.stopPropagation();
    const confirmed = window.confirm(
      `Delete "${collectionName.replace(/_/g, " ")}"? This cannot be undone.`
    );
    if (!confirmed) return;
    try {
      await deleteDocument(collectionName);
      setMenuOpen(null);
      fetchDocuments();
    } catch (error) {
      console.error("Failed to delete:", error);
      alert("Failed to delete document.");
    }
  };

  const handleShare = (e, collectionName) => {
    e.stopPropagation();
    const shareUrl = `${window.location.origin}?doc=${collectionName}`;
    navigator.clipboard.writeText(shareUrl);
    alert("Link copied to clipboard!");
    setMenuOpen(null);
  };

  const handleDownload = async (e, collectionName) => {
    e.stopPropagation();
    try {
      const response = await fetch(`${API_BASE}/files/list`);
      const files = await response.json();

      const match = files.find((f) => {
        const converted = f
          .toLowerCase()
          .replace(/\s+/g, "_")
          .replace(/\./g, "_")
          .replace(/-/g, "_");
        return converted === collectionName;
      });

      if (match) {
        window.open(`${API_BASE}/uploads/${match}`, "_blank");
      } else {
        alert("Original file not found in uploads folder.");
      }
    } catch (err) {
      console.error(err);
      alert("Download failed.");
    }
    setMenuOpen(null);
  };

  const handleRename = (e, collectionName) => {
    e.stopPropagation();
    const newName = window.prompt(
      "Enter new display name:",
      collectionName.replace(/_/g, " ")
    );
    if (newName) {
      const names = JSON.parse(
        localStorage.getItem("doc_display_names") || "{}"
      );
      names[collectionName] = newName;
      localStorage.setItem("doc_display_names", JSON.stringify(names));
      fetchDocuments();
    }
    setMenuOpen(null);
  };

  const toggleMenu = (e, collectionName) => {
    e.stopPropagation();
    setMenuOpen(menuOpen === collectionName ? null : collectionName);
  };

  const getDisplayName = (collectionName) => {
    const names = JSON.parse(
      localStorage.getItem("doc_display_names") || "{}"
    );
    return names[collectionName] || collectionName.replace(/_/g, " ");
  };

  return (
    <div className="doc-list-container">
      <p className="doc-list-label">Indexed Documents</p>

      {/* Server status messages */}
      {serverStatus === "checking" && (
        <div className="doc-list-status doc-list-status--loading">
          ⏳ Waking up server... (may take 60s on free tier)
        </div>
      )}

      {serverStatus === "offline" && (
        <div className="doc-list-status doc-list-status--error">
          ❌ Server offline. Please refresh and try again.
        </div>
      )}

      {serverStatus === "online" && documents.length === 0 && (
        <p className="doc-list-empty">
          No documents yet. Upload a PDF to get started.
        </p>
      )}

      {serverStatus === "online" &&
        documents.map((doc) => (
          <div
            key={doc.collection_name}
            onClick={() => onSelect(doc.collection_name)}
            className={`doc-item ${
              activeCollection === doc.collection_name ? "doc-item--active" : ""
            }`}
          >
            <span className="doc-icon">📄</span>

            <div className="doc-info">
              <p className="doc-name">{getDisplayName(doc.collection_name)}</p>
              <p className="doc-chunks">{doc.chunk_count} chunks</p>
            </div>

            <div className="doc-menu-wrapper" ref={menuRef}>
              <button
                onClick={(e) => toggleMenu(e, doc.collection_name)}
                className="doc-menu-button"
                title="Options"
              >
                ⋮
              </button>

              {menuOpen === doc.collection_name && (
                <div className="doc-dropdown">
                  <button
                    className="doc-dropdown__item"
                    onClick={(e) => handleRename(e, doc.collection_name)}
                  >
                    <span className="doc-dropdown__icon">✏️</span>
                    Rename
                  </button>

                  <button
                    className="doc-dropdown__item"
                    onClick={(e) => handleShare(e, doc.collection_name)}
                  >
                    <span className="doc-dropdown__icon">🔗</span>
                    Copy Link
                  </button>

                  <button
                    className="doc-dropdown__item"
                    onClick={(e) => handleDownload(e, doc.collection_name)}
                  >
                    <span className="doc-dropdown__icon">⬇️</span>
                    Download
                  </button>

                  <div className="doc-dropdown__divider" />

                  <button
                    className="doc-dropdown__item doc-dropdown__item--danger"
                    onClick={(e) => handleDelete(e, doc.collection_name)}
                  >
                    <span className="doc-dropdown__icon">🗑️</span>
                    Delete
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
    </div>
  );
}