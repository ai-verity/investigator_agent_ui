import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

/** Returns a user-friendly error message; never exposes raw "Http failure response for..." or technical details. */
export function getUserFriendlyErrorMessage(err: unknown, fallback: string): string {
  const msg = (err as { message?: string })?.message ?? '';
  if (!msg || msg.trim() === '') return fallback;
  if (msg.startsWith('Http failure response') || /Unknown Error|Failed to fetch|NetworkError|NS_/i.test(msg)) return fallback;
  return msg;
}

export interface StartApplicationRequest {
  application_id: string;
  date: string; // ISO string
  application_type: 'NEW' | string;
  owner_name: string;
  project_address: string;
  zoning_type: string;
}

export interface SowRequest {
  application_id: string;
  question_id: string;
  response: string;
}

export interface SowResponse {
  application_id: string;
  next_question_id: string;
  next_question: string | null;
  is_done: boolean;
  generated_sow: string | null;
}

export interface ApplicationListItem {
  application_id?: string | number;
  app_id?: string | number;
  permit_id?: string | number;
  project_address?: string;
  address?: string;
  application_type?: string;
  permit_type?: string;
  zoning_type?: string;
  zoningType?: string;
  status?: string;
  application_status?: string;
  officer_decision?: string;
  officer_comment?: string;
  officer_decided_at?: string;
  owner_name?: string;
  date?: string;
  submitted_date?: string;
  submitted_time?: string;
  sow_text?: string;
  blueprint_file_name?: string;
  site_images_count?: number;
  /** When true, AI Decision shows Critical Violation and Decision section is disabled. */
  has_critical?: boolean | number;
}

/** Response from POST /applications/{app_id} (view application). Map all fields from API. */
export interface ApplicationDetail {
  feedback?: string;
  inspector_status?: string;
  officer_decision?: string;
  application_id: string;
  date?: string;
  application_type?: string;
  owner_name?: string;
  full_name?: string;
  applicant_type?: string;
  organization?: string;
  email?: string;
  phone?: string;
  zoning_type?: string;
  project_address?: string;
  address?: string;
  land_area_sq_ft?: number | string;
  existing_built_up_area?: number | string;
  proposed_built_up_area?: number | string;
  no_of_floors?: number | string;
  sow_question_answer?: string;
  sow_text?: string;
  describe_proposed_work?: string;
  status?: string;
  submitted_date?: string;
  submitted_time?: string;
  permit_id?: string;
  signature_file_name?: string;
  blueprint_file_name?: string;
  site_images_count?: number;
}

/** SSE stream: GET /review/{app_id}/stream returns text/event-stream with "data: {json}\n" lines. */
export interface ReviewStreamFinding {
  agent: string;
  finding: string;
  severity: string;
  detail?: string;
}

export interface ReviewStreamEvent {
  event_type: 'agent_start' | 'agent_done' | 'complete';
  agent_name: string;
  agent_index: number;
  message: string;
  finding: ReviewStreamFinding | null;
  all_findings?: ReviewStreamFinding[] | null;
  compliance_score?: number | null;
}

/** Response from GET /review/{app_id}/results – findings for an application. */
export interface ReviewResultsResponse {
  findings?: ReviewStreamFinding[];
  all_findings?: ReviewStreamFinding[];
}

/** Response from GET /review/{app_id}/images – image paths for blueprint and photos. */
export interface ReviewImagesResponse {
  images?: string[];
}

@Injectable({
  providedIn: 'root',
})
export class ApplicationsApiService {
  constructor(
    private http: HttpClient,
    private auth: AuthService,
  ) {}

  startApplication(payload: StartApplicationRequest): Observable<unknown> {
    const base = environment.applicationsBaseUrl || '';
    return this.http.post(`${base}/applications/start`, payload);
  }

  sendSowMessage(payload: SowRequest): Observable<SowResponse> {
    const base = environment.applicationsBaseUrl || '';
    return this.http.post<SowResponse>(`${base}/sow/sow`, payload);
  }

  /** List applications for user dashboard */
  listApplications(): Observable<ApplicationListItem[]> {
    const base = environment.applicationsBaseUrl || '';
    return this.http.get<ApplicationListItem[]>(`${base}/applications`);
  }

  /** View application: POST /applications/{app_id} (empty body). Returns single application detail. */
  viewApplication(appid: string): Observable<ApplicationDetail> {
    const base = environment.applicationsBaseUrl || '';
    return this.http.post<ApplicationDetail>(`${base}/applications/${appid}`, {});
  }

  /**
   * Upload blueprint: POST /upload/{app_id}/blueprint with multipart/form-data field "file" only.
   * Matches API: single required "file" (binary); app_id in path.
   */
  uploadBlueprint(applicationId: string, file: File): Observable<unknown> {
    const base = environment.applicationsBaseUrl || '';
    const form = new FormData();
    form.append('file', file, file.name);
    return this.http.post(`${base}/upload/${applicationId}/blueprint`, form);
  }

  uploadPhotos(applicationId: string, files: File[]): Observable<unknown> {
    const base = environment.applicationsBaseUrl || '';
    const form = new FormData();
    form.append('application_id', applicationId);
    form.append('folder', 'photos');
    files.forEach((f) => form.append('files', f, f.name));
    return this.http.post(`${base}/upload/${applicationId}/photos`, form);
  }

