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
}

