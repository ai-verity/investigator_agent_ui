import { Component, OnInit, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ApplicationsApiService, ApplicationDetail, ReviewStreamFinding } from '../../../services/applications-api.service';
import { MarkdownPipe } from '../../../pipes/markdown.pipe';

/** Record data for view application page – all values from API, no hardcoding. */
export interface ViewApplicationRecord {
  permitId: string;
  applicantType?: string;
  applicant: string;
  organization?: string;
  email?: string;
  phone?: string;
  address: string;
  zoningType?: string;
  landAreaSqFt?: number | string;
  existingBuiltUpArea?: number | string;
  proposedBuiltUpArea?: number | string;
  noOfFloors?: number | string;
  scopeOfWork?: string;
  permitType?: string;
  submittedDate?: string;
  submittedTime?: string;
  status?: string;
  signatureFileName?: string;
  blueprintFileName?: string;
  siteImagesCount?: number | string;
}

@Component({
  selector: 'app-view-application',
  standalone: true,
  imports: [CommonModule, MarkdownPipe],
  templateUrl: './view-application.component.html',
  styleUrl: './view-application.component.scss',
})
export class ViewApplicationComponent implements OnInit {
  currentStep = 1;
  totalSteps = 6;
  steps = [1, 2, 3, 4, 5, 6];

  record: ViewApplicationRecord | null = null;
  viewLoading = false;
  viewError = '';

  agentActivityEvents = [
    { agentName: 'Intake Agent', agentKey: 'intake' as const, status: 'DONE', time: '11:43 am', description: "We're reviewing your uploaded documents and capturing key project information." },
    { agentName: 'Code Enforcement Agent', agentKey: 'code' as const, status: 'DONE', time: '11:45 am', description: "We're verifying your project against Austin building codes and safety standards." },
    { agentName: 'Planning Agent', agentKey: 'planner' as const, status: 'DONE', time: '11:47 am', description: "We're evaluating zoning rules, height limits, parking requirements, and overlay restrictions." },
    { agentName: 'Inspector Agent', agentKey: 'inspector' as const, status: 'DONE', time: '11:49 am', description: "We're compiling the results of all checks into your pre-compliance report." },
  ];

  complianceFindings = [
    { agent: 'Intake', findings: 'Missing Fire Egress', aiSuggestion: 'Add Fire Egress', status: 'Critical' },
    { agent: 'Code Enforcement', findings: 'Railing Height 34"', aiSuggestion: 'Railing Height 36"', status: 'Violation' },
    { agent: 'Planner', findings: 'Impervious 44.2%', aiSuggestion: 'Impervious 48%', status: 'Warning' },
    { agent: 'Inspector', findings: 'Unpermitted Shed', aiSuggestion: 'NA', status: 'Follow-up' },
  ];
  complianceFindingsLoading = false;
  complianceFindingsError = '';

  constructor(
    private router: Router,
    private applicationsApi: ApplicationsApiService,
  ) {}

  ngOnInit(): void {
    const state = (this.router.lastSuccessfulNavigation?.extras?.state ??
      this.router.getCurrentNavigation()?.extras?.state ??
      (typeof history !== 'undefined' ? history.state : null)) as { appId?: string; record?: ViewApplicationRecord } | null;

    const appId = state?.appId;
    if (appId) {
      this.viewLoading = true;
      this.viewError = '';
      this.applicationsApi.viewApplication(appId).subscribe({
        next: (item: ApplicationDetail) => {
          this.viewLoading = false;
          this.record = this.mapDetailToRecord(item);
        },
        error: () => {
          this.viewLoading = false;
          this.viewError = 'Failed to load application.';
        },
      });
      return;
    }
    if (state?.record) {
      this.record = state.record;
    }
  }

