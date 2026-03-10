import { Component, OnDestroy, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ReactiveFormsModule, FormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ApplicationsApiService, StartApplicationRequest, SowRequest, SowResponse, ReviewStreamEvent } from '../../../services/applications-api.service';
import { MarkdownPipe } from '../../../pipes/markdown.pipe';
import { forkJoin, of, Subscription } from 'rxjs';
import { finalize } from 'rxjs/operators';

type ApplicantType = 'individual' | 'business' | 'ngo';

export type FindingStatus = 'Critical' | 'Violation' | 'Warning' | 'Follow-up';

export interface ComplianceFinding {
  agent: string;
  findings: string;
  aiSuggestion: string;
  status: FindingStatus;
}

/** Status for Intake Agent – driven by stream; can be stream message when working */
export type IntakeAgentStatus = 'Completed' | 'Reviewing your documents…' | 'Waiting' | string;

/** Status for Code Enforcement Agent – driven by stream; can be stream message when working */
export type CodeAgentStatus = 'Completed' | 'Reviewing building regulations…' | 'Waiting' | string;

/** Status for Planning Agent – driven by stream; can be stream message when working */
export type PlannerAgentStatus = 'Completed' | 'Reviewing zoning requirements…' | 'Waiting' | string;

/** Status for Inspector Agent – driven by stream; can be stream message when working */
export type InspectorAgentStatus = 'Completed' | 'Finalizing your compliance summary…' | 'Waiting' | string;

export interface AgentActivityEvent {
  agentName: string;
  agentKey: 'intake' | 'code' | 'planner' | 'inspector';
  action: string;
  status: string;
  statusClass: string;
  time: string;
  /** Optional subtitle (e.g. "Extracting Application Details") */
  subtitle?: string;
  /** Optional fixed description for paced copy */
  description?: string;
  /** Optional detailed text populated from stream finding.detail */
  detail?: string;
}

@Component({
  selector: 'app-applications',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule, MarkdownPipe],
  templateUrl: './applications.component.html',
  styleUrl: './applications.component.scss',
})
export class ApplicationsComponent implements OnDestroy, AfterViewChecked {
  currentStep = 1;
  totalSteps = 6;
  steps = [1, 2, 3, 4, 5, 6];
  /** Highest step the user has reached by completing previous steps; prevents jumping to Step 4+ without data. */
  maxStepReached = 1;
  /** Unique application ID (UUID) created when user opens New Application – used across all steps */
  applicationId: string;
  applicationStarted = false;
  startApplicationLoading = false;
  startApplicationError = '';
  /** First request: send question_id as empty; after that use next_question_id from response (1, 2, 3, …). */
  sowQuestionId = '';
  /** First SOW request is sent with empty response to get the first question; after that we send user text. */
  firstSowRequestSent = false;
  sowLoading = false;
  sowError = '';
  step1Form: FormGroup;
  step2Form: FormGroup;
  step3Form: FormGroup;
  signatureFile: File | null = null;
  signatureFileName = '';
  blueprintFile: File | null = null;
  blueprintFileName = '';
  blueprintUploadLoading = false;
  blueprintUploadError = '';
  siteImageFiles: File[] = [];
  photosUploadLoading = false;
  photosUploadError = '';
  step3UploadLoading = false;

  /** Review stream (Step 4) subscription; unsubscribed on destroy. */
  reviewStreamSubscription: Subscription | null = null;
  reviewStreamError = '';

  /** When false, show Scope of Work Agent intro popup; when true, show chatbot. */
  scopeAgentChatOpen = false;

  @ViewChild('chatMessagesContainer') chatMessagesContainer: ElementRef<HTMLDivElement> | null = null;
  private lastCompanionMessagesLength = 0;

  aiCompanionMessages: { role: 'user' | 'bot'; text: string; isSow?: boolean }[] = [];
  aiCompanionInput = '';

  /** Index of the SOW message that shows "Copied!" after copy (reset after 2s). */
  copySowMessageIndex: number | null = null;

  /** Intake agent status – update from background API (polling or websocket) */
  intakeAgentStatus: IntakeAgentStatus = 'Completed';

  /** Code Enforcement agent status – update from background API */
  codeAgentStatus: CodeAgentStatus = 'Completed';

