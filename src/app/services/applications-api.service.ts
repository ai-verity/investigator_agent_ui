import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

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
}

/** Response from POST /applications/{app_id} (view application). Map all fields from API. */
export interface ApplicationDetail {
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
  event_type: 'agent_start' | 'agent_done';
  agent_name: string;
  agent_index: number;
  message: string;
  finding: ReviewStreamFinding | null;
  all_findings?: unknown;
  compliance_score?: unknown;
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
}