  /**
   * GET /review/{app_id}/stream – Server-Sent Events (text/event-stream).
   * Each line is "data: {json}\n". Parse and emit ReviewStreamEvent. Bearer token in header.
   */
  getReviewStream(appId: string | number): Observable<ReviewStreamEvent> {
    const base = environment.reviewStreamBaseUrl || '';
    const token = this.auth.getToken() || (environment as { reviewStreamAuthToken?: string }).reviewStreamAuthToken || '';
    const url = `${base}/review/${appId}/stream`;

    return new Observable<ReviewStreamEvent>((subscriber) => {
      const headers: Record<string, string> = {
        Accept: 'text/event-stream',
      };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      fetch(url, { method: 'GET', headers })
        .then((res) => {
          if (!res.ok) {
            subscriber.error(new Error(`Review stream failed: ${res.status} ${res.statusText}`));
            return;
          }
          if (!res.body) {
            subscriber.complete();
            return;
          }
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          const read = (): void => {
            reader
              .read()
              .then(({ done, value }) => {
                if (done) {
                  processBuffer();
                  subscriber.complete();
                  return;
                }
                buffer += decoder.decode(value, { stream: true });
                processBuffer();
                read();
              })
              .catch((err) => subscriber.error(err));
          };

          function processBuffer(): void {
            const lines = buffer.split(/\r?\n/);
            buffer = lines.pop() || '';
            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed || !trimmed.startsWith('data:')) continue;
              const payload = trimmed.slice(5).trim();
              if (payload === '' || payload === '[DONE]') continue;
              try {
                subscriber.next(JSON.parse(payload) as ReviewStreamEvent);
              } catch {
                // skip malformed
              }
            }
          }

          read();
        })
        .catch((err) => subscriber.error(err));
    });
  }

  /**
   * GET /review/{app_id}/results – Get findings for an application.
   */
  getReviewResults(appId: string | number): Observable<ReviewResultsResponse> {
    const base = environment.reviewStreamBaseUrl || '';
    const token = this.auth.getToken() || (environment as { reviewStreamAuthToken?: string }).reviewStreamAuthToken || '';
    const url = `${base}/review/${appId}/results`;
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return this.http.get<ReviewResultsResponse>(url, { headers });
  }

  /**
   * GET /review/{app_id}/images – Get image paths for blueprint and photos (relative paths, e.g. uploads/.../blueprint/..., uploads/.../photos/...).
   */
  getReviewImages(appId: string | number): Observable<ReviewImagesResponse> {
    const base = environment.reviewStreamBaseUrl || '';
    const token = this.auth.getToken() || (environment as { reviewStreamAuthToken?: string }).reviewStreamAuthToken || '';
    const url = `${base}/review/${appId}/images`;
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return this.http.get<ReviewImagesResponse>(url, { headers });
  }

  /**
   * GET /applications/{app_id}/application-status – Fetch current application status (pending | submitted | completed).
   */
  getApplicationStatus(appId: string | number): Observable<string> {
    const base = environment.applicationsBaseUrl || '';
    return this.http.get<string>(`${base}/applications/${appId}/application-status`);
  }

  /**
   * PATCH /applications/{app_id}/application-status – Update application status.
   * Use when user reaches milestones: pending (after start), submitted (after step 3), completed (after step 6).
   * Optional extra fields (e.g. has_critical) are merged into the payload so backend can store AI summary flags.
   */
  updateApplicationStatus(
    appId: string | number,
    status: 'pending' | 'submitted' | 'completed',
    extra?: Record<string, unknown>,
  ): Observable<unknown> {
    const base = environment.applicationsBaseUrl || '';
    const url = `${base}/applications/${appId}/application-status`;
    const body: Record<string, unknown> = { status, ...(extra ?? {}) };
    return this.http.patch(url, body, { headers: { 'Content-Type': 'application/json' } });
  }

  /**
   * Payload should be sent in lowercase (e.g. decision, comment).
   * For submit-feedback-only flows, pass { comment: string }; decision defaults to 'feedback'.
   */
  submitInspectorFeedback(appId: string | number, body: { comment: string; decision?: string }): Observable<unknown> {
    const base = environment.applicationsBaseUrl || '';
    const url = `${base}/applications/${appId}/inspector-feedback`;
    const decision = (body.decision ?? 'feedback').toLowerCase().trim();
    const payload = {
      status: decision,
      ...(body.comment != null && body.comment !== '' ? { comment: String(body.comment).toLowerCase().trim() } : {}),
    };
    return this.http.post(url, payload, { headers: { 'Content-Type': 'application/json' } });
  }

  /**
   * POST /applications/{app_id}/inspector-status – Submit officer decision.
   * Payload: officer_decision, officer_comment, permit_id (string | null), officer_decided_at (ISO string).
   */
  submitOfficerDecision(
    appId: string | number,
    body: {
      officer_decision: string;
      officer_comment: string | null;
      permit_id: string | null;
      officer_decided_at: string;
    },
  ): Observable<unknown> {
    const base = environment.applicationsBaseUrl || '';
    const url = `${base}/applications/${appId}/inspector-status`;
    return this.http.post(url, body, { headers: { 'Content-Type': 'application/json' } });
  }

  /**
   * PATCH /applications/{app_id}/feedback – Update inspector feedback text.
   */
  updateFeedback(appId: string | number, feedback: string): Observable<unknown> {
    const base = environment.applicationsBaseUrl || '';
    const url = `${base}/applications/${appId}/feedback`;
    const payload = { feedback: String(feedback ?? '').trim().toLowerCase() };
    return this.http.patch(url, payload, { headers: { 'Content-Type': 'application/json' } });
  }
}

