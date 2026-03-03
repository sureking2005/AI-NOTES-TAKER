import { useState } from "react";
import UploadForm from "./components/UploadForm";
import MeetingView from "./components/MeetingView";
import Dashboard from "./components/Dashboard";
import "./styles/app.css";

function App() {
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [activeNav, setActiveNav] = useState("dashboard");

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="logo">
          <svg className="logo-icon" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="12" r="10" opacity="0.2" />
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
          </svg>
          <span>ScribeAI</span>
        </div>

        <nav className="sidebar-nav">
          <button
            className={`nav-item ${activeNav === "dashboard" ? "active" : ""}`}
            onClick={() => {
              setActiveNav("dashboard");
              setSelectedMeeting(null);
            }}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7"></rect>
              <rect x="14" y="3" width="7" height="7"></rect>
              <rect x="14" y="14" width="7" height="7"></rect>
              <rect x="3" y="14" width="7" height="7"></rect>
            </svg>
            <span>Dashboard</span>
          </button>
          <button className="nav-item">
            <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 3H5a2 2 0 0 0-2 2v4m0 6v4a2 2 0 0 0 2 2h4m0-14h4a2 2 0 0 1 2 2v4m0 6v4a2 2 0 0 1-2 2h-4"></path>
            </svg>
            <span>History</span>
          </button>
          <button className="nav-item">
            <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="1"></circle>
              <path d="M12 1v6m0 6v6M4.22 4.22l4.24 4.24m5.08 5.08l4.24 4.24M1 12h6m6 0h6M4.22 19.78l4.24-4.24m5.08-5.08l4.24-4.24"></path>
            </svg>
            <span>Settings</span>
          </button>
        </nav>

        {/* <div className="sidebar-footer">
          <div className="user-badge">
            <div className="user-avatar">A</div>
            <div className="user-info">
              <p className="user-name">Admin User</p>
              <p className="user-email">admin@scribeai.com</p>
            </div>
          </div>
        </div> */}
      </aside>

      {/* Main Content */}
      <main className="main-content">
        {!selectedMeeting ? (
          <>
            <header className="page-header">
              <div className="header-title">
                <h1>Your Meetings</h1>
                <p>Upload and review AI-generated meeting summaries</p>
              </div>
            </header>

            

            <div className="dashboard-grid">
              <div className="card upload-card">
                <UploadForm onUploaded={setSelectedMeeting} />
              </div>

              <div className="card meetings-card">
                <Dashboard onSelectMeeting={setSelectedMeeting} />
              </div>
            </div>
          </>
        ) : (
          <div className="card meeting-detail-card">
            <button className="back-button" onClick={() => setSelectedMeeting(null)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M15 18l-6-6 6-6"></path>
              </svg>
              <span>Back to Dashboard</span>
            </button>
            <MeetingView meetingId={selectedMeeting} />
          </div>
        )}
      </main>
    </div>
  );
}

export default App;