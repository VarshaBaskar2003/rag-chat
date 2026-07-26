import FileUpload from "./FileUpload";
import DocumentList from "./DocumentList";
import "./Sidebar.css";

export default function Sidebar({ activeCollection, onUploadSuccess, onSelectDocument }) {
  return (
    <div className="sidebar">
      <div className="sidebar__logo">🧠 RAG Chat</div>
      <FileUpload onUploadSuccess={onUploadSuccess} />
      <DocumentList
        activeCollection={activeCollection}
        onSelect={onSelectDocument}
      />
    </div>
  );
}