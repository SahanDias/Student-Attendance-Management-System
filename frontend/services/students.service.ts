import type { Student } from "@/types/api";

import { delay, request, USE_MOCK } from "./api";
import { students as mockStudents } from "./mock-data";

export async function listStudents(): Promise<Student[]> {
  if (USE_MOCK) {
    await delay(500);
    return mockStudents;
  }
  return request<Student[]>("/students");
}

export async function getStudent(index: string): Promise<Student> {
  const studentIndex = typeof index === "string" ? index.trim() : "";
  if (!studentIndex) {
    throw new Error("Missing student index");
  }

  if (USE_MOCK) {
    await delay(400);
    const found = mockStudents.find((s) => s.index === studentIndex);
    if (!found) throw new Error(`Student ${studentIndex} not found`);
    return found;
  }
  return request<Student>(`/students/${studentIndex}`);
}
