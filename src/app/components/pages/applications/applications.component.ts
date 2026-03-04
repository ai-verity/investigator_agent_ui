import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ReactiveFormsModule, FormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';

type ApplicantType = 'individual' | 'business' | 'ngo';

export type FindingStatus = 'Critical' | 'Violation' | 'Warning' | 'Follow-up';

export interface ComplianceFinding {
  agent: string;
  findings: string;
  aiSuggestion: string;
  status: FindingStatus;
}

/** Status for Intake Agent – driven by background API */
export type IntakeAgentStatus = 'Completed' | 'Reviewing your documents…' | 'Waiting';

/** Status for Code Enforcement Agent – driven by background API */
export type CodeAgentStatus = 'Completed' | 'Reviewing building regulations…' | 'Waiting';

/** Status for Planning Agent – driven by background API */
export type PlannerAgentStatus = 'Completed' | 'Reviewing zoning requirements…' | 'Waiting';

/** Status for Inspector Agent – driven by background API */
export type InspectorAgentStatus = 'Completed' | 'Finalizing your compliance summary…' | 'Waiting';

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
}

@Component({
  selector: 'app-applications',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule],
  templateUrl: './applications.component.html',
  styleUrl: './applications.component.scss',
})
export class ApplicationsComponent {
  currentStep = 1;
  totalSteps = 6;
  steps = [1, 2, 3, 4, 5, 6];
  /** Unique application ID (UUID) created when user opens New Application – used across all steps */
  applicationId: string;
  step1Form: FormGroup;
  step2Form: FormGroup;
  step3Form: FormGroup;
  signatureFile: File | null = null;
  signatureFileName = '';
  blueprintFile: File | null = null;
  blueprintFileName = '';
  siteImageFiles: File[] = [];
  readonly describeWorkMaxLength = 2000;

  aiCompanionMessages: { role: 'user' | 'bot'; text: string }[] = [
    { role: 'bot', text: "Hi! I'm your AI companion for this step. Ask me anything about scope of work or document upload." },
  ];
  aiCompanionInput = '';

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

  complianceFindings: ComplianceFinding[] = [
    { agent: 'Intake', findings: 'Missing Fire Egress', aiSuggestion: 'Add Fire Egress', status: 'Critical' },
    { agent: 'Code Enforcement', findings: 'Railing Height 34"', aiSuggestion: 'Railing Height 36"', status: 'Violation' },
    { agent: 'Planner', findings: 'Impervious 44.2%', aiSuggestion: 'Impervious 48%', status: 'Warning' },
    { agent: 'Inspector', findings: 'Unpermitted Shed', aiSuggestion: 'NA', status: 'Follow-up' },
  ];

  submissionPermitId = 'BLR-006';
  estimatedReviewDays = 18;

  constructor(private fb: FormBuilder, private router: Router) {
    this.applicationId = this.generateUUID();
    this.step1Form = this.fb.nonNullable.group({
      applicantType: ['individual' as ApplicantType],
      fullName: [''],
      organization: [''],
      email: [''],
      phone: [''],
      address: [''],
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
      if (file.type === 'application/pdf') {
        this.blueprintFile = file;
        this.blueprintFileName = file.name;
      }
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
      this.siteImageFiles = [...this.siteImageFiles, ...imageFiles].slice(0, this.maxSiteImages);
    }
  }

  saveAndContinue(): void {
    if (this.currentStep === 1) {
      this.step1Form.markAllAsTouched();
      if (this.step1Form.valid) {
        this.currentStep = 2;
      }
    } else if (this.currentStep === 2) {
      this.step2Form.markAllAsTouched();
      if (this.step2Form.valid) {
        this.currentStep = 3;
      }
    } else if (this.currentStep === 3) {
      this.step3Form.markAllAsTouched();
      if (this.step3Form.valid) {
        // Collect all data (Step 1–3 + applicationId) for submit
        const payload = this.getApplicationData();
        console.log('New application submit payload (Step 1–3):', payload);
        this.currentStep = 4; // Show "AI Agents at Work" timeline
      }
    }
  }

  /** Call this from your background API / polling / websocket to update Intake agent status */
  setIntakeAgentStatus(status: IntakeAgentStatus): void {
    this.intakeAgentStatus = status;
  }

  /** CSS class for Intake agent status (for styling Completed / Reviewing… / Waiting) */
  getIntakeAgentStatusClass(): string {
    switch (this.intakeAgentStatus) {
      case 'Completed':
        return 'status-done';
      case 'Reviewing your documents…':
        return 'status-progress';
      case 'Waiting':
        return 'status-pending';
      default:
        return 'status-pending';
    }
  }

  /** Call this from your background API to update Code Enforcement agent status */
  setCodeAgentStatus(status: CodeAgentStatus): void {
    this.codeAgentStatus = status;
  }

  /** CSS class for Code Enforcement agent status */
  getCodeAgentStatusClass(): string {
    switch (this.codeAgentStatus) {
      case 'Completed':
        return 'status-done';
      case 'Reviewing building regulations…':
        return 'status-progress';
      case 'Waiting':
        return 'status-pending';
      default:
        return 'status-pending';
    }
  }

  /** Call this from your background API to update Planning agent status */
  setPlannerAgentStatus(status: PlannerAgentStatus): void {
    this.plannerAgentStatus = status;
  }

  /** CSS class for Planning agent status */
  getPlannerAgentStatusClass(): string {
    switch (this.plannerAgentStatus) {
      case 'Completed':
        return 'status-done';
      case 'Reviewing zoning requirements…':
        return 'status-progress';
      case 'Waiting':
        return 'status-pending';
      default:
        return 'status-pending';
    }
  }

  /** Call this from your background API to update Inspector agent status */
  setInspectorAgentStatus(status: InspectorAgentStatus): void {
    this.inspectorAgentStatus = status;
  }

  /** CSS class for Inspector agent status */
  getInspectorAgentStatusClass(): string {
    switch (this.inspectorAgentStatus) {
      case 'Completed':
        return 'status-done';
      case 'Finalizing your compliance summary…':
        return 'status-progress';
      case 'Waiting':
        return 'status-pending';
      default:
        return 'status-pending';
    }
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
    }
  }

  goToStep(step: number): void {
    if (step >= 1 && step <= this.totalSteps) {
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

  sendAiMessage(): void {
    const text = this.aiCompanionInput?.trim();
    if (!text) return;
    this.aiCompanionMessages.push({ role: 'user', text });
    this.aiCompanionInput = '';
    // Placeholder bot reply – replace with API call later
    this.aiCompanionMessages.push({
      role: 'bot',
      text: "Thanks for your message. I'm here to help with scope of work and document upload. (This is a placeholder reply.)",
    });
  }
}
