import { useEffect, useState } from "react";
import { getMeeting, downloadPDF, downloadDOCX } from "../api";

export default function MeetingView({ meetingId }) {
  const [meeting, setMeeting] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("summary");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState(null);

  const formatTime = (seconds) => {
    if (typeof seconds !== "number") return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  useEffect(() => {
    let intervalId  = null;
    let isMounted   = true;
    let pollCount   = 0;
    const MAX_POLLS = 150; // 150 × 2s = 5 minutes max

    const fetchMeeting = async () => {
      try {
        const res = await getMeeting(meetingId);
        if (!isMounted) return;

        setMeeting(res.data);
        setError(null);
        pollCount++;

        if (res.data.status === "ready" && res.data.transcript && res.data.mom) {
          // ✅ Data is fully ready — stop polling
          setLoading(false);
          clearInterval(intervalId);

        } else if (res.data.status === "failed") {
          // ✅ Failed — stop polling, show error
          setLoading(false);
          setError("Meeting processing failed. Please try again.");
          clearInterval(intervalId);

        } else if (pollCount >= MAX_POLLS) {
          // ✅ FIXED: Timeout after 5 minutes — don't poll forever
          setLoading(false);
          setError(
            "Processing is taking longer than expected. " +
            "Check that your Celery worker and Whisper VM are running."
          );
          clearInterval(intervalId);

        } else {
          setLoading(true);
        }
      } catch (err) {
        console.error("Failed to fetch meeting:", err);
        if (isMounted) {
          setError("Failed to load meeting: " + (err.response?.data?.detail || err.message));
          setLoading(false);
          clearInterval(intervalId);
        }
      }
    };

    fetchMeeting();
    intervalId = setInterval(fetchMeeting, 2000);

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, [meetingId]);

  const handleDownloadPDF = async () => {
    try {
      setDownloading(true);
      const response = await downloadPDF(meetingId);
      const url  = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href  = url;
      link.setAttribute("download", `${meeting.title}.pdf`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert("Failed to download PDF: " + (err.response?.data?.detail || err.message));
    } finally {
      setDownloading(false);
    }
  };

  const handleDownloadDOCX = async () => {
    try {
      setDownloading(true);
      const response = await downloadDOCX(meetingId);
      const url  = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href  = url;
      link.setAttribute("download", `${meeting.title}.docx`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert("Failed to download DOCX: " + (err.response?.data?.detail || err.message));
    } finally {
      setDownloading(false);
    }
  };

  // ── Loading state ─────────────────────────────────────────────
  if (loading && !meeting) {
    return (
      <div className="meeting-view-loading">
        <div className="loading-spinner"></div>
        <p>Processing meeting...</p>
        <p style={{ fontSize: "12px", color: "#999" }}>
          This may take a few minutes depending on audio length.
          Make sure your Whisper VM and Celery worker are running.
        </p>
      </div>
    );
  }

  // ── Error state ───────────────────────────────────────────────
  if (error && !meeting) {
    return (
      <div className="meeting-view-error">
        <p>❌ {error}</p>
      </div>
    );
  }

  if (!meeting) {
    return <div className="meeting-view-error"><p>Failed to load meeting</p></div>;
  }

  // ── Parse MoM safely ─────────────────────────────────────────
  let momData = null;
  try {
    if (meeting?.mom) {
      momData = typeof meeting.mom === "string" ? JSON.parse(meeting.mom) : meeting.mom;
    }
  } catch (err) {
    console.error("Failed to parse MoM:", err);
  }

  const correctionStats    = meeting.correction_stats || {};
  const transcriptAccuracy = meeting.transcript_accuracy ?? null;
  const evaluationScore    = meeting.evaluation_score    ?? null;

  return (
    <div className="meeting-view">

      {/* HEADER */}
      <div className="meeting-view-header">
        <div className="meeting-view-title">
          <h1>{meeting.title}</h1>
          <span className={`status-badge status-${meeting.status}`}>
            {meeting.status === "ready"      ? "✓ Ready"
           : meeting.status === "processing" ? "⏳ Processing"
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

      {/* METRICS */}
      {meeting.status === "ready" && (
        <div className="meeting-metrics">
          <div className="metric-card">
            <h4>Transcript Accuracy</h4>
            <p>{transcriptAccuracy !== null ? `${(transcriptAccuracy * 100).toFixed(1)}%` : "N/A"}</p>
          </div>
          <div className="metric-card">
            <h4>MoM Quality Score</h4>
            <p>{evaluationScore !== null ? `${(evaluationScore * 100).toFixed(1)}%` : "N/A"}</p>
          </div>
          <div className="metric-card">
            <h4>Correction Rate</h4>
            <p>
              {correctionStats.correction_rate !== undefined
                ? `${(correctionStats.correction_rate * 100).toFixed(1)}%`
                : "N/A"}
            </p>
          </div>
          <div className="metric-card">
            <h4>Terms Corrected</h4>
            <p>{correctionStats.total_corrected || 0}</p>
          </div>
        </div>
      )}

      {/* METADATA */}
      <div className="meeting-view-metadata">
        <div className="metadata-item">
          <span>
            {meeting.created_at
              ? new Date(meeting.created_at).toLocaleDateString("en-US", {
                  weekday: "long", month: "long", day: "numeric", year: "numeric"
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

      {/* TABS */}
      <div className="meeting-tabs">
        {["summary", "mom", "transcript"].map((tab) => (
          <button
            key={tab}
            className={`tab-button ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === "summary" ? "Summary" : tab === "mom" ? "Minutes of Meeting" : "Transcript"}
          </button>
        ))}
      </div>

      {/* SUMMARY TAB */}
      {activeTab === "summary" && (
        <div className="meeting-summary">
          {momData?.["Summary by Topics"]?.length > 0 ? (
            <ul className="summary-list">
              {momData["Summary by Topics"].map((item, i) => <li key={i}>{item}</li>)}
            </ul>
          ) : (
            <p className="empty-section">No summary available</p>
          )}
        </div>
      )}

      {/* MOM TAB */}
      {activeTab === "mom" && (
        <div className="meeting-summary">
          {momData?.["Decisions"]?.length > 0 && (
            <div className="summary-section">
              <h3>Key Decisions</h3>
              <ul className="summary-list">
                {momData["Decisions"].map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </div>
          )}

          {momData?.["Risks"]?.length > 0 && (
            <div className="summary-section">
              <h3>Risks</h3>
              <ul className="summary-list">
                {momData["Risks"].map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </div>
          )}

          {momData?.["Action Items"]?.length > 0 && (
            <div className="summary-section">
              <h3>Action Items</h3>
              {momData["Action Items"].map((item, i) => (
                <div key={i} className="action-item-card">
                  <div className="action-item-title">{item.task}</div>
                  <div className="action-item-meta">
                    {item.owner && item.owner !== "Unassigned" && <span>👤 {item.owner}</span>}
                    {item.due_date && item.due_date !== "Not specified" && <span>📅 {item.due_date}</span>}
                    {item.priority && <span>🎯 {item.priority}</span>}
                    {item.confidence_score && <span>✓ {item.confidence_score}%</span>}
                  </div>
                </div>
              ))}
            </div>
          )}

          {momData?.["Open Questions"]?.length > 0 && (
            <div className="summary-section">
              <h3>Open Questions</h3>
              <ul className="summary-list">
                {momData["Open Questions"].map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </div>
          )}

          {!momData && <p className="empty-section">Minutes of Meeting not available yet</p>}
        </div>
      )}

      {/* TRANSCRIPT TAB */}
      {activeTab === "transcript" && (
        <div className="meeting-transcript">
          {meeting.transcript?.length > 0 ? (
            meeting.transcript.map((segment, i) => (
              <div key={i} className="transcript-segment">
                <div className="segment-header">
                  <span className="segment-speaker">{segment.speaker}</span>
                  <span className="segment-time">{formatTime(segment.start)}</span>
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