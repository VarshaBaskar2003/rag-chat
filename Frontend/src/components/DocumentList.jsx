import { useEffect, useState, useRef } from "react";
import { getDocuments, deleteDocument } from "../api/ragApi";
import "./DocumentList.css";

export default function DocumentList({ activeCollection, onSelect }) {
  const [documents, setDocuments] = useState([]);
  const [menuOpen, setMenuOpen] = useState(null);
  const menuRef = useRef(null);

  useEffect(() => {
    fetchDocuments();
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [activeCollection]);

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
      const response = await fetch(`http://localhost:8000/files/list`);
      const files = await response.json();

      console.log("Available files:", files);
      console.log("Looking for collection:", collectionName);

      const match = files.find((f) => {
        const converted = f
          .toLowerCase()
          .replace(/\s+/g, "_")
          .replace(/\./g, "_")
          .replace(/-/g, "_");
        console.log(`${f} → ${converted}`);
        return converted === collectionName;
      });

      if (match) {
        window.open(`http://localhost:8000/uploads/${match}`, "_blank");
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
      {documents.length === 0 && (
        <p className="doc-list-empty">
          No documents yet. Upload a PDF to get started.
        </p>
      )}
      {documents.map((doc) => (
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