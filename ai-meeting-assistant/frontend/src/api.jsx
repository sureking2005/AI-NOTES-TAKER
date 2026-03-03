import axios from "axios";

const API = axios.create({
  baseURL: "http://127.0.0.1:8000",
  headers: {
    "Content-Type": "application/json",
  },
});

// Handle API errors
API.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("API Error:", error.response?.data || error.message);
    return Promise.reject(error);
  }
);

// ========================================
// MEETING ENDPOINTS
// ========================================

// Upload a new meeting
export const uploadMeeting = (formData) => {
  return API.post("/meetings/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
};

// Get all meetings (Dashboard)
export const getMeetings = () => {
  return API.get("/meetings/");
};

// Get a specific meeting with full details
export const getMeeting = (id) => {
  return API.get(`/meetings/${id}`);
};

// Download meeting as PDF
export const downloadPDF = (id) => {
  return API.get(`/meetings/${id}/pdf`, {
    responseType: "blob",
  });
};

// Download meeting as DOCX
export const downloadDOCX = (id) => {
  return API.get(`/meetings/${id}/docx`, {
    responseType: "blob",
  });
};

// ========================================
// OPTIONAL: Additional endpoints
// ========================================

// Delete a meeting
export const deleteMeeting = (id) => {
  return API.delete(`/meetings/${id}`);
};

// Update meeting metadata
export const updateMeeting = (id, data) => {
  return API.patch(`/meetings/${id}`, data);
};

// Get meeting transcript
export const getTranscript = (id) => {
  return API.get(`/meetings/${id}/transcript`);
};

// Get meeting summary/MoM
export const getSummary = (id) => {
  return API.get(`/meetings/${id}/summary`);
};

export default API;