  /** Planning agent status – update from background API */
  plannerAgentStatus: PlannerAgentStatus = 'Reviewing zoning requirements…';

  /** Inspector agent status – update from background API */
  inspectorAgentStatus: InspectorAgentStatus = 'Waiting';

  /** Timeline events shown between Step 3 and Step 4 (AI agents at work) */
  agentActivityEvents: AgentActivityEvent[] = [
    {
      agentName: 'Intake Agent',
      agentKey: 'intake',
      action: 'Processing uploaded documents and extracting application details',
      status: 'DONE',
      statusClass: 'status-done',
      time: '11:43 am',
      subtitle: 'Extracting Application Details',
      description: "We're reviewing your uploaded documents and capturing key project information.",
    },
    {
      agentName: 'Code Enforcement Agent',
      agentKey: 'code',
      action: 'Analyzing project against building codes and zoning regulations',
      status: 'DONE',
      statusClass: 'status-done',
      time: '11:45 am',
      subtitle: 'Checking Building Code Compliance',
      description: "We're verifying your project against Austin building codes and safety standards.",
    },
    {
      agentName: 'Planning Agent',
      agentKey: 'planner',
      action: 'Reviewing site plan and land use compliance',
      status: 'IN PROGRESS',
      statusClass: 'status-progress',
      time: '11:47 am',
      subtitle: 'Reviewing Zoning & Land Use',
      description: "We're evaluating zoning rules, height limits, parking requirements, and overlay restrictions.",
    },
    {
      agentName: 'Inspector Agent',
      agentKey: 'inspector',
      action: 'Running final compliance checks and generating report',
      status: 'PENDING',
      statusClass: 'status-pending',
      time: '—',
      subtitle: 'Preparing Final Compliance Summary',
      description: "We're compiling the results of all checks into your pre-compliance report.",
    },
  ];

  /** Filled from review stream agent_done events (finding objects); or from "complete" event all_findings. */
  complianceFindings: ComplianceFinding[] = [];

  submissionPermitId = 'BLR-006';
  estimatedReviewDays = 18;

  constructor(
    private fb: FormBuilder,
    private router: Router,
    private applicationsApi: ApplicationsApiService,
  ) {
    this.applicationId = this.generateUUID();
    this.step1Form = this.fb.nonNullable.group({
      applicantType: ['individual' as ApplicantType],
      fullName: ['', [Validators.required, Validators.minLength(3)]],
      organization: [''],
      email: [''],
      phone: [''],
      address: ['', [Validators.required, Validators.minLength(3)]],
    });
    this.step2Form = this.fb.nonNullable.group({
      zoningType: [''],
      landAreaSqFt: [''],
      existingBuiltUpArea: [''],
      proposedBuiltUpArea: [''],
      noOfFloors: [''],
    });
    this.step3Form = this.fb.nonNullable.group({
      describeProposedWork: [''],
    });
  }

  get applicantType() {
    return this.step1Form.get('applicantType');
  }
  get fullName() {
    return this.step1Form.get('fullName');
  }
  get email() {
    return this.step1Form.get('email');
  }
  get phone() {
    return this.step1Form.get('phone');
  }
  get address() {
    return this.step1Form.get('address');
  }

  get zoningType() {
    return this.step2Form.get('zoningType');
  }
  get landAreaSqFt() {
    return this.step2Form.get('landAreaSqFt');
  }
  get existingBuiltUpArea() {
    return this.step2Form.get('existingBuiltUpArea');
  }
  get proposedBuiltUpArea() {
    return this.step2Form.get('proposedBuiltUpArea');
  }
  get noOfFloors() {
    return this.step2Form.get('noOfFloors');
  }

  get describeProposedWork() {
    return this.step3Form.get('describeProposedWork');
  }

  get describeWorkLength(): number {
    return (this.step3Form.get('describeProposedWork')?.value ?? '').length;
  }

  onSignatureChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      this.signatureFile = file;
      this.signatureFileName = file.name;
    }
  }

  onBlueprintChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      this.blueprintFile = file;
      this.blueprintFileName = file.name;
    }
  }

  onBlueprintDrop(files: FileList | null): void {
    if (files?.length) {
      const file = files[0];
      this.blueprintFile = file;
      this.blueprintFileName = file.name;
    }
  }

  readonly maxSiteImages = 3;

  onSiteImagesChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = input.files;
    if (files?.length) {
      const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/')).slice(0, this.maxSiteImages);
      this.siteImageFiles = imageFiles;
      input.value = '';
    }
  }

  onSiteImagesDrop(files: FileList | null): void {
    if (files?.length) {
      const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'));
      const next = [...this.siteImageFiles, ...imageFiles].slice(0, this.maxSiteImages);
      this.siteImageFiles = next;
    }
  }

  private uploadBlueprintFile(file: File): void {
    if (!this.applicationId) return;
    this.blueprintUploadLoading = true;
    this.blueprintUploadError = '';
    this.applicationsApi.uploadBlueprint(this.applicationId, file).subscribe({
      next: () => {
        this.blueprintUploadLoading = false;
      },
      error: (err) => {
        console.error('Blueprint upload failed:', err);
        this.blueprintUploadLoading = false;
        const statusVal = err?.status;
        const status =
          statusVal === 0 || typeof statusVal === 'number'
            ? ` (HTTP ${statusVal}${err?.statusText ? ` ${err.statusText}` : ''})`
            : '';
        const url = err?.url ? ` URL: ${err.url}` : '';
        const hint =
          statusVal === 0
            ? ' Request blocked (CORS / network).'
            : statusVal === 404
              ? ' Upload endpoint not found.'
              : '';
        this.blueprintUploadError = `Blueprint upload failed${status}.${hint}${url}`;
      },
    });
  }

  private uploadPhotoFiles(files: File[]): void {
    if (!this.applicationId || files.length === 0) return;
    this.photosUploadLoading = true;
    this.photosUploadError = '';
    this.applicationsApi.uploadPhotos(this.applicationId, files).subscribe({
      next: () => {
        this.photosUploadLoading = false;
      },
      error: (err) => {
        console.error('Photo upload failed:', err);
        this.photosUploadLoading = false;
        const statusVal = err?.status;
        const status =
          statusVal === 0 || typeof statusVal === 'number'
            ? ` (HTTP ${statusVal}${err?.statusText ? ` ${err.statusText}` : ''})`
            : '';
        const url = err?.url ? ` URL: ${err.url}` : '';
        const hint =
          statusVal === 0
            ? ' Request blocked (CORS / network).'
            : statusVal === 404
              ? ' Upload endpoint not found.'
              : '';
        this.photosUploadError = `Photo upload failed${status}.${hint}${url}`;
      },
    });
  }

  saveAndContinue(): void {
    if (this.currentStep === 1) {
      this.step1Form.markAllAsTouched();
      if (this.step1Form.valid) {
        this.currentStep = 2; // applicationId already set on load; /applications/start is called at Step 2
        this.maxStepReached = Math.max(this.maxStepReached, 2);
      }
    } else if (this.currentStep === 2) {
      this.step2Form.markAllAsTouched();
      if (!this.step2Form.valid) return;
      if (this.applicationStarted) {
        this.currentStep = 3;
        this.maxStepReached = Math.max(this.maxStepReached, 3);
        return;
      }
      const step1 = this.step1Form.getRawValue();
      const step2 = this.step2Form.getRawValue();
      const startPayload: StartApplicationRequest = {
        application_id: this.applicationId,
        date: new Date().toISOString(),
        application_type: 'NEW',
        owner_name: (step1.fullName ?? '').toString(),
        project_address: (step1.address ?? '').toString(),
        zoning_type: (step2.zoningType ?? '').toString(),
      };
      this.startApplicationLoading = true;
      this.startApplicationError = '';
      this.applicationsApi.startApplication(startPayload).subscribe({
        next: (res: unknown) => {
          const body = res as { application_id?: string | number; app_id?: string | number };
          const id = body?.application_id ?? body?.app_id;
          if (id !== undefined && id !== null && String(id).trim()) this.applicationId = String(id).trim();
          this.applicationStarted = true;
          this.startApplicationLoading = false;
          this.startApplicationError = '';
          this.currentStep = 3;
          this.maxStepReached = Math.max(this.maxStepReached, 3);
        },
        error: (err) => {
          console.error('Start application failed:', err);
          this.startApplicationLoading = false;
          this.startApplicationError = 'Failed to start application. Please try again.';
        },
      });
    } else if (this.currentStep === 3) {
      this.step3Form.markAllAsTouched();
      if (this.step3Form.valid) {
        if (this.step3UploadLoading) return;

        this.step3UploadLoading = true;
        this.blueprintUploadError = '';
        this.photosUploadError = '';

        const uploads = forkJoin({
          blueprint: this.blueprintFile
            ? this.applicationsApi.uploadBlueprint(this.applicationId, this.blueprintFile)
            : of(null),
          photos:
            this.siteImageFiles.length > 0 ? this.applicationsApi.uploadPhotos(this.applicationId, this.siteImageFiles) : of(null),
        });

        // Mirror loading flags so UI can show progress under each control
        this.blueprintUploadLoading = !!this.blueprintFile;
        this.photosUploadLoading = this.siteImageFiles.length > 0;

        uploads.subscribe({
          next: () => {
            this.step3UploadLoading = false;
            this.blueprintUploadLoading = false;
            this.photosUploadLoading = false;
            this.reviewStreamError = '';
            this.currentStep = 4; // Move to Step 4 first, then start streaming
            this.maxStepReached = Math.max(this.maxStepReached, 4);
            this.startReviewStream(); // Keeps running until stream ends; statuses update from events, then all set to Completed on complete
          },
          error: (err) => {
            console.error('Step 3 upload failed:', err);
            this.step3UploadLoading = false;
            this.blueprintUploadLoading = false;
            this.photosUploadLoading = false;
            // Keep user on Step 3 and show errors (best-effort: use same err for whichever was attempted)
            const statusVal = err?.status;
            const status =
              statusVal === 0 || typeof statusVal === 'number'
                ? ` (HTTP ${statusVal}${err?.statusText ? ` ${err.statusText}` : ''})`
                : '';
            const url = err?.url ? ` URL: ${err.url}` : '';
            const hint =
              statusVal === 0 ? ' Request blocked (CORS / network).' : statusVal === 404 ? ' Upload endpoint not found.' : '';
            const msg = `Upload failed${status}.${hint}${url}`;
            if (this.blueprintFile) this.blueprintUploadError = msg;
            if (this.siteImageFiles.length > 0) this.photosUploadError = msg;
          },
        });
      }
    }
  }

  /** Start GET /review/{app_id}/stream and update Step 4 agent statuses from each event. Runs until stream ends or API sends done. */
  startReviewStream(): void {
    this.reviewStreamSubscription?.unsubscribe();
    this.reviewStreamSubscription = null;
    this.reviewStreamError = '';

    this.intakeAgentStatus = 'Waiting';
    this.codeAgentStatus = 'Waiting';
    this.plannerAgentStatus = 'Waiting';
    this.inspectorAgentStatus = 'Waiting';

    // Reset timeline times so they update from the stream
    this.agentActivityEvents = this.agentActivityEvents.map((e) => ({ ...e, time: '—' }));

    this.reviewStreamSubscription = this.applicationsApi.getReviewStream(this.applicationId).subscribe({
      next: (event: ReviewStreamEvent) => this.applyReviewStreamEvent(event),
      error: (err) => {
        this.reviewStreamError = err?.message || 'Review stream failed. Set Bearer token (e.g. in Settings or environment.reviewStreamAuthToken) if the API requires authentication.';
        this.reviewStreamSubscription = null;
      },
      complete: () => {
        this.reviewStreamSubscription = null;
        if (!this.reviewStreamError) {
          this.intakeAgentStatus = 'Completed';
          this.codeAgentStatus = 'Completed';
          this.plannerAgentStatus = 'Completed';
          this.inspectorAgentStatus = 'Completed';
        }
      },
    });
  }

  /** Format current time as "h:mm a" (e.g. 2:46 pm) for timeline display. */
  private getCurrentTimeFormatted(): string {
    const d = new Date();
    const h = d.getHours();
    const m = d.getMinutes();
    const ampm = h >= 12 ? 'pm' : 'am';
    const h12 = h % 12 || 12;
    return `${h12}:${m.toString().padStart(2, '0')} ${ampm}`;
  }

  /** Update the timeline time for the given agent to current time. */
  private updateAgentEventTime(agentKey: 'intake' | 'code' | 'planner' | 'inspector'): void {
    const time = this.getCurrentTimeFormatted();
    this.agentActivityEvents = this.agentActivityEvents.map((e) =>
      e.agentKey === agentKey ? { ...e, time } : e
    );
  }

  /**
   * Display status for the 4 agents from stream event.
   * For "Intake: Blueprint Analysis" → "Blueprint Analysis"; for others use message.
   */
  private getDisplayStatusForStream(event: ReviewStreamEvent): string {
    const name = event.agent_name || '';
    if (name.startsWith('Intake: ')) return name.slice('Intake: '.length).trim();
    return event.message || 'Working…';
  }

  /**
   * Map stream agent_name to one of the 4 agents: Intake, Code Enforcement, Planning, Inspector.
   */
  private getAgentKeyFromStreamName(agentName: string): 'intake' | 'code' | 'planner' | 'inspector' | null {
    const name = (agentName || '').toLowerCase();
    if (name.includes('intake')) return 'intake';
    if (name.includes('code enforcement') || name === 'code enforcement') return 'code';
    if (name.includes('zoning') || name.includes('planner') || name.includes('planning')) return 'planner';
    if (name.includes('inspector') || name.includes('field inspector')) return 'inspector';
    return null;
  }

  /** Map SSE event to the 4 agents only. Agent name stays fixed; status shows sub-task (e.g. "Blueprint Analysis") or message, then "Completed". Handles event_type "complete". */
  private applyReviewStreamEvent(event: ReviewStreamEvent): void {
    console.log("Stream event review=====>", event)
    const isComplete = event.event_type === 'complete';
    const isStart = event.event_type === 'agent_start';
    const isDone = event.event_type === 'agent_done';
    const time = this.getCurrentTimeFormatted();

    if (isComplete) {
      this.setIntakeAgentStatus('Completed');
      this.setCodeAgentStatus('Completed');
      this.setPlannerAgentStatus('Completed');
      this.setInspectorAgentStatus('Completed');
      if (Array.isArray(event.all_findings) && event.all_findings.length > 0) {
        this.complianceFindings = event.all_findings.map((f) => {
          const severity = (f.severity || '').toLowerCase();
          let status: FindingStatus = 'Follow-up';
          if (severity === 'critical') status = 'Critical';
          else if (severity === 'warning') status = 'Warning';
          else if (severity === 'violation') status = 'Violation';
          else if (severity === 'pass') status = 'Follow-up';
          return {
            agent: f.agent || '—',
            findings: f.finding || '',
            aiSuggestion: f.detail ?? '',
            status,
          };
        });
      }
      return;
    }

    const agentKey = this.getAgentKeyFromStreamName(event.agent_name || '');

    if (isStart && agentKey) {
      const displayStatus = this.getDisplayStatusForStream(event);
      if (agentKey === 'intake') this.setIntakeAgentStatus(displayStatus);
      else if (agentKey === 'code') this.setCodeAgentStatus(displayStatus);
      else if (agentKey === 'planner') this.setPlannerAgentStatus(displayStatus);
      else if (agentKey === 'inspector') this.setInspectorAgentStatus(displayStatus);
      this.updateAgentEventTime(agentKey);
    } else if (isDone && agentKey) {
      if (agentKey === 'intake') this.setIntakeAgentStatus('Completed');
      else if (agentKey === 'code') this.setCodeAgentStatus('Completed');
      else if (agentKey === 'planner') this.setPlannerAgentStatus('Completed');
      else if (agentKey === 'inspector') this.setInspectorAgentStatus('Completed');
      this.updateAgentEventTime(agentKey);
      // Use finding.detail for the timeline card, appending if the same agent emits multiple findings
      if (event.finding?.detail) {
        const detail = event.finding.detail.trim();
        this.agentActivityEvents = this.agentActivityEvents.map((e) => {
          if (e.agentKey !== agentKey) return e;
          const prev = (e.detail ?? '').trim();
          const next = prev ? `${prev}\n\n${detail}` : detail;
          return { ...e, detail: next };
        });
      }
    }

    if (isDone && event.finding) {
      const f = event.finding;
      const severity = (f.severity || '').toLowerCase();
      let status: FindingStatus = 'Follow-up';
      if (severity === 'critical') status = 'Critical';
      else if (severity === 'warning') status = 'Warning';
      else if (severity === 'violation') status = 'Violation';
      this.complianceFindings = [...this.complianceFindings, {
        agent: f.agent || event.agent_name || '—',
        findings: f.finding || '',
        aiSuggestion: f.detail ?? '',
        status,
      }];
    }
  }

  /** Call this from your background API / polling / websocket to update Intake agent status */
  setIntakeAgentStatus(status: IntakeAgentStatus): void {
    this.intakeAgentStatus = status;
  }

  /** CSS class for Intake agent status (for styling Completed / Reviewing… / Waiting) */
  getIntakeAgentStatusClass(): string {
    if (this.intakeAgentStatus === 'Completed') return 'status-done';
    if (this.intakeAgentStatus === 'Waiting') return 'status-pending';
    return 'status-progress'; // any "reviewing" or stream message
  }

  /** Call this from your background API to update Code Enforcement agent status */
  setCodeAgentStatus(status: CodeAgentStatus): void {
    this.codeAgentStatus = status;
  }

  /** CSS class for Code Enforcement agent status */
  getCodeAgentStatusClass(): string {
    if (this.codeAgentStatus === 'Completed') return 'status-done';
    if (this.codeAgentStatus === 'Waiting') return 'status-pending';
    return 'status-progress';
  }

  /** Call this from your background API to update Planning agent status */
  setPlannerAgentStatus(status: PlannerAgentStatus): void {
    this.plannerAgentStatus = status;
  }

  /** CSS class for Planning agent status */
  getPlannerAgentStatusClass(): string {
    if (this.plannerAgentStatus === 'Completed') return 'status-done';
    if (this.plannerAgentStatus === 'Waiting') return 'status-pending';
    return 'status-progress';
  }

  /** Call this from your background API to update Inspector agent status */
  setInspectorAgentStatus(status: InspectorAgentStatus): void {
    this.inspectorAgentStatus = status;
  }

  /** CSS class for Inspector agent status */
  getInspectorAgentStatusClass(): string {
    if (this.inspectorAgentStatus === 'Completed') return 'status-done';
    if (this.inspectorAgentStatus === 'Waiting') return 'status-pending';
    return 'status-progress';
  }

  /** True only when all four agents have completed their work */
  get canContinueToPreComplianceReport(): boolean {
    return (
      this.intakeAgentStatus === 'Completed' &&
      this.codeAgentStatus === 'Completed' &&
      this.plannerAgentStatus === 'Completed' &&
      this.inspectorAgentStatus === 'Completed'
    );
  }

  continueToPreComplianceReport(): void {
    if (this.currentStep === 4 && this.canContinueToPreComplianceReport) {
      this.currentStep = 5;
      this.maxStepReached = Math.max(this.maxStepReached, 5);
    }
  }

  goToStep(step: number): void {
    if (step >= 1 && step <= this.totalSteps && step <= this.maxStepReached) {
      this.currentStep = step;
    }
  }

  goToNextStep(): void {
    if (this.currentStep < this.totalSteps) {
      this.currentStep++;
    }
  }

  getStepTitle(step: number): string {
    const titles: Record<number, string> = {
      1: 'Applicant Information',
      2: 'Property Details',
      3: 'Scope of Work & Document Upload',
      4: 'AI Agents at Work',
      5: 'AI Permit Readiness Report',
      6: 'Submission Confirmation',
    };
    return titles[step] ?? `Step ${step}`;
  }

  /** Generate a UUID v4 for applicationId (created when New Application is opened). */
  private generateUUID(): string {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  /** Beautify generated_sow for display: pretty-print JSON if valid, otherwise normalize whitespace. */
  getBeautifiedSow(raw: string): string {
    if (!raw?.trim()) return '';
    const text = raw.trim();
    try {
      const parsed = JSON.parse(text);
      return typeof parsed === 'string' ? parsed : JSON.stringify(parsed, null, 2);
    } catch {
      return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    }
  }

  copySowFromMessage(text: string, index: number): void {
    if (!text) return;
    navigator.clipboard.writeText(text).then(
      () => {
        this.copySowMessageIndex = index;
        setTimeout(() => (this.copySowMessageIndex = null), 2000);
      },
      () => {},
    );
  }

  /**
   * When the API returns multiple numbered questions in one string (e.g. "1) ... 2) ..." or "1. ... 2. ..."),
   * return only the N-th block so we show one question at a time: first on open, then 2nd after first answer, etc.
   */
  private getNthQuestion(nextQuestion: string, n: number): string {
    if (!nextQuestion?.trim()) return nextQuestion || '';
    const raw = nextQuestion.trim();
    const oneBasedIndex = Math.max(1, n || 1);

    // Match blocks that start with "1) ", "2) ", "1. ", "2. " etc. (digit + ) or . + space), content until next such pattern or end
    const blockRegex = /\d+[\).]\s*[\s\S]*?(?=\d+[\).]\s|$)/gi;
    const blocks = raw.match(blockRegex);
    if (blocks && blocks.length > 0) {
      const index = Math.min(oneBasedIndex - 1, blocks.length - 1);
      return blocks[index].trim();
    }

    // Fallback: split by newline when line starts with number + ) or .
    const lines = raw.split(/\n/);
    const result: string[] = [];
    let current: string[] = [];
    for (const line of lines) {
      if (/^\s*\d+[\).]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
        if (current.length > 0) result.push(current.join('\n').trim());
        current = [line];
      } else {
        current.push(line);
      }
    }
    if (current.length > 0) result.push(current.join('\n').trim());

    if (result.length > 0) {
      const index = Math.min(oneBasedIndex - 1, result.length - 1);
      return result[index];
    }

    return oneBasedIndex === 1 ? raw : raw.split(/\n\n+/)[0]?.trim() || raw;
  }

  /** Application data (applicationId + steps data) for API or persistence. */
  getApplicationData(): {
    applicationId: string;
    step1: Record<string, unknown>;
    step2: Record<string, unknown>;
    step3: Record<string, unknown>;
    currentStep: number;
  } {
    return {
      applicationId: this.applicationId,
      step1: this.step1Form.getRawValue(),
      step2: this.step2Form.getRawValue(),
      step3: this.step3Form.getRawValue(),
      currentStep: this.currentStep,
    };
  }

  editApplication(): void {
    this.goToStep(3);
  }

  /** True when at least one finding has Critical severity – disables Submit for Review in Step 5 */
  get hasCriticalSeverity(): boolean {
    return this.complianceFindings.some((f) => f.status === 'Critical');
  }

  submitForReview(): void {
    const year = new Date().getFullYear();
    const num = Math.floor(1000 + Math.random() * 9000);
    this.submissionPermitId = `BLR-${year}-${num}`;
    this.maxStepReached = Math.max(this.maxStepReached, 6);
    this.goToStep(6);
  }

  /** Agent icon paths for Step 4 timeline (AI Agents at Work) */
  getAgentImageUrl(agentKey: 'intake' | 'code' | 'planner' | 'inspector'): string {
    const map: Record<string, string> = {
      intake: 'assets/agents/Intake_Agent.png',
      code: 'assets/agents/Code_Enforcement_Agent.png',
      planner: 'assets/agents/Planning_Agent.png',
      inspector: 'assets/agents/Inspector_Agent.png',
    };
    return map[agentKey] ?? 'assets/agents/Intake_Agent.png';
  }

  getFindingStatusClass(status: FindingStatus): string {
    return 'status-' + status.toLowerCase().replace(/\s+/g, '-');
  }

  /** Display name for Agent column in Step 5 – e.g. Code → Code Enforcement Agent */
  getAgentDisplayName(agent: string): string {
    if (agent === 'Code') return 'Code Enforcement Agent';
    return agent;
  }

  downloadCopy(): void {
    // Placeholder: generate or download submission copy
    console.log('Download copy for permit', this.submissionPermitId);
  }

  returnToDashboard(): void {
    this.router.navigate(['/dashboard']);
  }

  ngOnDestroy(): void {
    this.reviewStreamSubscription?.unsubscribe();
    this.reviewStreamSubscription = null;
  }

  ngAfterViewChecked(): void {
    if (this.chatMessagesContainer?.nativeElement && this.aiCompanionMessages.length !== this.lastCompanionMessagesLength) {
      this.lastCompanionMessagesLength = this.aiCompanionMessages.length;
      this.scrollChatToBottom();
    }
  }

  private scrollChatToBottom(): void {
    const el = this.chatMessagesContainer?.nativeElement;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }

  /** True while the review stream is active (Step 4); used to show "Receiving agent updates…" until all agents complete. */
  get isReviewStreamActive(): boolean {
    return this.reviewStreamSubscription != null;
  }

  /** Called when user clicks the Scope of Work Agent icon; opens chat and fetches first question if not yet sent. */
  openScopeAgentChat(): void {
    this.scopeAgentChatOpen = true;
    if (!this.applicationId) {
      this.aiCompanionMessages.push({
        role: 'bot',
        text: 'Please complete Step 2 (Save & Continue) first so we can start your Scope of Work questionnaire.',
      });
      return;
    }
    if (!this.firstSowRequestSent) {
      this.fetchFirstSowQuestion();
    }
  }

  /** Call SOW API with empty question_id and response to get the first question; show it in chat. */
  private fetchFirstSowQuestion(): void {
    this.sowLoading = true;
    this.sowError = '';
    const payload: SowRequest = {
      application_id: this.applicationId,
      question_id: '',
      response: '',
    };
    this.firstSowRequestSent = true;

    this.applicationsApi.sendSowMessage(payload).pipe(
      finalize(() => (this.sowLoading = false)),
    ).subscribe({
      next: (res: SowResponse) => {
        this.sowQuestionId = '1'; // next request will be user's answer to question 1

        if (res.next_question) {
          const textToShow = this.getNthQuestion(res.next_question, 1);
          const intro = 'To proceed with your new construction permit, please provide the following details:';
          const displayText = `${intro}\n\n${textToShow}`;
          this.aiCompanionMessages.push({
            role: 'bot',
            text: displayText,
          });
        }

        if (res.generated_sow) {
          const beautified = this.getBeautifiedSow(res.generated_sow);
          this.aiCompanionMessages.push({
            role: 'bot',
            text: beautified,
            isSow: true,
          });
        }
      },
      error: (err) => {
        console.error('SOW fetch first question error:', err);
        this.firstSowRequestSent = false;
        this.sowError = 'Unable to load the first question. Please try again.';
        this.aiCompanionMessages.push({
          role: 'bot',
          text: 'Sorry, I could not load the first question right now. Please try again.',
        });
      },
    });
  }

  sendAiMessage(): void {
    const text = this.aiCompanionInput?.trim();
    if (!text || this.sowLoading) return;

    this.aiCompanionMessages.push({ role: 'user', text });
    this.aiCompanionInput = '';
    this.sowLoading = true;
    this.sowError = '';
    setTimeout(() => this.scrollChatToBottom(), 80);

    // Every SOW request: { application_id, question_id, response }. First time: question_id empty, response empty;
    // after that question_id = next_question_id from previous response (1, 2, 3, …), response = user text.
    const payload: SowRequest = {
      application_id: this.applicationId,
      question_id: this.sowQuestionId,
      response: this.firstSowRequestSent ? text : '',
    };
    if (!this.firstSowRequestSent) this.firstSowRequestSent = true;

    this.applicationsApi.sendSowMessage(payload).pipe(
      finalize(() => (this.sowLoading = false)),
    ).subscribe({
      next: (res: SowResponse) => {
        const sentQuestionNum = this.sowQuestionId === '' ? 1 : parseInt(this.sowQuestionId, 10) || 1;
        // Use sequential question_id for next payload: "" → "2", "2" → "3", "3" → "4", etc. (ignore API next_question_id)
        const nextNum = sentQuestionNum + 1;
        this.sowQuestionId = String(nextNum);

        if (res.next_question) {
          // sentQuestionNum = question user just answered; show the NEXT question (e.g. 2nd block)
          const nextQuestionIndex = sentQuestionNum + 1;
          const textToShow = this.getNthQuestion(res.next_question, nextQuestionIndex);
          // Do not prepend the intro here — intro is only for the very first question (in fetchFirstSowQuestion).
          this.aiCompanionMessages.push({
            role: 'bot',
            text: textToShow,
          });
        }

        if (res.generated_sow) {
          const beautified = this.getBeautifiedSow(res.generated_sow);
          this.aiCompanionMessages.push({
            role: 'bot',
            text: beautified,
            isSow: true,
          });
        }
      },
      error: (err) => {
        console.error('SOW AI companion error:', err);
        this.sowError = 'AI companion is unavailable. Please try again.';
        this.aiCompanionMessages.push({
          role: 'bot',
          text: 'Sorry, I could not process that right now. Please try again.',
        });
      },
    });
  }
}