  private mapDetailToRecord(item: ApplicationDetail): ViewApplicationRecord {
    const toStr = (v: unknown) => (v === undefined || v === null ? '' : String(v).trim());
    const toNum = (v: unknown): number | string | undefined => {
      if (v === undefined || v === null) return undefined;
      if (typeof v === 'number') return v;
      const s = String(v).trim();
      if (s === '') return undefined;
      const n = Number(s);
      return Number.isNaN(n) ? s : n;
    };
    const opt = (v: unknown) => (v === undefined || v === null || toStr(v) === '' ? undefined : toStr(v));
    return {
      permitId: toStr(item.application_id ?? item.permit_id) || '',
      applicantType: opt(item.applicant_type),
      applicant: toStr(item.owner_name ?? item.full_name) || '',
      organization: opt(item.organization),
      email: opt(item.email),
      phone: opt(item.phone),
      address: toStr(item.project_address ?? item.address) || '',
      zoningType: opt(item.zoning_type),
      landAreaSqFt: toNum(item.land_area_sq_ft),
      existingBuiltUpArea: toNum(item.existing_built_up_area),
      proposedBuiltUpArea: toNum(item.proposed_built_up_area),
      noOfFloors: toNum(item.no_of_floors),
      scopeOfWork: opt(item.sow_text ?? item.describe_proposed_work),
      permitType: opt(item.application_type),
      submittedDate: opt(item.submitted_date),
      submittedTime: opt(item.submitted_time),
      status: opt(item.status),
      signatureFileName: opt(item.signature_file_name),
      blueprintFileName: opt(item.blueprint_file_name),
      siteImagesCount: toNum(item.site_images_count),
    };
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

  goToStep(step: number): void {
    if (step >= 1 && step <= this.totalSteps) {
      this.currentStep = step;
      if (step === 5 && this.record) this.loadFindings();
    }
  }

  goToNextStep(): void {
    if (this.currentStep < this.totalSteps) {
      this.currentStep++;
      if (this.currentStep === 5 && this.record) this.loadFindings();
    }
  }

  returnToDashboard(): void {
    this.router.navigate(['/dashboard']);
  }

  /** Load findings from GET /review/{app_id}/results when step 5 is shown. */
  loadFindings(): void {
    const appId = this.record?.permitId;
    if (!appId) return;
    this.complianceFindingsLoading = true;
    this.complianceFindingsError = '';
    this.applicationsApi.getReviewResults(appId).subscribe({
      next: (res) => {
        this.complianceFindingsLoading = false;
        const raw = res.findings ?? res.all_findings ?? [];
        this.complianceFindings = raw.map((f: ReviewStreamFinding) => this.mapFindingToDisplay(f));
      },
      error: (err) => {
        this.complianceFindingsLoading = false;
        this.complianceFindingsError = err?.message ?? 'Failed to load findings.';
      },
    });
  }

  private mapFindingToDisplay(f: ReviewStreamFinding): { agent: string; findings: string; aiSuggestion: string; status: string } {
    const severity = (f.severity ?? '').toLowerCase();
    let status = 'Follow-up';
    if (severity === 'critical') status = 'Critical';
    else if (severity === 'warning') status = 'Warning';
    else if (severity === 'violation') status = 'Violation';
    return {
      agent: f.agent ?? '—',
      findings: f.finding ?? '',
      aiSuggestion: f.detail ?? '',
      status,
    };
  }

  getFindingStatusClass(status: string): string {
    return 'status-' + status.toLowerCase().replace(/\s+/g, '-');
  }

  getAgentDisplayName(agent: string): string {
    if (agent === 'Code') return 'Code Enforcement Agent';
    return agent;
  }

  getAgentImageUrl(agentKey: 'intake' | 'code' | 'planner' | 'inspector'): string {
    const map: Record<string, string> = {
      intake: 'assets/agents/Intake_Agent.png',
      code: 'assets/agents/Code_Enforcement_Agent.png',
      planner: 'assets/agents/Planning_Agent.png',
      inspector: 'assets/agents/Inspector_Agent.png',
    };
    return map[agentKey] ?? 'assets/agents/Intake_Agent.png';
  }

  /** Blueprint image from assets/images/blueprint. Uses record.blueprintFileName or default file. */
  getBlueprintImageUrl(): string {
    if (!this.record) return 'assets/images/blueprint/blueprint.png';
    const name = this.record.blueprintFileName?.trim();
    if (name) return `assets/images/blueprint/${name}`;
    return 'assets/images/blueprint/old_permit_modified 1.jpg';
  }

  /** Site image URLs from assets/images/site-images. Uses known filenames, limited by siteImagesCount. */
  getSiteImageUrls(): string[] {
    const files = ['front_view.png', 'back_view.png'];
    const count = this.record?.siteImagesCount;
    const n = typeof count === 'number' ? Math.min(Math.max(0, count), files.length) : files.length;
    return files.slice(0, n || files.length).map((f) => `assets/images/site-images/${f}`);
  }

  /** Enlarged image URL (blueprint or site); null when closed. */
  enlargedImageUrl: string | null = null;

  openImageEnlarged(url: string): void {
    this.enlargedImageUrl = url;
  }

  closeImageEnlarged(): void {
    this.enlargedImageUrl = null;
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.enlargedImageUrl) this.closeImageEnlarged();
  }
}
