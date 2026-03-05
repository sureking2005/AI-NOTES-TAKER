// import { useState, useRef } from "react";
// import { uploadMeeting } from "../api";

// export default function UploadForm({ onUploaded }) {
//   const [title, setTitle] = useState("");
//   const [attendees, setAttendees] = useState("");
//   const [audioFile, setAudioFile] = useState(null);
//   const [glossaryFile, setGlossaryFile] = useState(null);
//   const [referenceFile, setReferenceFile] = useState(null);
//   const [recording, setRecording] = useState(false);
//   const [uploading, setUploading] = useState(false);
//   const [recordingTime, setRecordingTime] = useState(0);

//   const mediaRecorderRef = useRef(null);
//   const screenStreamRef = useRef(null);
//   const micStreamRef = useRef(null);
//   const chunksRef = useRef([]);
//   const timerRef = useRef(null);

//   const uploadAudioFile = async (file) => {
//     try {
//       if (!title.trim()) {
//         alert("Please enter a meeting title");
//         return;
//       }

//       setUploading(true);

//       const formData = new FormData();
//       formData.append("title", title);
//       formData.append("attendees", attendees);
//       formData.append("audio", file);

//       if (glossaryFile) {
//         formData.append("glossary", glossaryFile);
//       }

//       if (referenceFile) {
//         formData.append("reference", referenceFile);
//       }

//       const res = await uploadMeeting(formData);

//       setTitle("");
//       setAttendees("");
//       setAudioFile(null);
//       setGlossaryFile(null);
//       setReferenceFile(null);

//       onUploaded(res.data.meeting_id);
//     } catch (err) {
//       console.error(err);
//       alert("Upload failed. Please try again.");
//     } finally {
//       setUploading(false);
//     }
//   };

//   const startLiveRecording = async () => {
//     try {
//       if (!title.trim()) {
//         alert("Please enter a meeting title before recording.");
//         return;
//       }

//       const screenStream = await navigator.mediaDevices.getDisplayMedia({
//         video: true,
//         audio: true,
//       });

//       const micStream = await navigator.mediaDevices.getUserMedia({
//         audio: true,
//       });

//       screenStreamRef.current = screenStream;
//       micStreamRef.current = micStream;

//       const combinedStream = new MediaStream([
//         ...screenStream.getAudioTracks(),
//         ...micStream.getAudioTracks(),
//       ]);

//       const mediaRecorder = new MediaRecorder(combinedStream, {
//         mimeType: "audio/webm;codecs=opus",
//       });

//       mediaRecorderRef.current = mediaRecorder;
//       chunksRef.current = [];

//       setRecordingTime(0);
//       timerRef.current = setInterval(() => {
//         setRecordingTime((prev) => prev + 1);
//       }, 1000);

//       mediaRecorder.ondataavailable = (event) => {
//         if (event.data.size > 0) {
//           chunksRef.current.push(event.data); // ✅ correctly uses chunksRef.current
//         }
//       };

//       // ✅ FIXED: Everything is inside onstop, using correct variable names
//       mediaRecorder.onstop = async () => {
//         // ✅ Stop the timer first
//         clearInterval(timerRef.current);

//         // ✅ Use chunksRef.current (NOT undefined "chunks")
//         const blob = new Blob(chunksRef.current, { type: "audio/webm" });

//         // ✅ Validate blob is not empty before uploading
//         if (blob.size < 1000) {
//           alert("Recording was too short or empty. Please try again.");
//           setRecording(false);
//           setRecordingTime(0);
//           return;
//         }

//         // ✅ Create File from blob (blob is defined here, inside onstop)
//         const file = new File([blob], "live_meeting.webm", {
//           type: "audio/webm",
//         });

//         // ✅ Stop all tracks AFTER blob is created
//         screenStreamRef.current?.getTracks().forEach((track) => track.stop());
//         micStreamRef.current?.getTracks().forEach((track) => track.stop());

//         setRecording(false);
//         setRecordingTime(0);

//         // ✅ Call correct function name: uploadAudioFile (NOT undefined "uploadAudio")
//         await uploadAudioFile(file);
//       };

//       // ✅ Pass timeslice of 1000ms so ondataavailable fires every second
//       mediaRecorder.start(1000);
//       setRecording(true);
//     } catch (err) {
//       console.error("Recording error:", err);
//       alert("Use Chrome and allow screen + microphone permissions.");
//     }
//   };

//   const stopLiveRecording = () => {
//     clearInterval(timerRef.current); // ✅ also clear timer on manual stop
//     mediaRecorderRef.current?.stop();
//   };

//   const handleUpload = async () => {
//     if (!audioFile) {
//       alert("Please select an audio file or record a meeting");
//       return;
//     }

