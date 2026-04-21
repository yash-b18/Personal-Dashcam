/**
 * API client for DashcamIQ FastAPI backend.
 * All requests go through Next.js rewrites → http://localhost:8000
 */

const API_BASE = "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Types ──────────────────────────────────────────────────────────────────────

export interface ClipSummary {
  id: string;
  filename_prefix: string;
  duration_seconds: number | null;
  recorded_at: string | null;
  processing_status: string;
  score: number | null;
  grade: string | null;
  anomaly_count: number;
  front_url: string | null;
}

export interface ClipDetail extends ClipSummary {
  r2_key_front: string;
  r2_key_rear: string;
  processing_error: string | null;
  created_at: string;
  processed_at: string | null;
  rear_url: string | null;
}

export interface ClipListResponse {
  clips: ClipSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface AnomalySummary {
  id: string;
  clip_id: string;
  model_type: string;
  anomaly_type: string;
  severity: number;
  confidence: number;
  timestamp_start: number;
  timestamp_end: number;
  score_impact: number;
  ai_explanation: string | null;
  detected_at: string;
}

export interface AnomalyDetail extends AnomalySummary {
  detection_metadata: Record<string, unknown> | null;
  clip_filename: string | null;
  front_url: string | null;
  rear_url: string | null;
}

export interface AnomalyListResponse {
  anomalies: AnomalySummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface LabelQueueItem {
  id: string;
  filename_prefix: string;
  duration_seconds: number | null;
  recorded_at: string | null;
  front_url: string | null;
  rear_url: string | null;
}

export interface LabelQueueResponse {
  clips: LabelQueueItem[];
  total_unlabeled: number;
}

export interface LabelSubmit {
  is_anomaly: boolean;
  anomaly_types?: string[];
  reason?: string;
}

export interface LabelResponse {
  clip_id: string;
  is_anomaly: boolean;
  anomaly_types: string[] | null;
  reason: string | null;
  labeled_at: string;
}

export interface OverallScoreResponse {
  score: number;
  grade: string;
  clips_analyzed: number;
  breakdown: Record<string, number>;
  calculated_at: string | null;
}

export interface ClipScoreHistory {
  clip_id: string;
  filename_prefix: string;
  recorded_at: string | null;
  score: number;
  grade: string;
  anomaly_count: number;
  calculated_at: string;
}

export interface ScoreHistoryResponse {
  history: ClipScoreHistory[];
  total: number;
}

export interface AnomalyBreakdown {
  anomaly_type: string;
  count: number;
  total_score_impact: number;
}

export interface DashboardResponse {
  overall_score: number;
  grade: string;
  clips_analyzed: number;
  recent_anomaly_count: number;
  anomaly_breakdown: AnomalyBreakdown[];
  score_trend: ClipScoreHistory[];
}

export interface ProcessResponse {
  task_id: string;
  clip_id: string;
  status: string;
}

// ── Endpoints ──────────────────────────────────────────────────────────────────

export const api = {
  // Videos / Clips
  clips: {
    list: (params?: { page?: number; page_size?: number; status?: string }) => {
      const q = new URLSearchParams();
      if (params?.page)      q.set("page",      String(params.page));
      if (params?.page_size) q.set("page_size", String(params.page_size));
      if (params?.status)    q.set("status",    params.status);
      return request<ClipListResponse>(`/videos?${q}`);
    },
    get: (id: string) => request<ClipDetail>(`/videos/${id}`),
    process: (id: string) => request<ProcessResponse>(`/videos/${id}/process`, { method: "POST" }),
    processAll: () => request<{ enqueued: number; status: string }>("/videos/process-all", { method: "POST" }),
    reprocessAll: () => request<{ enqueued: number; status: string }>("/videos/reprocess-all", { method: "POST" }),
    upload: async (file: File, onProgress?: (pct: number) => void): Promise<ProcessResponse> => {
      // XMLHttpRequest lets us report upload progress; fetch does not.
      return new Promise((resolve, reject) => {
        const form = new FormData();
        form.append("file", file);
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${API_BASE}/videos/upload`);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && onProgress) onProgress((e.loaded / e.total) * 100);
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try { resolve(JSON.parse(xhr.responseText) as ProcessResponse); }
            catch (err) { reject(err); }
          } else {
            reject(new Error(`Upload ${xhr.status}: ${xhr.responseText}`));
          }
        };
        xhr.onerror = () => reject(new Error("Network error during upload"));
        xhr.send(form);
      });
    },
  },

  // Anomalies
  anomalies: {
    list: (params?: { page?: number; page_size?: number; anomaly_type?: string; min_severity?: number; clip_id?: string; model_type?: string }) => {
      const q = new URLSearchParams();
      if (params?.page)          q.set("page",          String(params.page));
      if (params?.page_size)     q.set("page_size",     String(params.page_size));
      if (params?.anomaly_type)  q.set("anomaly_type",  params.anomaly_type);
      if (params?.model_type)    q.set("model_type",    params.model_type);
      if (params?.clip_id)       q.set("clip_id",       params.clip_id);
      if (params?.min_severity != null) q.set("min_severity", String(params.min_severity));
      return request<AnomalyListResponse>(`/anomalies?${q}`);
    },
    get: (id: string) => request<AnomalyDetail>(`/anomalies/${id}`),
  },

  // Labels
  labels: {
    queue: (params?: { page?: number; page_size?: number }) => {
      const q = new URLSearchParams();
      if (params?.page)      q.set("page",      String(params.page));
      if (params?.page_size) q.set("page_size", String(params.page_size));
      return request<LabelQueueResponse>(`/labels/queue?${q}`);
    },
    get: (clipId: string) => request<LabelResponse>(`/labels/${clipId}`),
    submit: (clipId: string, data: LabelSubmit) =>
      request<LabelResponse>(`/labels/${clipId}`, { method: "POST", body: JSON.stringify(data) }),
    update: (clipId: string, data: LabelSubmit) =>
      request<LabelResponse>(`/labels/${clipId}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (clipId: string) => request<{ message: string }>(`/labels/${clipId}`, { method: "DELETE" }),
  },

  // Scores
  scores: {
    overall: () => request<OverallScoreResponse>("/scores/overall"),
    history: (params?: { page?: number; page_size?: number }) => {
      const q = new URLSearchParams();
      if (params?.page)      q.set("page",      String(params.page));
      if (params?.page_size) q.set("page_size", String(params.page_size));
      return request<ScoreHistoryResponse>(`/scores/history?${q}`);
    },
    dashboard: () => request<DashboardResponse>("/scores/dashboard"),
    recalculate: () => request<{ message: string; clips_scored: number }>("/scores/recalculate", { method: "POST" }),
  },

  // Health
  health: () => fetch("/health").then(r => r.json()),
};
