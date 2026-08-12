import type { AttendanceSummary, StudentAttendanceSummary } from "@/types/api";

import { delay, request, USE_MOCK } from "./api";
import {
  attendanceRateSeries,
  resultsFor,
  sessions as mockSessions,
  students as mockStudents,
  summaryFor,
} from "./mock-data";

export async function getAttendanceSummary(index: string): Promise<AttendanceSummary> {
  const studentIndex = typeof index === "string" ? index.trim() : "";
  if (!studentIndex) {
    throw new Error("Missing student index");
  }

  if (USE_MOCK) {
    await delay(520);
    return summaryFor(studentIndex);
  }
  return request<AttendanceSummary>(`/attendance/${studentIndex}/summary`);
}

export async function getStudentSignatures(index: string): Promise<
  {
    session_id: string;
    session_date: string;
    subject_code: string;
    cell_image: string;
    present: boolean;
  }[]
> {
  const studentIndex = typeof index === "string" ? index.trim() : "";
  if (!studentIndex) {
    throw new Error("Missing student index");
  }

  if (USE_MOCK) {
    await delay(500);
    return mockSessions.map((s) => {
      const row = resultsFor(s.session_id).find((r) => r.student_index === studentIndex);
      return {
        session_id: s.session_id,
        session_date: s.session_date,
        subject_code: s.subject_code,
        cell_image: row?.cell_image ?? "",
        present: row?.present ?? false,
      };
    });
  }
  return request(`/attendance/${studentIndex}`);
}

export async function getAttendanceTrend(): Promise<
  { date: string; subject_code: string; rate: number }[]
> {
  if (USE_MOCK) {
    await delay(480);
    return attendanceRateSeries();
  }
  return request<{ date: string; subject_code: string; rate: number }[]>("/attendance/trend");
}

export async function getAttendanceSummaries(): Promise<StudentAttendanceSummary[]> {
  if (USE_MOCK) {
    await delay(480);
    return mockStudents.map((s) => ({
      index: s.index,
      name: s.name,
      sessions_attended: s.sessions_attended,
      sessions_total: s.sessions_total,
      percentage: s.attendance_percentage,
    }));
  }
  return request<StudentAttendanceSummary[]>("/attendance/summary");
}