//     await uploadAudioFile(audioFile);
//   };

//   const formatTime = (seconds) => {
//     const mins = Math.floor(seconds / 60);
//     const secs = seconds % 60;
//     return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
//   };

//   return (
//     <div className="upload-form">
//       <div className="form-header">
//         <h2>Add Meeting</h2>
//         <p>Upload audio or record a live meeting</p>
//       </div>

//       <div className="form-group">
//         <label className="form-label">Meeting Title</label>
//         <input
//           type="text"
//           className="form-input"
//           placeholder="e.g., Project Kickoff, Q1 Planning"
//           value={title}
//           onChange={(e) => setTitle(e.target.value)}
//           disabled={uploading}
//         />
//       </div>

//       <div className="form-group">
//         <label className="form-label">Attendees</label>
//         <input
//           type="text"
//           className="form-input"
//           placeholder="Comma separated names or emails"
//           value={attendees}
//           onChange={(e) => setAttendees(e.target.value)}
//           disabled={uploading}
//         />
//       </div>

//       <div className="form-divider">
//         <span>Upload Audio</span>
//       </div>

//       <div className="form-group">
//         <label className="file-upload-label">
//           <input
//             type="file"
//             accept="audio/*"
//             onChange={(e) => setAudioFile(e.target.files[0])}
//             disabled={uploading}
//             className="file-input"
//           />
//           <span className="file-upload-text">
//             {audioFile ? (
//               <>
//                 <svg viewBox="0 0 24 24" fill="currentColor">
//                   <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
//                 </svg>
//                 {audioFile.name}
//               </>
//             ) : (
//               <>
//                 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
//                   <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
//                   <polyline points="17 8 12 3 7 8"></polyline>
//                   <line x1="12" y1="3" x2="12" y2="15"></line>
//                 </svg>
//                 Click to upload or drag and drop
//               </>
//             )}
//           </span>
//         </label>
//       </div>

//       <div className="form-divider">
//         <span>Or Record Live</span>
//       </div>

//       <div className="form-group">
//         {!recording ? (
//           <button
//             className="btn btn-record"
//             onClick={startLiveRecording}
//             disabled={uploading}
//           >
//             <svg viewBox="0 0 24 24" fill="currentColor">
//               <circle cx="12" cy="12" r="10" />
//               <circle cx="12" cy="12" r="6" fill="white" />
//             </svg>
//             Start Recording
//           </button>
//         ) : (
//           <div className="recording-state">
//             <button className="btn btn-stop" onClick={stopLiveRecording}>
//               <svg viewBox="0 0 24 24" fill="currentColor">
//                 <rect x="6" y="4" width="12" height="16" rx="1" />
//               </svg>
//               Stop Recording
//             </button>
//             <div className="recording-indicator">
//               <span className="recording-dot"></span>
//               <span className="recording-text">
//                 Recording... {formatTime(recordingTime)}
//               </span>
//             </div>
//           </div>
//         )}
//       </div>

//       <p className="help-text">
//         When prompted, select your Zoom/Meet tab and enable "Share tab audio".
//         Allow microphone permission. Works best in Chrome.
//       </p>

//       <div className="form-divider">
//         <span>Optional</span>
//       </div>

//       <div className="form-group">
//         <label className="form-label">Glossary (Optional)</label>
//         <label className="file-upload-label small">
//           <input
//             type="file"
//             accept=".json"
//             onChange={(e) => setGlossaryFile(e.target.files[0])}
//             disabled={uploading}
//             className="file-input"
//           />
//           <span className="file-upload-text">
//             {glossaryFile ? (
//               <>
//                 <svg viewBox="0 0 24 24" fill="currentColor">
//                   <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
//                 </svg>
//                 {glossaryFile.name}
//               </>
//             ) : (
//               <>
//                 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
//                   <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
//                   <polyline points="17 8 12 3 7 8"></polyline>
//                   <line x1="12" y1="3" x2="12" y2="15"></line>
//                 </svg>
//                 Upload glossary
//               </>
//             )}
//           </span>
//         </label>
//       </div>

//       <div className="form-group">
//         <label className="form-label">
//           Reference Transcript (Optional - .txt)
//         </label>
//         <label className="file-upload-label small">
//           <input
//             type="file"
//             accept=".txt"
//             onChange={(e) => setReferenceFile(e.target.files[0])}
//             disabled={uploading}
//             className="file-input"
//           />
//           <span className="file-upload-text">
//             {referenceFile ? (
//               <>
//                 <svg viewBox="0 0 24 24" fill="currentColor">
//                   <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
//                 </svg>
//                 {referenceFile.name}
//               </>
//             ) : (
//               <>
//                 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
//                   <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
//                   <polyline points="17 8 12 3 7 8"></polyline>
//                   <line x1="12" y1="3" x2="12" y2="15"></line>
//                 </svg>
//                 Upload reference transcript
//               </>
//             )}
//           </span>
//         </label>
//       </div>

