// Real API values are "uploaded" | "processing" | "processed" | "failed" (see
// backend app/models/schemas.py Session.status). "queued" / "completed" /
// "needs_review" are mock-data-only values from services/mock-data.ts.
// StatusBadge must still degrade gracefully for anything outside this union,
// since the type isn't enforced at runtime.
export type SessionStatus =
  "uploaded" | "queued" | "processing" | "processed" | "completed" | "needs_review" | "failed";

export interface SessionSummary {
  session_id: string;
  subject_code: string;
  session_date: string;
  students_detected: number;
  present_count: number;
  absent_count: number;
  flagged_count: number;
  status: SessionStatus;
  header_rows: number;
  signature_col: number;
  processed_at: string;
  /**
   * Storage-relative path to the operator's originally uploaded photograph
   * (see backend app/api/routes/sheets.py, where the session document's
   * "image_path" is set on upload). GET /sheets does not currently include
   * this field in its response, so it comes through empty until the
   * backend adds it -- render via staticUrl() and fall back to a
   * broken-image state rather than a placeholder when it's missing.
   */
  image_path: string;
}

/** GET /sheets/{id}/steps */
export interface ProcessingStep {
  name: string;
  order: number;
  path: string;
}

/** GET /sheets/{id}/results */
export interface SheetResult {
  row: number;
  student_index: string;
  name?: string | undefined;
  present: boolean;
  ink_ratio: number;
  confidence: number;
  cell_image: string;
}

/** GET /students */
export interface Student {
  index: string;
  name: string;
  batch: string;
  sessions_attended: number;
  sessions_total: number;
  attendance_percentage: number;
}

/**
 * GET /attendance/summary -- one entry per enrolled student, aggregated
 * across "processed" sessions only. sessions_total is the same value for
 * every student (the total count of processed sessions), not a per-student
 * record count.
 */
export interface StudentAttendanceSummary {
  index: string;
  name: string;
  sessions_attended: number;
  sessions_total: number;
  percentage: number;
}

/** GET /attendance/{index}/summary */
export interface AttendanceSummary {
  student_index: string;
  present: number;
  absent: number;
  percentage: number;
  series: {
    date: string;
    present: boolean;
    subject_code: string;
    session_id: string;
  }[];
}

/**
 * GET /signatures/sessions -- one entry per processed session, newest
 * first. `lecturer_name`/`batch` come back null until the backend session
 * document actually stores them (see app/api/routes/signatures.py).
 * `item_count` is how many comparison cards GET /signatures/sessions/{id}
 * will return for this session -- students present in it who also have an
 * earlier present session to compare against.
 */
export interface SignatureSessionSummary {
  session_id: string;
  session_date: string | null;
  subject_code: string | null;
  lecturer_name: string | null;
  batch: string | null;
  original_filename: string | null;
  item_count: number;
}

/**
 * GET /signatures/sessions/{session_id} — raw backend shape. Unlike the
 * flat `GET /signatures` queue (whose reference is a student's all-time
 * earliest session), each item here compares a student's crop in this
 * session against their crop from `previous_session_date`, the most recent
 * earlier session they were present for.
 */
export interface SignatureSessionApiItem {
  id: string;
  student_id: string;
  student_name: string;
  session_id: string;
  session_date: string | null;
  subject_code: string | null;
  previous_session_date: string | null;
  reference_signature: string;
  detected_signature: string;
  confidence_score: number;
  similarity_score: number;
  match_method: string;
  review_required: boolean;
}

/** UI-facing shape for one comparison card within a session. */
export interface SignatureSessionItem {
  id: string;
  student_index: string;
  name: string;
  session_id: string;
  session_date: string | null;
  subject_code: string | null;
  previous_session_date: string | null;
  similarity: number;
  match_method: string;
  flagged: boolean;
  reference_image: string;
  current_image: string;
}

/** POST /signatures/{student_index}/review request body. */
export interface SignatureReviewDecisionRequest {
  session_id: string;
  decision: "confirmed" | "flagged";
  note?: string | undefined;
}

/**
 * Shape returned by both POST /signatures/{student_index}/review and
 * GET /signatures/reviews -- one persisted operator decision per
 * (student_index, session_id) pair (see backend app/api/routes/signatures.py,
 * upserted into the signature_reviews collection).
 */
export interface SignatureReviewRecord {
  student_index: string;
  session_id: string;
  decision: "confirmed" | "flagged";
  note: string | null;
  reviewed_at: string;
}

/**
 * WS /sheets/ws/{id}. Per-step events ("running"/"done"/"failed") always
 * carry step/order/total/path. The terminal "complete" event is a distinct
 * shape sent only after attendance records are written and the session
 * status is persisted -- it carries session_id/record_count instead, never
 * step/order/total/path. onDone must key off status === "complete", not off
 * a per-step event reaching order === total.
 */
export interface ProcessingEvent {
  step?: string;
  order?: number;
  total?: number;
  path?: string;
  status: "running" | "done" | "failed" | "complete";
  message?: string | undefined;
  session_id?: string;
  record_count?: number;
}

export interface UploadResponse {
  session_id: string;
}

/**
 * POST /sheets/{id}/process request body. Every field beyond header_rows/
 * signature_col is optional on the backend (see ProcessOptions in
 * app/api/routes/sheets.py) -- omitted ones fall through to that service's
 * own constructor default. The upload/reprocess forms always send the full
 * set via lib/processing-settings.ts's toProcessOptionsPayload().
 */
export interface ProcessOptions {
  header_rows: number;
  signature_col: number;
  resize_width?: number;
  adaptive_block_size?: number;
  adaptive_constant?: number;
  deskew_search_range_degrees?: number;
  horizontal_threshold_fraction?: number;
  vertical_threshold_fraction?: number;
  horizontal_kernel_scale?: number;
  vertical_kernel_scale?: number;
  min_cols?: number;
  signature_horizontal_shrink?: number;
  signature_vertical_shrink?: number;
  signature_vertical_expansion?: number;
  presence_horizontal_shrink?: number;
  presence_vertical_shrink?: number;
  min_ink_ratio?: number;
  min_component_area?: number;
  similarity_threshold?: number;
  orb_nfeatures?: number;
  min_keypoints?: number;
}
