import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

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

@Injectable({
  providedIn: 'root',
})
export class ApplicationsApiService {
  constructor(private http: HttpClient) {}

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
}