//       <div className="form-actions">
//         <button
//           className="btn btn-primary"
//           onClick={handleUpload}
//           disabled={uploading || !audioFile}
//         >
//           {uploading ? (
//             <>
//               <svg
//                 className="spin"
//                 viewBox="0 0 24 24"
//                 fill="none"
//                 stroke="currentColor"
//                 strokeWidth="2"
//               >
//                 <circle cx="12" cy="12" r="10"></circle>
//                 <path d="M12 2a10 10 0 0 1 10 10"></path>
//               </svg>
//               Uploading...
//             </>
//           ) : (
//             <>
//               <svg
//                 viewBox="0 0 24 24"
//                 fill="none"
//                 stroke="currentColor"
//                 strokeWidth="2"
//               >
//                 <path d="M12 5v14M5 12h14"></path>
//               </svg>
//               Upload Meeting
//             </>
//           )}
//         </button>
//       </div>
//     </div>
//   );
// }


import { useState, useRef } from "react";
import { uploadMeeting } from "../api";

export default function UploadForm({ onUploaded }) {
  const [title, setTitle] = useState("");
  const [attendees, setAttendees] = useState("");
  const [audioFile, setAudioFile] = useState(null);
  const [glossaryFile, setGlossaryFile] = useState(null);
  const [referenceFile, setReferenceFile] = useState(null);
  const [recording, setRecording] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);

  const mediaRecorderRef = useRef(null);
  const screenStreamRef = useRef(null);
  const micStreamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);

  const uploadAudioFile = async (file) => {
    try {
      if (!title.trim()) {
        alert("Please enter a meeting title");
        return;
      }

      setUploading(true);

      const formData = new FormData();
      formData.append("title", title);
      formData.append("attendees", attendees);
      formData.append("audio", file);

      if (glossaryFile) {
        formData.append("glossary", glossaryFile);
      }

      if (referenceFile) {
        formData.append("reference", referenceFile);
      }

      const res = await uploadMeeting(formData);

      setTitle("");
      setAttendees("");
      setAudioFile(null);
      setGlossaryFile(null);
      setReferenceFile(null);

      onUploaded(res.data.meeting_id);
    } catch (err) {
      console.error(err);
      alert("Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const startLiveRecording = async () => {
    try {
      if (!title.trim()) {
        alert("Please enter a meeting title before recording.");
        return;
      }

      // ✅ FIX #1: Check browser support
      if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
        alert("Screen recording requires Chrome, Edge, or Firefox on a secure context (HTTPS or localhost).\n\nPlease use Chrome.");
        return;
      }

      console.log("📹 Requesting screen permissions...");
      const screenStream = await navigator.mediaDevices.getDisplayMedia({
        video: {
          cursor: "always",
        },
        audio: true,
      }).catch((err) => {
        console.error("❌ Screen capture denied:", err.name, err.message);
        if (err.name === "NotAllowedError") {
          throw new Error("Screen capture was denied. Please click 'Share' when prompted.");
        } else if (err.name === "NotFoundError") {
          throw new Error("No screen or window available to share.");
        }
        throw err;
      });

      console.log("✅ Screen granted, requesting microphone...");
      const micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
        },
      }).catch((err) => {
        console.error("❌ Microphone denied:", err.name, err.message);
        screenStream.getTracks().forEach((t) => t.stop()); // Clean up screen stream
        if (err.name === "NotAllowedError") {
          throw new Error("Microphone permission was denied. Please check your browser settings.");
        }
        throw err;
      });

      screenStreamRef.current = screenStream;
      micStreamRef.current = micStream;

      // ✅ FIX #2: Combine streams properly
      const combinedStream = new MediaStream([
        ...screenStream.getAudioTracks(),
        ...micStream.getAudioTracks(),
      ]);

      // ✅ FIX #3: Check codec support
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "audio/mp4";

      console.log(`🎙️ Using MIME type: ${mimeType}`);

      const mediaRecorder = new MediaRecorder(combinedStream, {
        mimeType: mimeType,
      });

      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      setRecordingTime(0);
      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        clearInterval(timerRef.current);

        const blob = new Blob(chunksRef.current, { type: mimeType });

        if (blob.size < 1000) {
          alert("Recording was too short or empty. Please try again.");
          setRecording(false);
          setRecordingTime(0);
          return;
        }

        const file = new File([blob], "live_meeting.webm", {
          type: mimeType,
        });

        screenStreamRef.current?.getTracks().forEach((track) => track.stop());
        micStreamRef.current?.getTracks().forEach((track) => track.stop());

        setRecording(false);
        setRecordingTime(0);

        await uploadAudioFile(file);
      };

      mediaRecorder.start(1000);
      setRecording(true);
      console.log("✅ Recording started");
    } catch (err) {
      console.error("❌ Recording error:", err);
      setRecording(false);
      setRecordingTime(0);
      
      // ✅ FIX #4: Show specific error messages
      if (err.message) {
        alert(err.message);
      } else {
        alert(`Recording failed: ${err.name || "Unknown error"}\n\nTroubleshooting:\n1. Use Chrome browser\n2. Allow screen + microphone permissions\n3. Make sure you're on localhost or HTTPS`);
      }
    }
  };

  const stopLiveRecording = () => {
    clearInterval(timerRef.current);
    mediaRecorderRef.current?.stop();
  };

  const handleUpload = async () => {
    if (!audioFile) {
      alert("Please select an audio file or record a meeting");
      return;
    }

    await uploadAudioFile(audioFile);
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div className="upload-form">
      <div className="form-header">
        <h2>Add Meeting</h2>
        <p>Upload audio or record a live meeting</p>
      </div>

      <div className="form-group">
        <label className="form-label">Meeting Title</label>
        <input
          type="text"
          className="form-input"
          placeholder="e.g., Project Kickoff, Q1 Planning"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={uploading}
        />
      </div>

      <div className="form-group">
        <label className="form-label">Attendees</label>
        <input
          type="text"
          className="form-input"
          placeholder="Comma separated names or emails"
          value={attendees}
          onChange={(e) => setAttendees(e.target.value)}
          disabled={uploading}
        />
      </div>

      <div className="form-divider">
        <span>Upload Audio</span>
      </div>

      <div className="form-group">
        <label className="file-upload-label">
          <input
            type="file"
            accept="audio/*"
            onChange={(e) => setAudioFile(e.target.files[0])}
            disabled={uploading}
            className="file-input"
          />
          <span className="file-upload-text">
            {audioFile ? (
              <>
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
                </svg>
                {audioFile.name}
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
                Click to upload or drag and drop
              </>
            )}
          </span>
        </label>
      </div>

      <div className="form-divider">
        <span>Or Record Live</span>
      </div>

      <div className="form-group">
        {!recording ? (
          <button
            className="btn btn-record"
            onClick={startLiveRecording}
            disabled={uploading}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <circle cx="12" cy="12" r="10" />
              <circle cx="12" cy="12" r="6" fill="white" />
            </svg>
            Start Recording
          </button>
        ) : (
          <div className="recording-state">
            <button className="btn btn-stop" onClick={stopLiveRecording}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="4" width="12" height="16" rx="1" />
              </svg>
              Stop Recording
            </button>
            <div className="recording-indicator">
              <span className="recording-dot"></span>
              <span className="recording-text">
                Recording... {formatTime(recordingTime)}
              </span>
            </div>
          </div>
        )}
      </div>

      <p className="help-text">
        When prompted, select your Zoom/Meet tab and enable "Share tab audio".
        Allow microphone permission. Works best in Chrome.
      </p>

      <div className="form-divider">
        <span>Optional</span>
      </div>

      <div className="form-group">
        <label className="form-label">Glossary (Optional)</label>
        <label className="file-upload-label small">
          <input
            type="file"
            accept=".json"
            onChange={(e) => setGlossaryFile(e.target.files[0])}
            disabled={uploading}
            className="file-input"
          />
          <span className="file-upload-text">
            {glossaryFile ? (
              <>
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
                </svg>
                {glossaryFile.name}
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
                Upload glossary
              </>
            )}
          </span>
        </label>
      </div>

      <div className="form-group">
        <label className="form-label">
          Reference Transcript (Optional - .txt)
        </label>
        <label className="file-upload-label small">
          <input
            type="file"
            accept=".txt"
            onChange={(e) => setReferenceFile(e.target.files[0])}
            disabled={uploading}
            className="file-input"
          />
          <span className="file-upload-text">
            {referenceFile ? (
              <>
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
                </svg>
                {referenceFile.name}
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
                Upload reference transcript
              </>
            )}
          </span>
        </label>
      </div>

      <div className="form-actions">
        <button
          className="btn btn-primary"
          onClick={handleUpload}
          disabled={uploading || !audioFile}
        >
          {uploading ? (
            <>
              <svg
                className="spin"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M12 2a10 10 0 0 1 10 10"></path>
              </svg>
              Uploading...
            </>
          ) : (
            <>
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M12 5v14M5 12h14"></path>
              </svg>
              Upload Meeting
            </>
          )}
        </button>
      </div>
    </div>
  );
}