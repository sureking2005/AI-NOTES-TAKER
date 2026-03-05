import { useState, useEffect } from "react";
import { getMeetings } from "../api";

export default function Dashboard({ onSelectMeeting }) {
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // ================================
  // FETCH MEETINGS (with proper polling)
  // ================================
  useEffect(() => {
    let intervalId = null;
    let isMounted = true;

    const fetchMeetings = async () => {
      try {
        const res = await getMeetings();
        if (isMounted) {
          setMeetings(res.data || []);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        console.error("Failed to fetch meetings:", err);
        if (isMounted) {
          setError("Failed to load meetings");
          setMeetings([]);
          setLoading(false);
        }
      }
    };

    // ✅ FIX #1: Fetch immediately first time
    fetchMeetings();

    // ✅ FIX #2: Set up polling interval - declare outside function
    intervalId = setInterval(() => {
      fetchMeetings();
    }, 4000); // refresh every 4 seconds

    // ✅ FIX #3: Proper cleanup on unmount
    return () => {
      isMounted = false;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, []);

  // ================================
  // DYNAMIC STATS (REAL DATA)
  // ================================
  const total = meetings.length;
  const completed = meetings.filter(m => m.status === "ready").length;
  const processing = meetings.filter(m => m.status === "processing").length;

  const getStatusColor = (status) => {
    switch (status) {
      case "ready":
        return "status-ready";
      case "processing":
        return "status-processing";
      case "failed":
        return "status-failed";
      default:
        return "status-default";
    }
  };

  const getStatusLabel = (status) => {
    switch (status) {
      case "ready":
        return "✓ Ready";
      case "processing":
        return "⏳ Processing";
      case "failed":
        return "❌ Failed";
      default:
        return status;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return "";
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  // ================================
  // LOADING STATE
  // ================================
  if (loading && meetings.length === 0) {
    return (
      <div className="dashboard">
        <div className="loading-state">
          <p>Loading meetings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard">

      {/* ================================
          STATS SECTION (REAL DATA)
      ================================= */}
      <div className="stats-container">
        <div className="stat-card">
          <h3>Total Meetings</h3>
          <p className="stat-value">{total}</p>
        </div>

        <div className="stat-card">
          <h3>Completed</h3>
          <p className="stat-value">{completed}</p>
        </div>

        <div className="stat-card">
          <h3>Processing</h3>
          <p className="stat-value">{processing}</p>
        </div>
      </div>

      {/* ================================
          HEADER
      ================================= */}
      <div className="dashboard-header">
        <h2>Recent Meetings</h2>
        <p className="dashboard-subtitle">
          {total} meeting{total !== 1 ? "s" : ""}
          {processing > 0 && ` (${processing} processing)`}
        </p>
      </div>

      {/* ================================
          ERROR
      ================================= */}
      {error && (
        <div className="error-message">
          ❌ {error}
        </div>
      )}

      {/* ================================
          EMPTY STATE
      ================================= */}
      {meetings.length === 0 ? (
        <div className="empty-state">
          <p>No meetings yet</p>
          <p className="empty-state-hint">
            Upload your first meeting to get started
          </p>
        </div>
      ) : (
        <div className="meetings-list">
          {meetings.map((meeting) => (
            <div
              key={meeting.id}
              className="meeting-card"
              onClick={() => onSelectMeeting(meeting.id)}
              style={{ cursor: "pointer" }}
            >
              <div className="meeting-card-header">
                <h3 className="meeting-title">{meeting.title}</h3>
                <span className={`status-badge ${getStatusColor(meeting.status)}`}>
                  {getStatusLabel(meeting.status)}
                </span>
              </div>

              <div className="meeting-card-meta">
                <span>{formatDate(meeting.created_at)}</span>

                {meeting.attendees && (
                  <span className="attendees">
                    👥 {meeting.attendees}
                  </span>
                )}
              </div>

              {meeting.duration && (
                <div className="meeting-duration">
                  ⏱️ {Math.round(meeting.duration / 60)} min
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}