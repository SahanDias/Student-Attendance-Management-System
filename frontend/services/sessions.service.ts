import { PIPELINE_STAGES } from "@/lib/pipeline-stages";
import type {
  ProcessOptions,
  ProcessingEvent,
  ProcessingStep,
  SessionSummary,
  SheetResult,
  UploadResponse,
} from "@/types/api";

function mapSessionSummary(raw: Record<string, unknown>): SessionSummary {
  return {
    session_id: String(raw["session_id"] ?? raw["id"] ?? ""),
    subject_code: String(raw["subject_code"] ?? ""),
    session_date: String(raw["session_date"] ?? raw["date"] ?? ""),
    students_detected: Number(raw["students_detected"] ?? 0),
    present_count: Number(raw["present_count"] ?? 0),
    absent_count: Number(raw["absent_count"] ?? 0),
    flagged_count: Number(raw["flagged_count"] ?? 0),
    status: (raw["status"] as SessionSummary["status"]) ?? "uploaded",
    header_rows: Number(raw["header_rows"] ?? 1),
    signature_col: Number(raw["signature_col"] ?? -1),
    processed_at: String(raw["processed_at"] ?? raw["uploaded_at"] ?? raw["date"] ?? ""),
    // GET /sheets doesn't send this field today (see the image_path doc
    // comment on SessionSummary) -- String(undefined ?? "") resolves to ""
    // either way, which staticUrl() and the broken-image fallback treat as
    // "no path", not as a reason to guess a different field name.
    image_path: String(raw["image_path"] ?? ""),
  };
}

export async function getSession(id: string): Promise<SessionSummary> {
  if (USE_MOCK) {
    await delay(400);
    const found = mockSessions.find((s) => s.session_id === id);
    if (!found) throw new Error(`Session ${id} not found`);
    return found;
  }
  const raw = await request<Record<string, unknown>>(`/sheets/${id}`);
  return mapSessionSummary(raw);
}

export async function getSteps(id: string): Promise<ProcessingStep[]> {
  if (USE_MOCK) {
    await delay(450);
    return stepsFor(id);
  }
  return request<ProcessingStep[]>(`/sheets/${id}/steps`);
}

export async function getResults(id: string): Promise<SheetResult[]> {
  if (USE_MOCK) {
    await delay(600);
    return resultsFor(id);
  }
  return request<SheetResult[]>(`/sheets/${id}/results`);
}

export async function uploadSheet(
  image: File,
  infoXml: File,
  subjectCode: string,
  sessionDate: string,
): Promise<UploadResponse> {
  if (USE_MOCK) {
    await delay(900);
    return { session_id: `sess_upload_${Date.now()}` };
  }
  const form = new FormData();
  form.append("image", image);
  form.append("info_xml", infoXml);
  form.append("subject_code", subjectCode);
  form.append("session_date", sessionDate);
  return request<UploadResponse>("/sheets/upload", { method: "POST", body: form });
}

export async function startProcessing(id: string, opts: ProcessOptions): Promise<{ ok: boolean }> {
  if (USE_MOCK) {
    await delay(300);
    return { ok: true };
  }
  return request<{ ok: boolean }>(`/sheets/${id}/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
}

export function subscribeProcessing(
  id: string,
  handlers: {
    onEvent: (event: ProcessingEvent) => void;
    onDone?: () => void;
    onError?: (message: string) => void;
    failAtStep?: number | undefined;
  },
): () => void {
  if (USE_MOCK) {
    let cancelled = false;
    const total = PIPELINE_STAGES.length;
    (async () => {
      for (let i = 0; i < total; i++) {
        const stage = PIPELINE_STAGES[i]!;
        if (cancelled) return;
        handlers.onEvent({ step: stage.name, order: i + 1, total, path: "", status: "running" });
        await delay(720 + i * 90);
        if (cancelled) return;
        if (handlers.failAtStep && i + 1 === handlers.failAtStep) {
          handlers.onEvent({
            step: stage.name,
            order: i + 1,
            total,
            path: "",
            status: "failed",
            message: `cv2.error: (-215:Assertion failed) !ssize.empty() in function 'resize' — grid detection returned 0 horizontal rules for stage "${stage.name}"`,
          });
          handlers.onError?.(
            `Processing failed at "${stage.name}": the backend could not detect a table grid. Try increasing header rows or re-photographing the sheet with less skew.`,
          );
          return;
        }
        handlers.onEvent({
          step: stage.name,
          order: i + 1,
          total,
          path: `${id}/steps/${String(i + 1).padStart(2, "0")}_${stage.name.toLowerCase().replace(/ /g, "_")}.png`,
          status: "done",
        });
      }
      if (!cancelled) {
        // Mirrors the real backend: a distinct terminal event after the
        // stage stream, not inferred from the last stage's own event.
        handlers.onEvent({
          status: "complete",
          session_id: id,
          record_count: resultsFor(id).length,
        });
        handlers.onDone?.();
      }
    })();
    return () => {
      cancelled = true;
    };
  }