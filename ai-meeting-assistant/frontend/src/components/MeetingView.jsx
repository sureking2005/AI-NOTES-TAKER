import { useEffect, useState } from "react";
import { getMeeting, downloadPDF, downloadDOCX } from "../api";

export default function MeetingView({ meetingId }) {
  const [meeting, setMeeting] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("summary");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState(null);

  // Format seconds → mm:ss
  const formatTime = (seconds) => {
    if (typeof seconds !== "number") return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  useEffect(() => {
    // ✅ FIX #1: Declare interval OUTSIDE fetchMeeting so it can be referenced
    let intervalId = null;
    let isMounted = true;

    const fetchMeeting = async () => {
      try {
        const res = await getMeeting(meetingId);
        
        if (!isMounted) return; // Prevent state updates after unmount

        setMeeting(res.data);
        setError(null);

        // ✅ FIX #2: Only stop polling once we KNOW data is ready
        // Check if status is ready AND we have actual data
        if (res.data.status === "ready" && res.data.transcript && res.data.mom) {
          setLoading(false);
          // Once ready and data is present, clear the interval
          if (intervalId) {
            clearInterval(intervalId);
          }
        } else if (res.data.status === "ready") {
          // Status ready but data not fully loaded yet - keep polling
          setLoading(true);
        } else if (res.data.status === "processing") {
          setLoading(true);
        } else if (res.data.status === "failed") {
          setLoading(false);
          setError("Meeting processing failed. Please try again.");
        }
      } catch (err) {
        console.error("Failed to fetch meeting:", err);
        if (isMounted) {
          setError("Failed to load meeting: " + (err.response?.data?.detail || err.message));
          setLoading(false);
        }
      }
    };

    // ✅ FIX #3: Fetch immediately first time
    fetchMeeting();

    // ✅ FIX #4: Then set up polling interval
    // Keep polling every 2 seconds until data is ready
    intervalId = setInterval(fetchMeeting, 2000);

    // ✅ FIX #5: Proper cleanup on unmount
    return () => {
      isMounted = false;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [meetingId]);

  const handleDownloadPDF = async () => {
    try {
      setDownloading(true);
      const response = await downloadPDF(meetingId);
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `${meeting.title}.pdf`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download failed:", err);
      alert("Failed to download PDF: " + (err.response?.data?.detail || err.message));
    } finally {
      setDownloading(false);
    }
  };

  const handleDownloadDOCX = async () => {
    try {
      setDownloading(true);
      const response = await downloadDOCX(meetingId);
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `${meeting.title}.docx`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download failed:", err);
      alert("Failed to download DOCX: " + (err.response?.data?.detail || err.message));
    } finally {
      setDownloading(false);
    }
  };

  // ✅ FIX #6: Show loading state with actual message
  if (loading && !meeting) {
    return (
      <div className="meeting-view-loading">
        <div className="loading-spinner"></div>
        <p>Processing meeting...</p>
        <p style={{ fontSize: "12px", color: "#999" }}>
          This may take a few minutes depending on audio length
        </p>
      </div>
    );
  }

  // ✅ FIX #7: Show error if it exists
  if (error && !meeting) {
    return (
      <div className="meeting-view-error">
        <p>❌ {error}</p>
      </div>
    );
  }

  if (!meeting) {
    return (
      <div className="meeting-view-error">
        <p>Failed to load meeting</p>
      </div>
    );
  }

  // ✅ FIX #8: Better JSON parsing with error logging
  let momData = null;
  try {
    if (meeting?.mom) {
      if (typeof meeting.mom === "string") {
        momData = JSON.parse(meeting.mom);
      } else {
        momData = meeting.mom;
      }
    }
  } catch (err) {
    console.error("Failed to parse MoM data:", err, "Raw data:", meeting.mom);
    momData = null;
  }

  // ✅ FIX #9: Safe access to correction_stats
  const correctionStats = meeting.correction_stats || {};
  const transcriptAccuracy = meeting.transcript_accuracy !== null && meeting.transcript_accuracy !== undefined
    ? meeting.transcript_accuracy
    : null;
  const evaluationScore = meeting.evaluation_score !== null && meeting.evaluation_score !== undefined
    ? meeting.evaluation_score
    : null;

  return (
    <div className="meeting-view">
      {/* ================= HEADER ================= */}
      <div className="meeting-view-header">
        <div className="meeting-view-title">
          <h1>{meeting.title}</h1>
          <span className={`status-badge status-${meeting.status}`}>
            {meeting.status === "ready"
              ? "✓ Ready"
              : meeting.status === "processing"
              ? "⏳ Processing"
              : "❌ Failed"}
          </span>
        </div>

        <div className="meeting-view-actions">
          <button
            className="btn btn-secondary"
            onClick={handleDownloadPDF}
            disabled={downloading || meeting.status !== "ready"}
          >
            {downloading ? "Downloading..." : "PDF"}
          </button>

          <button
            className="btn btn-secondary"
            onClick={handleDownloadDOCX}
            disabled={downloading || meeting.status !== "ready"}
          >
            {downloading ? "Downloading..." : "DOCX"}
          </button>
        </div>
      </div>

      {/* ================= METADATA ================= */}
      <div className="meeting-view-metadata">
        {/* ================= EVALUATION METRICS ================= */}
        {meeting.status === "ready" && (
          <div className="meeting-metrics">
            <div className="metric-card">
              <h4>Transcript Accuracy</h4>
              <p>
                {transcriptAccuracy !== null
                  ? `${(transcriptAccuracy * 100).toFixed(1)}%`
                  : "N/A (no reference provided)"}
              </p>
            </div>

            <div className="metric-card">
              <h4>MoM Quality Score</h4>
              <p>
                {evaluationScore !== null
                  ? `${(evaluationScore * 100).toFixed(1)}%`
                  : "N/A"}
              </p>
            </div>

            <div className="metric-card">
              <h4>Correction Success Rate</h4>
              <p>
                {correctionStats.correction_rate !== undefined
                  ? `${(correctionStats.correction_rate * 100).toFixed(1)}%`
                  : "N/A"}
              </p>
            </div>

            <div className="metric-card">
              <h4>Total Terms Corrected</h4>
              <p>{correctionStats.total_corrected || 0}</p>
            </div>
          </div>
        )}

        <div className="metadata-item">
          <span>
            {meeting.created_at
              ? new Date(meeting.created_at).toLocaleDateString("en-US", {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                })
              : "Date not available"}
          </span>
        </div>

        {meeting.duration > 0 && (
          <div className="metadata-item">
            <span>{Math.round(meeting.duration / 60)} minutes</span>
          </div>
        )}
      </div>

      {/* ================= TABS ================= */}
      <div className="meeting-tabs">
        <button
          className={`tab-button ${activeTab === "summary" ? "active" : ""}`}
          onClick={() => setActiveTab("summary")}
        >
          Summary
        </button>

        <button
          className={`tab-button ${activeTab === "mom" ? "active" : ""}`}
          onClick={() => setActiveTab("mom")}
        >
          Minutes of Meeting
        </button>

        <button
          className={`tab-button ${activeTab === "transcript" ? "active" : ""}`}
          onClick={() => setActiveTab("transcript")}
        >
          Transcript
        </button>
      </div>

      {/* ================= SUMMARY TAB ================= */}
      {activeTab === "summary" && (
        <div className="meeting-summary">
          {momData?.["Summary by Topics"] && momData["Summary by Topics"].length > 0 ? (
            <ul className="summary-list">
              {momData["Summary by Topics"].map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="empty-section">No summary available</p>
          )}
        </div>
      )}

      {/* ================= MINUTES OF MEETING TAB ================= */}
      {activeTab === "mom" && (
        <div className="meeting-summary">
          {momData?.["Decisions"] && momData["Decisions"].length > 0 && (
            <div className="summary-section">
              <h3>Key Decisions</h3>
              <ul className="summary-list">
                {momData["Decisions"].map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {momData?.["Risks"] && momData["Risks"].length > 0 && (
            <div className="summary-section">
              <h3>Risks</h3>
              <ul className="summary-list">
                {momData["Risks"].map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {momData?.["Action Items"] && momData["Action Items"].length > 0 && (
            <div className="summary-section">
              <h3>Action Items</h3>
              {momData["Action Items"].map((item, i) => (
                <div key={i} className="action-item-card">
                  <div className="action-item-title">{item.task}</div>
                  <div className="action-item-meta">
                    {item.owner && item.owner !== "Unassigned" && (
                      <span>👤 Owner: {item.owner}</span>
                    )}
                    {item.due_date && item.due_date !== "Not specified" && (
                      <span>📅 Due: {item.due_date}</span>
                    )}
                    {item.priority && <span>🎯 Priority: {item.priority}</span>}
                    {item.confidence_score && (
                      <span>✓ Confidence: {item.confidence_score}%</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {momData?.["Open Questions"] && momData["Open Questions"].length > 0 && (
            <div className="summary-section">
              <h3>Open Questions</h3>
              <ul className="summary-list">
                {momData["Open Questions"].map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {(!momData ||
            (!momData["Decisions"] &&
              !momData["Risks"] &&
              !momData["Action Items"] &&
              !momData["Open Questions"])) && (
            <p className="empty-section">Minutes of Meeting not available yet</p>
          )}
        </div>
      )}

      {/* ================= TRANSCRIPT TAB ================= */}
      {activeTab === "transcript" && (
        <div className="meeting-transcript">
          {meeting.transcript && meeting.transcript.length > 0 ? (
            meeting.transcript.map((segment, i) => (
              <div key={i} className="transcript-segment">
                <div className="segment-header">
                  <span className="segment-speaker">{segment.speaker}</span>
                  <span className="segment-time">
                    {formatTime(segment.start)}
                  </span>
                </div>
                <p className="segment-text">{segment.text}</p>
              </div>
            ))
          ) : (
            <p className="empty-section">Transcript not available yet</p>
          )}
        </div>
      )}
    </div>
  );
}