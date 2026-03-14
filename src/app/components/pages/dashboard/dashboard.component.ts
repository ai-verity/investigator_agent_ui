import { Component, computed, signal, HostListener, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../services/auth.service';
import { ApplicationsApiService, ApplicationListItem, ReviewStreamFinding, getUserFriendlyErrorMessage } from '../../../services/applications-api.service';
import { MarkdownPipe } from '../../../pipes/markdown.pipe';
import { environment } from '../../../../environments/environment';

export interface Permit {
  permitId: string;
  address: string;
  type: string;
  zoningType: string;
  status: string;
}

export interface AdminRecord {
  /** Display ID (may be "—" when missing). */
  permitId: string;
  /** Real application id for API calls (review, inspector). Omit when missing so we never call APIs with "—". */
  applicationId?: string;
  applicant: string;
  address: string;
  status: string;
  /** Officer decision from API (approve, reject, revision, etc.). When empty, Officer Decision column shows "Review Pending". */
  officerDecision?: string;
  officer_comment?: string;
  /** ISO date-time when officer made the decision (from API). Shown as "Decision confirmed at" timestamp. */
  officerDecidedAt?: string;
  daysElapsed: number;
  permitType: string;
  zoningType: string;
  submittedDate: string;
  submittedTime: string;
  landAreaSqFt?: number;
  existingBuiltUpArea?: number;
  proposedBuiltUpArea?: number;
  noOfFloors?: number;
  proposedHeightFt?: number;
  allowedHeightFt?: number;
  imperviousCoverPct?: number;
  scopeOfWork?: string;
  blueprintFileName?: string;
  siteImagesCount?: number;
  /** When true, AI Decision shows Critical Violation and Officer Decision shows NA; Decision section is disabled. */
  hasCritical?: boolean;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, MarkdownPipe],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  title = 'Dashboard';

  // User view (existing)
  permits: Permit[] = [];
  userPermitsLoading = false;
  userPermitsError = '';

  // Admin view: list + detail (no filters for now)
  adminRecords: AdminRecord[] = [];
  adminRecordsLoading = false;
  adminRecordsError = '';
  /** Zoning type filter for admin list; empty = All */
  adminZoningFilter = '';
  /** Permit type filter for admin list; empty = All */
  adminPermitTypeFilter = '';

  selectedRecord = signal<AdminRecord | null>(null);
  otherDetailButtons = [
    // { label: 'Overview', index: 0 },
    { label: 'Scope', index: 1 },
    { label: 'Blueprint', index: 2 },
    { label: 'Images', index: 3 },
  ];
  activeDetailContent = signal<number>(-1); // -1=closed, 0=Overview, 1=Scope, 2=Blueprint, 3=Images

  /** Mock AI issues per permitId so AI Summary updates when switching records */
  private static readonly DETECTED_ISSUES_BY_PERMIT: Record<string, string[]> = {
    'BLR-001': [
      'Proposed height exceeds allowed by 0.8 ft',
      'Missing secondary fire exit',
      'Parking requirement short by 2 units',
      'Located in Floodplain Overlay',
    ],
    'BLR-002': [
      'Commercial fire egress width below code',
      'Accessibility ramp slope exceeds 1:12',
      'Façade material not in design guidelines',
    ],
    'BLR-003': [
      'Demolition debris disposal plan required',
      'Stormwater BMPs missing for rebuild phase',
      'Setback variance documentation incomplete',
    ],
    'BLR-004': [
      'Floodplain fill and grading permit needed',
      'Impervious cover variance not justified',
      'Industrial use compatibility review pending',
    ],
  };

  detectedIssues = computed(() => {
    const record = this.selectedRecord();
    if (!record?.permitId) return [];
    return DashboardComponent.DETECTED_ISSUES_BY_PERMIT[record.permitId] ?? [
      'No issues detected for this permit.',
    ];
  });

  /** AI findings from GET /review/{app_id}/results for the selected record (admin). */
  adminFindings: { agent: string; findings: string; aiSuggestion: string; status: string }[] = [];
  adminFindingsLoading = false;
  adminFindingsError = '';

  /** Image URLs from GET /review/{app_id}/images for selected record (admin). */
  adminReviewImagesLoading = false;
  adminBlueprintImageUrl: string | null = null;
  adminPhotoUrls: string[] = [];
  feedbackTooltip = 'This feedback will be used for finetuning our Agents.';
  feedbackModalOpen = signal<boolean>(false);
  feedbackText = '';
  feedbackSubmitting = false;
  feedbackError = '';
  officerComments = '';
  decisionChoice = signal<'approve' | 'reject' | 'revision' | null>(null);
  decisionComment = '';

  /** After Confirm Decision with Approve, show confirmation summary instead of form */
  decisionConfirmed = signal<boolean>(false);
  decisionConfirmedChoice = signal<'approve' | 'reject' | 'revision' | null>(null);
  decisionConfirmedAt = signal<Date | null>(null);
  /** Stored officer comment when confirming Request Revision (shown in REVISION DETAILS) */
  decisionRevisionComment = signal<string>('');
  decisionConfirmLoading = false;
  decisionConfirmError = '';

  siteImagesEnlarged = signal<number | null>(null); // 1-based index of image shown enlarged, null = none

  /** Enlarged image URL for admin blueprint/site images overlay; null when closed. */
  enlargedImageUrl: string | null = null;

  blueprintZoom = signal(1);
  blueprintPan = signal({ x: 0, y: 0 });
  blueprintDragging = false;
  private blueprintLastPan = { x: 0, y: 0 };
  private blueprintLastClient = { x: 0, y: 0 };

  constructor(
    public auth: AuthService,
    private router: Router,
    private applicationsApi: ApplicationsApiService,
  ) {}

  ngOnInit(): void {
    if (this.auth.currentRole === 'user') {
      this.loadUserApplications();
    } else if (this.auth.currentRole === 'admin') {
      this.loadAdminApplications();
    }
  }

  private loadAdminApplications(): void {
    this.adminRecordsLoading = true;
    this.adminRecordsError = '';
    this.selectedRecord.set(null);
    this.applicationsApi.listApplications().subscribe({
      next: (response: ApplicationListItem[] | Record<string, unknown>) => {
        this.adminRecordsLoading = false;
        let items: ApplicationListItem[] = Array.isArray(response) ? response : [];
        if (!items.length && response && typeof response === 'object' && !Array.isArray(response)) {
          const obj = response as Record<string, unknown>;
          if (Array.isArray(obj.data)) items = obj.data as ApplicationListItem[];
          else if (Array.isArray(obj.applications)) items = obj.applications as ApplicationListItem[];
          else {
            // Array-like response: { "0": {...}, "1": {...} } from some backends
            const values = Object.values(obj);
            if (values.length > 0 && values.every((v) => v && typeof v === 'object' && ('application_id' in v || 'app_id' in v || 'permit_id' in v))) {
              items = values as ApplicationListItem[];
            }
          }
        }
        this.adminRecords = (items || []).map((it) => this.mapListItemToAdminRecord(it));
        const filtered = this.filteredAdminRecords;
        if (filtered.length > 0) {
          this.selectedRecord.set(filtered[0]);
          const appId = filtered[0].applicationId;
          if (appId) {
            this.loadAdminFindings(appId);
            this.loadAdminReviewImages(appId);
          }
        }
      },
      error: (err) => {
        console.error('Admin list applications failed:', err);
        this.adminRecordsLoading = false;
        this.adminRecordsError = getUserFriendlyErrorMessage(err, 'Unable to load applications. Please try again.');
      },
    });
  }

  private mapListItemToAdminRecord(it: ApplicationListItem): AdminRecord {
    const toStr = (v: unknown) => (v === undefined || v === null ? '' : String(v));
    const rawId = it.application_id ?? it.app_id ?? it.permit_id;
    const applicationId = rawId != null && String(rawId).trim() !== '' ? String(rawId).trim() : undefined;
    const permitId = applicationId ?? '—';
    const officerDecision = toStr(it.officer_decision).trim();
    const workflow = toStr(it.status ?? it.application_status).trim();
    const combinedStatus = officerDecision || workflow || '—';
    const officerDecidedAt = it.officer_decided_at ? String(it.officer_decided_at).trim() : undefined;
    const hasCritical = it.has_critical === true || it.has_critical === 1;
    return {
      permitId,
      applicationId,
      applicant: toStr(it.owner_name) || '—',
      address: toStr(it.project_address ?? it.address) || '—',
      status: combinedStatus,
      officerDecision: officerDecision || undefined,
      officer_comment: it.officer_comment ? toStr(it.officer_comment) : undefined,
      officerDecidedAt: officerDecidedAt || undefined,
      daysElapsed: 0,
      permitType: toStr(it.application_type ?? it.permit_type) || '—',
      zoningType: toStr(it.zoning_type ?? it.zoningType) || '—',
      submittedDate: toStr(it.submitted_date ?? it.date) || '—',
      submittedTime: toStr(it.submitted_time) || '—',
      scopeOfWork: it.sow_text ? toStr(it.sow_text) : undefined,
      blueprintFileName: it.blueprint_file_name ? toStr(it.blueprint_file_name) : undefined,
      siteImagesCount: it.site_images_count != null ? Number(it.site_images_count) : undefined,
      hasCritical,
    };
  }

  private loadUserApplications(): void {
    this.userPermitsLoading = true;
    this.userPermitsError = '';
    this.applicationsApi.listApplications().subscribe({
      next: (response: ApplicationListItem[] | Record<string, unknown>) => {
        this.userPermitsLoading = false;
        let items: ApplicationListItem[] = Array.isArray(response) ? response : [];
        if (!items.length && response && typeof response === 'object' && !Array.isArray(response)) {
          const obj = response as Record<string, unknown>;
          if (Array.isArray(obj.data)) items = obj.data as ApplicationListItem[];
          else if (Array.isArray(obj.applications)) items = obj.applications as ApplicationListItem[];
          else {
            const values = Object.values(obj);
            if (values.length > 0 && values.every((v) => v && typeof v === 'object' && ('application_id' in v || 'app_id' in v || 'permit_id' in v))) {
              items = values as ApplicationListItem[];
            }
          }
        }
        const toStr = (v: unknown) => (v === undefined || v === null ? '' : String(v)).trim();
        this.permits = (items || []).map((it) => {
          // For user list, treat application_id as the primary Application ID.
          const rawId = it.application_id ?? it.app_id ?? it.permit_id;
          const applicationId = toStr(rawId) || '—';
          // Status: officer_decision first, then status, then application_status; never show empty.
          const status =
            toStr(it.officer_decision) ||
            toStr(it.status) ||
            toStr(it.application_status) ||
            '—';
          return {
            permitId: applicationId,
            address: toStr(it.project_address ?? it.address) || '—',
            type: toStr(it.application_type ?? it.permit_type) || '—',
            zoningType: toStr(it.zoning_type ?? it.zoningType) || '—',
            status,
          };
        });
      },
      error: (err) => {
        console.error('List applications failed:', err);
        this.userPermitsLoading = false;
        this.userPermitsError = getUserFriendlyErrorMessage(err, 'Unable to load applications. Please try again.');
      },
    });
  }

  get isAdmin(): boolean {
    return this.auth.currentRole === 'admin';
  }

  /** Fixed zoning type options for admin filter; first letter (of each word) capitalized in display. */
  private static readonly ZONING_OPTIONS = ['Residential', 'Commercial', 'Industrial', 'Mixed-Use', 'Civic/Public'] as const;

  /** Fixed permit type options for admin filter. */
  private static readonly PERMIT_TYPE_OPTIONS = ['New Construction', 'Remodel/ Alteration', 'Demolition'] as const;

  /** Zoning filter dropdown: All + fixed options. */
  get adminZoningFilterOptions(): { value: string; label: string }[] {
    return [
      { value: '', label: 'All' },
      ...DashboardComponent.ZONING_OPTIONS.map((v) => ({ value: v, label: v })),
    ];
  }

  /** Permit type filter dropdown: All + fixed options. */
  get adminPermitTypeFilterOptions(): { value: string; label: string }[] {
    return [
      { value: '', label: 'All' },
      ...DashboardComponent.PERMIT_TYPE_OPTIONS.map((v) => ({ value: v, label: v })),
    ];
  }

  /** Admin list filtered by zoning and permit type. Hide only pending; show everything else (regardless of officer_decision). */
  get filteredAdminRecords(): AdminRecord[] {
    let list = this.adminRecords.filter(
      (r) => (r.status ?? '').trim().toLowerCase() !== 'pending',
    );
    const z = this.adminZoningFilter.trim();
    if (z) {
      const lower = z.toLowerCase();
      list = list.filter((r) => (r.zoningType ?? '').trim().toLowerCase() === lower);
    }
    const p = this.adminPermitTypeFilter.trim();
    if (p) {
      const normFilter = this.normalizeForPermitFilter(p);
      list = list.filter((r) => this.normalizeForPermitFilter(r.permitType ?? '') === normFilter);
    }
    return list;
  }

  /** Normalize for permit type filter match: lowercase, trim, collapse spaces around slash. */
  private normalizeForPermitFilter(s: string): string {
    return (s ?? '').trim().toLowerCase().replace(/\s*\/\s*/g, '/');
  }

  /** Capitalize first letter of each word (e.g. "mixed-use" -> "Mixed-Use", "civic/public" -> "Civic/Public"). */
  capitalizeZoningType(value: string | undefined): string {
    if (value === undefined || value === null) return '—';
    const s = value.trim();
    if (!s) return '—';
    const lower = s.toLowerCase();
    return lower.replace(/(^|[\s/-])(\w)/g, (_, sep, c) => sep + c.toUpperCase());
  }

  /** Capitalize first letter of each word for permit type display. */
  capitalizePermitType(value: string | undefined): string {
    if (value === undefined || value === null) return '—';
    const s = value.trim();
    if (!s) return '—';
    const lower = s.toLowerCase();
    return lower.replace(/(^|[\s/-])(\w)/g, (_, sep, c) => sep + c.toUpperCase());
  }

  /** When zoning filter changes, keep selection in sync: if selected record is not in filtered list, select first filtered or null. */
  onAdminZoningFilterChange(value: string): void {
    this.adminZoningFilter = value;
    this.syncSelectionToFilteredList();
  }

  /** When permit type filter changes, keep selection in sync. */
  onAdminPermitTypeFilterChange(value: string): void {
    this.adminPermitTypeFilter = value;
    this.syncSelectionToFilteredList();
  }

  private syncSelectionToFilteredList(): void {
    const filtered = this.filteredAdminRecords;
    const current = this.selectedRecord();
    if (current && !filtered.some((r) => r.permitId === current.permitId)) {
      if (filtered.length > 0) {
        this.selectedRecord.set(filtered[0]);
        const appId = filtered[0].applicationId;
        if (appId) {
          this.loadAdminFindings(appId);
          this.loadAdminReviewImages(appId);
        }
      } else {
        this.selectedRecord.set(null);
        this.adminFindings = [];
        this.adminFindingsError = '';
        this.adminBlueprintImageUrl = null;
        this.adminPhotoUrls = [];
      }
    }
  }

  /**
   * AI Decision label for a record. When has_critical is true: "Critical Violation".
   * Otherwise maps status to Compliant / Non Compliant per officer/workflow rules.
   */
  getAiDecisionLabel(record: AdminRecord | { status?: string; hasCritical?: boolean } | string | undefined): string {
    if (record == null) return 'Compliant';
    if (typeof record === 'object' && (record as { hasCritical?: boolean }).hasCritical === true) return 'Critical Violation';
    const officerStatus = typeof record === 'string' ? record : (record as { status?: string }).status;
    if (officerStatus === undefined || officerStatus === null) return 'Compliant';
    const s = officerStatus.trim().toLowerCase();
    if (s === '' || s === 'pending' || s === 'review pending') return 'Compliant';
    if (s === 'submitted' || s === 'completed') return 'Compliant';
    if (s === 'na') return 'Critical Violation';
    if (s === 'approved' || s === 'approve') return 'Compliant';
    if (s === 'under review') return 'Compliant';
    if (s === 'requested for revision' || s === 'requested revision' || s === 'revision') return 'Non Compliant';
    if (s === 'rejected' || s === 'reject') return 'Non Compliant';
    if (s === 'complete') return 'Compliant';
    return 'Compliant';
  }

  /** Officer Decision column: show "NA" when has_critical (Critical Violation); "Review Pending" when empty; else officer decision. */
  getOfficerDecisionDisplay(record: AdminRecord | { status?: string; officerDecision?: string; hasCritical?: boolean } | null): string {
    if (!record) return 'Review Pending';
    if ((record as { hasCritical?: boolean }).hasCritical === true) return 'NA';
    if (this.getAiDecisionLabel(record) === 'Critical Violation') return 'NA';
    const raw = (record?.officerDecision ?? '').trim();
    if (!raw) return 'Review Pending';
    return this.capitalizeOfficerDecision(raw);
  }

  /** Capitalize first letter of Officer Decision for display (e.g. reject -> Reject, request revision -> Request Revision). */
  private capitalizeOfficerDecision(value: string): string {
    const v = value.trim();
    if (!v) return v;
    const lower = v.toLowerCase();
    if (lower === 'request revision') return 'Request Revision';
    if (lower === 'requested revision') return 'Requested Revision';
    if (lower === 'revision required') return 'Revision Required';
    return v.charAt(0).toUpperCase() + v.slice(1).toLowerCase();
  }

  /** True when the selected record has has_critical true (AI Decision = Critical Violation); disables the Decision section. */
  get isDecisionSectionDisabled(): boolean {
    const record = this.selectedRecord();
    return record ? (record.hasCritical === true || this.getAiDecisionLabel(record) === 'Critical Violation') : false;
  }

  /** True when the officer has already made a decision (from API or current session). Used to hide the decision form and show status/comment only. */
  hasOfficerDecided(record: { status?: string; officerDecision?: string } | null): boolean {
    if (!record) return false;
    const s = (record.officerDecision ?? record.status ?? '').trim().toLowerCase();
    return (
      s === 'approve' || s === 'approved' ||
      s === 'reject' || s === 'rejected' ||
      s === 'revision' || s === 'revision required' || s === 'request revision' || s === 'requested revision'
    );
  }

  /** Decision type for records that have already been decided (used to show the right summary in Decision section). */
  getOfficerDecisionType(record: { status?: string; officerDecision?: string } | null): 'approve' | 'reject' | 'revision' | null {
    if (!record) return null;
    const s = (record.officerDecision ?? record.status ?? '').trim().toLowerCase();
    if (s === 'approve' || s === 'approved') return 'approve';
    if (s === 'reject' || s === 'rejected') return 'reject';
    if (s === 'revision' || s === 'revision required' || s === 'request revision' || s === 'requested revision') return 'revision';
    return null;
  }

  /** Format submitted date/time for display (e.g. "Mar 9, 2026, 5:55 AM"). */
  formatSubmittedDateTime(dateStr?: string, timeStr?: string): string {
    const raw = (dateStr ?? '').trim() || (timeStr ?? '').trim();
    if (!raw) return '—';
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return dateStr ?? '—';
    const datePart = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const timePart = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    return `${datePart}, ${timePart}`;
  }

  /** Load image URLs from GET /review/{app_id}/images for selected record (admin). Uses application_id, never placeholder "—". */
  loadAdminReviewImages(applicationId: string): void {
    if (!applicationId || applicationId.trim() === '' || applicationId === '—') {
      this.adminReviewImagesLoading = false;
      this.adminBlueprintImageUrl = null;
      this.adminPhotoUrls = [];
      return;
    }
    const appId = applicationId.trim();
    this.adminReviewImagesLoading = true;
    this.adminBlueprintImageUrl = null;
    this.adminPhotoUrls = [];
    const base = (environment as { reviewStreamBaseUrl?: string }).reviewStreamBaseUrl || '';
    this.applicationsApi.getReviewImages(appId).subscribe({
      next: (res) => {
        this.adminReviewImagesLoading = false;
        const paths = res.images || [];
        const blueprintPath = paths.find((p) => p.includes('blueprint'));
        if (blueprintPath) {
          this.adminBlueprintImageUrl = blueprintPath.startsWith('http') ? blueprintPath : `${base.replace(/\/$/, '')}/${blueprintPath.replace(/^\//, '')}`;
        }
        this.adminPhotoUrls = paths
          .filter((p) => p.includes('photos'))
          .map((p) => (p.startsWith('http') ? p : `${base.replace(/\/$/, '')}/${p.replace(/^\//, '')}`));
      },
      error: () => {
        this.adminReviewImagesLoading = false;
      },
    });
  }

  /** Blueprint image from GET /review/{app_id}/images when available, else assets fallback (admin). */
  getBlueprintImageUrl(): string {
    if (this.adminBlueprintImageUrl) return this.adminBlueprintImageUrl;
    const record = this.selectedRecord();
    if (!record) return 'assets/images/blueprint/old_permit_modified 1.jpg';
    const name = record.blueprintFileName?.trim();
    if (name) return `assets/images/blueprint/${name}`;
    return 'assets/images/blueprint/old_permit_modified 1.jpg';
  }

  /** Site image URLs from GET /review/{app_id}/images when available, else assets fallback (admin). */
  getSiteImageUrls(): string[] {
    if (this.adminPhotoUrls.length > 0) return this.adminPhotoUrls;
    const files = ['front_view.png', 'back_view.png'];
    const record = this.selectedRecord();
    const count = record?.siteImagesCount;
    const n = typeof count === 'number' ? Math.min(Math.max(0, count), files.length) : files.length;
    return files.slice(0, n || files.length).map((f) => `assets/images/site-images/${f}`);
  }

  openImageEnlargedByUrl(url: string): void {
    this.enlargedImageUrl = url;
  }

  viewPermit(permit: Permit): void {
    console.log('View permit', permit.permitId);
  }

  selectRecord(record: AdminRecord): void {
    if (!record) return;
    this.selectedRecord.set({ ...record });
    const appId = record.applicationId;
    if (appId) {
      this.loadAdminFindings(appId);
      this.loadAdminReviewImages(appId);
    } else {
      this.adminFindings = [];
      this.adminFindingsError = '';
      this.adminFindingsLoading = false;
      this.adminBlueprintImageUrl = null;
      this.adminPhotoUrls = [];
    }
    this.activeDetailContent.set(-1);
    this.decisionConfirmed.set(false);
    this.decisionConfirmedChoice.set(null);
    this.decisionConfirmedAt.set(null);
    this.decisionRevisionComment.set('');
    this.officerComments = '';
    this.decisionChoice.set(null);
    this.decisionComment = '';
  }

  getRecordForPermitId(permitId: string): AdminRecord | undefined {
    return this.adminRecords.find(r => r.permitId === permitId);
  }

  /** Load AI findings from GET /review/{app_id}/results for the selected record (admin detail). Uses application_id, never placeholder "—". */
  loadAdminFindings(applicationId: string): void {
    if (!applicationId || applicationId.trim() === '' || applicationId === '—') {
      this.adminFindingsLoading = false;
      this.adminFindingsError = '';
      this.adminFindings = [];
      return;
    }
    const appId = applicationId.trim();
    this.adminFindingsLoading = true;
    this.adminFindingsError = '';
    this.adminFindings = [];
    this.applicationsApi.getReviewResults(appId).subscribe({
      next: (res) => {
        this.adminFindingsLoading = false;
        const raw = res.findings ?? res.all_findings ?? [];
        this.adminFindings = raw.map((f: ReviewStreamFinding) => this.mapFindingToDisplay(f));
      },
      error: (err: unknown) => {
        this.adminFindingsLoading = false;
        const status = (err as { status?: number; error?: { status?: number } })?.status ?? (err as { error?: { status?: number } })?.error?.status;
        if (status === 404) {
          this.adminFindings = [];
          this.adminFindingsError = '';
        } else {
          this.adminFindingsError = getUserFriendlyErrorMessage(err, 'Unable to load AI findings. Please try again.');
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

  getAgentDisplayName(agent: string): string {
    if (agent === 'Code') return 'Code Enforcement Agent';
    return agent;
  }

  getFindingStatusClass(status: string): string {
    return 'status-' + status.toLowerCase().replace(/\s+/g, '-');
  }

  /** AI findings with Critical severity, for Rejection Summary list. */
  get criticalFindings(): { agent: string; findings: string; aiSuggestion: string; status: string }[] {
    return this.adminFindings.filter((f) => (f.status ?? '').toLowerCase() === 'critical');
  }

  selectPermitAsUser(permit: Permit): void {
    const appId = permit.permitId;
    this.router.navigate(['/view-application'], { state: { appId } });
  }

  /** True when the citizen can edit this application (pending or revision required). */
  canEditPermit(permit: Permit): boolean {
    console.log("Permit===>", permit)
    const s = (permit?.status ?? '').trim().toLowerCase();
    return (
      s === 'pending' ||
      s === 'pending for submission' ||
      s.startsWith('pending') ||
      s === 'review pending' ||
      s === 'revision required' ||
      s === 'requested revision'
    );
  }

  /** Navigate to applications page in edit mode for the given permit. */
  editApplicationAsUser(permit: Permit): void {
    if (!permit?.permitId) return;
    this.router.navigate(['/applications'], { queryParams: { edit: permit.permitId } });
  }

  clearUserSelection(): void {
    this.selectedRecord.set(null);
    this.siteImagesEnlarged.set(null);
  }

  setDetailContent(index: number): void {
    if (this.activeDetailContent() === index) {
      this.activeDetailContent.set(-1);
    } else {
      this.activeDetailContent.set(index);
    }
  }

  closeDynamicPanel(): void {
    this.activeDetailContent.set(-1);
    this.siteImagesEnlarged.set(null);
  }

  /** Generate permit_id for approved applications, e.g. ATX-2026-1020. */
  private generatePermitId(appId: string): string {
    const year = new Date().getFullYear();
    const suffix = appId.slice(-4);
    const num = /^\d{4}$/.test(suffix) ? suffix : String(1000 + Math.abs(this.hashCode(suffix) % 9000));
    return `ATX-${year}-${num}`;
  }

  private hashCode(s: string): number {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
    return h;
  }

  confirmDecision(): void {
    const choice = this.decisionChoice();
    const record = this.selectedRecord();
    const appId = record?.applicationId ?? record?.permitId;
    if (!choice || !record || !appId || appId === '—' || appId.trim() === '') return;

    this.decisionConfirmError = '';
    this.decisionConfirmLoading = true;
    const comment = choice === 'revision' || choice === 'reject' ? (this.decisionComment || '').trim() : '';
    const officerDecidedAt = new Date().toISOString();

    let officerDecisionValue: string;
    let officerComment: string | null;
    let permitId: string | null;

    if (choice === 'approve') {
      officerDecisionValue = 'approve';
      officerComment = null;
      permitId = this.generatePermitId(appId.trim());
    } else if (choice === 'revision') {
      officerDecisionValue = 'revision required';
      officerComment = comment || null;
      permitId = null;
    } else {
      officerDecisionValue = 'reject';
      officerComment = comment || null;
      permitId = null;
    }

    this.applicationsApi.submitOfficerDecision(appId.trim(), {
      officer_decision: officerDecisionValue,
      officer_comment: officerComment ?? '',
      permit_id: permitId ?? '',
      officer_decided_at: officerDecidedAt,
    }).subscribe({
      next: () => {
        this.decisionConfirmLoading = false;
        this.decisionConfirmed.set(true);
        this.decisionConfirmedChoice.set(choice);
        this.decisionConfirmedAt.set(new Date());
        if (choice === 'revision' || choice === 'reject') {
          this.decisionRevisionComment.set(this.decisionComment || '');
        }
        const statusMap = { approve: 'Approved', reject: 'Rejected', revision: 'Requested Revision' } as const;
        record.status = statusMap[choice];
        record.officerDecision = officerDecisionValue;
        record.officerDecidedAt = officerDecidedAt;
        const idx = this.adminRecords.findIndex((r) => r.permitId === record.permitId);
        if (idx !== -1) this.adminRecords[idx] = { ...this.adminRecords[idx], status: record.status, officerDecision: officerDecisionValue, officerDecidedAt };
      },
      error: (err: unknown) => {
        this.decisionConfirmLoading = false;
        this.decisionConfirmError = getUserFriendlyErrorMessage(err, 'Unable to submit decision. Please try again.');
      },
    });
  }

  getDecisionConfirmedTimestamp(): string {
    const d = this.decisionConfirmedAt();
    if (d) return this.formatDecisionTimestamp(d);
    const record = this.selectedRecord();
    const iso = record?.officerDecidedAt?.trim();
    if (iso) {
      const d2 = new Date(iso);
      if (!Number.isNaN(d2.getTime())) return this.formatDecisionTimestamp(d2);
    }
    return '';
  }

  private formatDecisionTimestamp(d: Date): string {
    const datePart = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const h = d.getHours();
    const m = d.getMinutes();
    const timeStr = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
    return `${datePart} - ${timeStr}`;
  }

  /** Format officer_decided_at for display in list or detail. Returns empty string when not set. */
  formatOfficerDecidedAt(record: { officerDecidedAt?: string } | null): string {
    const iso = record?.officerDecidedAt?.trim();
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return this.formatDecisionTimestamp(d);
  }

  openImageEnlarged(index: number): void {
    this.siteImagesEnlarged.set(index);
  }

  closeImageEnlarged(): void {
    this.siteImagesEnlarged.set(null);
    this.enlargedImageUrl = null;
  }

  downloadAnalysis(): void {
    console.log('Download analysis');
  }

  blueprintZoomIn(): void {
    this.blueprintZoom.update(z => Math.min(z + 0.25, 3));
  }

  blueprintZoomOut(): void {
    this.blueprintZoom.update(z => Math.max(z - 0.25, 0.5));
  }

  blueprintZoomReset(): void {
    this.blueprintZoom.set(1);
    this.blueprintPan.set({ x: 0, y: 0 });
  }

  getBlueprintTransform(): string {
    const zoom = this.blueprintZoom();
    const pan = this.blueprintPan();
    // Divide pan by zoom so drag moves in screen pixels even when zoomed.
    const dx = pan.x / (zoom || 1);
    const dy = pan.y / (zoom || 1);
    return `translate(${dx}px, ${dy}px) scale(${zoom})`;
  }

  onBlueprintMouseDown(event: MouseEvent): void {
    // Only allow panning when zoomed in.
    if (this.blueprintZoom() <= 1) return;
    this.blueprintDragging = true;
    this.blueprintLastClient = { x: event.clientX, y: event.clientY };
    this.blueprintLastPan = { ...this.blueprintPan() };
  }

  onBlueprintMouseMove(event: MouseEvent): void {
    if (!this.blueprintDragging || this.blueprintZoom() <= 1) return;
    const dx = event.clientX - this.blueprintLastClient.x;
    const dy = event.clientY - this.blueprintLastClient.y;
    this.blueprintLastClient = { x: event.clientX, y: event.clientY };
    const pan = this.blueprintPan();
    this.blueprintPan.set({
      x: pan.x + dx,
      y: pan.y + dy,
    });
  }

  onBlueprintMouseUp(): void {
    this.blueprintDragging = false;
  }

  @HostListener('window:mousemove', ['$event'])
  onWindowMouseMove(event: MouseEvent): void {
    if (this.blueprintDragging) this.onBlueprintMouseMove(event);
  }

  @HostListener('window:mouseup')
  onWindowMouseUp(): void {
    if (this.blueprintDragging) this.onBlueprintMouseUp();
  }

  @HostListener('document:keydown.escape')
  onEscapeKey(): void {
    if (this.enlargedImageUrl) this.closeImageEnlarged();
  }

  openFeedbackModal(): void {
    this.feedbackModalOpen.set(true);
  }

  closeFeedbackModal(): void {
    this.feedbackModalOpen.set(false);
    this.feedbackText = '';
    this.feedbackSubmitting = false;
    this.feedbackError = '';
  }

  submitFeedback(): void {
    const text = (this.feedbackText || '').trim();
    const record = this.selectedRecord();
    const appId = record?.applicationId ?? record?.permitId;
    if (!appId || appId === '—' || appId.trim() === '' || !text) {
      return;
    }
    this.feedbackSubmitting = true;
    this.feedbackError = '';
    this.applicationsApi.submitInspectorFeedback(appId.trim(), { comment: text }).subscribe({
      next: () => {
        this.feedbackSubmitting = false;
        this.closeFeedbackModal();
      },
      error: (err: unknown) => {
        this.feedbackSubmitting = false;
        this.feedbackError = getUserFriendlyErrorMessage(err, 'Unable to submit feedback. Please try again.');
      },
    });
  }

  getStatusClass(status: string): string {
    return 'status-' + status.toLowerCase().replace(/\s+/g, '-');
  }

  /** Format application status for user list. Never return empty. Approve -> Approved; Reject -> Rejected; complete -> Completed; etc. */
  formatApplicationStatus(status: string): string {
    const s = (status ?? '').trim();
    if (!s) return '—';
    const lower = s.toLowerCase();
    if (lower === 'pending') return 'Pending for Submission';
    if (lower === 'approve' || lower === 'approved') return 'Approved';
    if (lower === 'reject' || lower === 'rejected') return 'Rejected';
    if (lower === 'complete' || lower === 'completed') return 'Completed';
    if (lower === 'submitted') return 'Submitted';
    return s
      .split(/\s+/)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join(' ');
  }
}
