import { Component, OnInit, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { jsPDF } from 'jspdf';
import { ApplicationsApiService, ApplicationDetail, ReviewStreamFinding, getUserFriendlyErrorMessage } from '../../../services/applications-api.service';
import { MarkdownPipe } from '../../../pipes/markdown.pipe';
import { environment } from '../../../../environments/environment';

/** Record data for view application page – all values from API, no hardcoding. */
export interface ViewApplicationRecord {
  feedback?: string;
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
  inspector_status?: string;
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
  /** Step 4 (AI Agents at Work) skipped for user view – only 5 steps shown. */
  steps = [1, 2, 3, 5, 6];

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

  /** Image URLs from GET /review/{app_id}/images (full URLs for blueprint and photos). */
  reviewImagesLoading = false;
  blueprintImageUrl: string | null = null;
  photoUrls: string[] = [];

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
          this.loadReviewImages();
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
      this.loadReviewImages();
    }
  }

  /** Load blueprint and photo URLs from GET /review/{app_id}/images. */
  loadReviewImages(): void {
    const appId = this.record?.permitId;
    if (!appId) {
      this.blueprintImageUrl = null;
      this.photoUrls = [];
      return;
    }
    this.reviewImagesLoading = true;
    this.blueprintImageUrl = null;
    this.photoUrls = [];
    const base = (environment as { reviewStreamBaseUrl?: string }).reviewStreamBaseUrl || '';
    this.applicationsApi.getReviewImages(appId).subscribe({
      next: (res: { images?: string[] }) => {
        this.reviewImagesLoading = false;
        const paths = res.images || [];
        const blueprintPath = paths.find((p: string) => p.includes('blueprint'));
        if (blueprintPath) {
          this.blueprintImageUrl = blueprintPath.startsWith('http') ? blueprintPath : `${base.replace(/\/$/, '')}/${blueprintPath.replace(/^\//, '')}`;
        }
        this.photoUrls = paths
          .filter((p: string) => p.includes('photos'))
          .map((p: string) => (p.startsWith('http') ? p : `${base.replace(/\/$/, '')}/${p.replace(/^\//, '')}`));
      },
      error: () => {
        this.reviewImagesLoading = false;
      },
    });
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
    const officer = opt(item.officer_decision);
    const workflow = opt(item.status);
    return {
      feedback: opt(item.feedback),
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
      status: officer ?? workflow,
      signatureFileName: opt(item.signature_file_name),
      blueprintFileName: opt(item.blueprint_file_name),
      siteImagesCount: toNum(item.site_images_count),
      inspector_status: opt(item.inspector_status),
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

  /** Format status for display in View Application (e.g. approve → Approved, reject → Rejected). */
  formatApplicationStatus(status: string | undefined): string {
    const s = (status ?? '').trim();
    if (!s) return '—';
    const lower = s.toLowerCase();
    if (lower === 'approve' || lower === 'approved') return 'Approved';
    if (lower === 'reject' || lower === 'rejected') return 'Rejected';
    if (lower === 'revision required' || lower === 'revision') return 'Revision Required';
    if (lower === 'pending') return 'Pending';
    if (lower === 'completed') return 'Completed';
    if (lower === 'submitted') return 'Submitted';
    return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
  }

  goToStep(step: number): void {
    if (step >= 1 && step <= this.totalSteps && this.steps.includes(step)) {
      this.currentStep = step;
      if (this.record && (step === 5 || step === 6)) this.loadFindings();
    }
  }

  goToNextStep(): void {
    if (this.currentStep === 3) {
      this.currentStep = 5; // skip step 4 (AI Agents at Work)
    } else if (this.currentStep < this.totalSteps) {
      this.currentStep++;
    }
    if (this.currentStep === 5 && this.record) this.loadFindings();
  }

  returnToDashboard(): void {
    this.router.navigate(['/dashboard']);
  }

  /** True when the application has been approved by an inspector (inspector_status or status/officer_decision is approve(d)). */
  get isOfficerApproved(): boolean {
    const inspector = (this.record?.inspector_status ?? '').trim().toLowerCase();
    if (inspector === 'approved' || inspector === 'approve') return true;
    const status = (this.record?.status ?? '').trim().toLowerCase();
    return status === 'approved' || status === 'approve';
  }

  /** Infer permit city for PDF template: 'newyork' if address suggests NYC, else 'austin'. */
  getPermitCity(): 'austin' | 'newyork' {
    const addr = (this.record?.address ?? '').toLowerCase();
    if (/new york|newyork|nyc|brooklyn|manhattan|queens|bronx|staten island|, ny\b/.test(addr)) return 'newyork';
    return 'austin';
  }

  /** Generate and download approval PDF (Austin or New York template) when officer has approved. */
  downloadApprovalPdf(): void {
    if (!this.record || !this.isOfficerApproved) return;
    const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    const city = this.getPermitCity();
    const approvalDate = this.formatSubmissionDateForPdf(this.record.submittedDate);
    const permitExpiry = this.formatDateForPdf(new Date(Date.now() + 365 * 24 * 60 * 60 * 1000));

    if (city === 'austin') {
      doc.setFontSize(18);
      doc.setTextColor(0, 51, 102);
      doc.text('City of Austin – Building Permit Approval Certificate', 20, 22);
      doc.setDrawColor(0, 51, 102);
      doc.setLineWidth(0.5);
      doc.line(20, 26, 190, 26);
      doc.setFontSize(10);
      doc.setTextColor(0, 0, 0);
      const rows: [string, string][] = [
        ['City', 'Austin, Texas'],
        ['Department', 'Development Services Department'],
        ['Permit Number', `ATX-BLD-2026-${(this.record.permitId || 'XXXX').slice(-4)}`],
        ['Application ID', this.record.permitId || 'PA-XXXXXX'],
        ['Approval Date', approvalDate],
        ['Applicant Name', this.record.applicant || '[Applicant Name]'],
        ['Property Owner', this.record.applicant || '[Owner Name]'],
        ['Project Address', this.record.address || '[Street Address, Austin, TX ZIP]'],
        ['Zoning Classification', this.record.zoningType || '[Residential / Commercial / Mixed Use]'],
        ['Property ID', this.record.permitId || '[Parcel ID]'],
        ['Approved Scope of Work', (this.record.scopeOfWork as string)?.slice(0, 80) || 'Construction of a residential/commercial structure per approved plans'],
        ['Compliance Codes', 'Austin Land Development Code, IRC, IBC'],
        ['Required Inspections', 'Foundation, Framing, Electrical, Plumbing, Final Inspection'],
        ['Permit Expiration', permitExpiry],
        ['Authorized Officer', '[City Permit Officer]'],
      ];
      this.addFieldDetailsTable(doc, rows, 30);
      doc.setFontSize(9);
      doc.text('This permit must be displayed at the construction site during the entire duration of work.', 20, 272);
      doc.save(`Austin-Building-Permit-${this.record.permitId || 'approval'}.pdf`);
    } else {
      doc.setFontSize(18);
      doc.setTextColor(0, 51, 102);
      doc.text('City of New York – Construction Permit Approval Notice', 20, 22);
      doc.setDrawColor(0, 51, 102);
      doc.setLineWidth(0.5);
      doc.line(20, 26, 190, 26);
      doc.setFontSize(10);
      doc.setTextColor(0, 0, 0);
      const rows: [string, string][] = [
        ['City', 'New York City'],
        ['Department', 'Department of Buildings'],
        ['Permit Number', `NYC-DOB-2026-${(this.record.permitId || 'XXXX').slice(-4)}`],
        ['Application Number', this.record.permitId || 'BIS-XXXXXX'],
        ['Approval Date', approvalDate],
        ['Applicant / Contractor', this.record.applicant || '[Applicant Name]'],
        ['Licensed Professional', '[Architect / Engineer Name]'],
        ['Project Address', this.record.address || '[Street Address, Borough, NY ZIP]'],
        ['Borough', '[Manhattan / Brooklyn / Queens / Bronx / Staten Island]'],
        ['Block / Lot Number', (this.record.permitId || 'XXXXX').slice(0, 5)],
        ['Approved Work Type', this.record.permitType || 'Construction / Alteration / Addition'],
        ['Scope of Work', (this.record.scopeOfWork as string)?.slice(0, 60) || 'Construction as per approved architectural plans'],
        ['Compliance Codes', 'NYC Building Code, NYC Zoning Resolution, Fire Code'],
        ['Required Inspections', 'Structural, Electrical, Plumbing, Fire Safety, Final Inspection'],
        ['Permit Validity', permitExpiry],
        ['Authorized Officer', '[DOB Plan Examiner]'],
      ];
      this.addFieldDetailsTable(doc, rows, 30);
      doc.setFontSize(9);
      doc.text('This permit must be displayed at the construction site during the entire duration of work.', 20, 272);
      doc.save(`NYC-Construction-Permit-${this.record.permitId || 'approval'}.pdf`);
    }
  }

  private formatDateForPdf(d: Date): string {
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const y = d.getFullYear();
    return `${m}/${day}/${y}`;
  }

  private formatSubmissionDateForPdf(value: string | undefined): string {
    if (!value || !value.trim()) return this.formatDateForPdf(new Date());
    const d = new Date(value);
    if (!Number.isNaN(d.getTime())) return this.formatDateForPdf(d);
    return value;
  }

  private addFieldDetailsTable(doc: jsPDF, rows: [string, string][], startY: number): void {
    const col1 = 20;
    const col2 = 70;
    const lineHeight = 7;
    doc.setFont('helvetica', 'bold');
    doc.text('Field', col1, startY);
    doc.text('Details', col2, startY);
    doc.setFont('helvetica', 'normal');
    let y = startY + lineHeight;
    for (const [field, detail] of rows) {
      if (y > 270) { doc.addPage(); y = 20; }
      doc.text(field, col1, y);
      doc.text(detail.length > 50 ? detail.slice(0, 47) + '...' : detail, col2, y);
      y += lineHeight;
    }
  }

  loadFindings(): void {
    const appId = (this.record?.permitId ?? '').trim();
    if (!appId || appId === '—') return;
    this.complianceFindingsLoading = true;
    this.complianceFindingsError = '';
    this.applicationsApi.getReviewResults(appId).subscribe({
      next: (res: { findings?: ReviewStreamFinding[]; all_findings?: ReviewStreamFinding[] }) => {
        this.complianceFindingsLoading = false;
        const raw = res.findings ?? res.all_findings ?? [];
        this.complianceFindings = raw.map((f: ReviewStreamFinding) => this.mapFindingToDisplay(f));
      },
      error: (err: unknown) => {
        this.complianceFindingsLoading = false;
        const status = (err as { status?: number; error?: { status?: number } })?.status ?? (err as { error?: { status?: number } })?.error?.status;
        if (status === 404) {
          this.complianceFindings = [];
          this.complianceFindingsError = '';
        } else {
          this.complianceFindingsError = getUserFriendlyErrorMessage(err, 'Unable to load findings. Please try again.');
        }
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

  /** True when at least one finding has Critical severity (from findings endpoint). Hides PDF download in step 6. */
  get hasCriticalSeverity(): boolean {
    return this.complianceFindings.some((f) => (f.status ?? '').toLowerCase() === 'critical');
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

  /** Blueprint image: from GET /review/{app_id}/images when available, else assets fallback. */
  getBlueprintImageUrl(): string {
    if (this.blueprintImageUrl) return this.blueprintImageUrl;
    if (!this.record) return 'assets/images/blueprint/blueprint.png';
    const name = this.record.blueprintFileName?.trim();
    if (name) return `assets/images/blueprint/${name}`;
    return 'assets/images/blueprint/old_permit_modified 1.jpg';
  }

  /** Site image URLs: from GET /review/{app_id}/images when available, else assets fallback. */
  getSiteImageUrls(): string[] {
    if (this.photoUrls.length > 0) return this.photoUrls;
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
