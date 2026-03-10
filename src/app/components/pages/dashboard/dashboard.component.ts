import { Component, computed, signal, HostListener, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../services/auth.service';
import { ApplicationsApiService, ApplicationListItem } from '../../../services/applications-api.service';
import { MarkdownPipe } from '../../../pipes/markdown.pipe';

export interface Permit {
  permitId: string;
  address: string;
  type: string;
  zoningType: string;
  status: string;
}

export interface AdminRecord {
  permitId: string;
  applicant: string;
  address: string;
  status: string;
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
  feedbackTooltip = 'This feedback will be used for finetuning our Agents.';
  feedbackModalOpen = signal<boolean>(false);
  feedbackText = '';
  officerComments = '';
  decisionChoice = signal<'approve' | 'reject' | 'revision' | null>(null);
  decisionComment = '';

  /** After Confirm Decision with Approve, show confirmation summary instead of form */
  decisionConfirmed = signal<boolean>(false);
  decisionConfirmedChoice = signal<'approve' | 'reject' | 'revision' | null>(null);
  decisionConfirmedAt = signal<Date | null>(null);
  /** Stored officer comment when confirming Request Revision (shown in REVISION DETAILS) */
  decisionRevisionComment = signal<string>('');

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
        if (this.adminRecords.length > 0) {
          this.selectedRecord.set(this.adminRecords[0]);
        }
      },
      error: (err) => {
        console.error('Admin list applications failed:', err);
        this.adminRecordsLoading = false;
        const statusVal = err?.status;
        const status =
          statusVal === 0 || typeof statusVal === 'number'
            ? ` (HTTP ${statusVal}${err?.statusText ? ` ${err.statusText}` : ''})`
            : '';
        this.adminRecordsError = `Failed to load applications${status}`;
      },
    });
  }

  private mapListItemToAdminRecord(it: ApplicationListItem): AdminRecord {
    const toStr = (v: unknown) => (v === undefined || v === null ? '' : String(v));
    const permitId = toStr(it.permit_id ?? it.application_id ?? it.app_id) || '—';
    return {
      permitId,
      applicant: toStr(it.owner_name) || '—',
      address: toStr(it.project_address ?? it.address) || '—',
      status: toStr(it.status ?? it.application_status) || '—',
      daysElapsed: 0,
      permitType: toStr(it.application_type ?? it.permit_type) || '—',
      zoningType: toStr(it.zoning_type ?? it.zoningType) || '—',
      submittedDate: toStr(it.submitted_date ?? it.date) || '—',
      submittedTime: toStr(it.submitted_time) || '—',
      scopeOfWork: it.sow_text ? toStr(it.sow_text) : undefined,
      blueprintFileName: it.blueprint_file_name ? toStr(it.blueprint_file_name) : undefined,
      siteImagesCount: it.site_images_count != null ? Number(it.site_images_count) : undefined,
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
        const toStr = (v: unknown) => (v === undefined || v === null ? '' : String(v));
        this.permits = (items || []).map((it) => ({
          permitId: toStr(it.permit_id ?? it.application_id ?? it.app_id) || '—',
          address: toStr(it.project_address ?? it.address) || '—',
          type: toStr(it.application_type ?? it.permit_type) || '—',
          zoningType: toStr(it.zoning_type ?? it.zoningType) || '—',
          status: toStr(it.status ?? it.application_status) || '—',
        }));
      },
      error: (err) => {
        console.error('List applications failed:', err);
        this.userPermitsLoading = false;
        const statusVal = err?.status;
        const status =
          statusVal === 0 || typeof statusVal === 'number'
            ? ` (HTTP ${statusVal}${err?.statusText ? ` ${err.statusText}` : ''})`
            : '';
        this.userPermitsError = `Failed to load applications${status}`;
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

  /** Admin list filtered by zoning and permit type (case-insensitive match). */
  get filteredAdminRecords(): AdminRecord[] {
    let list = this.adminRecords;
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
      this.selectedRecord.set(filtered.length > 0 ? filtered[0] : null);
    }
  }

  /**
   * Map Officer Decision (status) to AI Decision per the rules:
   * NA → Critical Violation; Approved → Compliant; Under Review → Compliant;
   * Requested for Revision / Rejected → Non Compliant.
   */
  getAiDecisionLabel(officerStatus: string | undefined): string {
    if (officerStatus === undefined || officerStatus === null) return 'Critical Violation';
    const s = officerStatus.trim().toLowerCase();
    if (s === '' || s === 'na' || s === 'pending') return 'Critical Violation';
    if (s === 'approved' || s === 'approve') return 'Compliant';
    if (s === 'under review') return 'Compliant';
    if (s === 'requested for revision' || s === 'requested revision' || s === 'revision') return 'Non Compliant';
    if (s === 'rejected' || s === 'reject') return 'Non Compliant';
    if (s === 'complete') return 'Compliant'; // treat complete as compliant for display
    return 'Critical Violation';
  }

  /** When AI Decision is Critical Violation, show Officer Decision as "Not Applicable". */
  getOfficerDecisionDisplay(record: { status?: string }): string {
    if (this.getAiDecisionLabel(record?.status) === 'Critical Violation') return 'Not Applicable';
    return (record?.status ?? '').trim() || '—';
  }

  /** True when the selected record has AI Decision = Critical Violation; disables the Decision section. */
  get isDecisionSectionDisabled(): boolean {
    const record = this.selectedRecord();
    return record ? this.getAiDecisionLabel(record.status) === 'Critical Violation' : false;
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

  /** Blueprint image from assets/images/blueprint for selected record (admin). */
  getBlueprintImageUrl(): string {
    const record = this.selectedRecord();
    if (!record) return 'assets/images/blueprint/old_permit_modified 1.jpg';
    const name = record.blueprintFileName?.trim();
    if (name) return `assets/images/blueprint/${name}`;
    return 'assets/images/blueprint/old_permit_modified 1.jpg';
  }

  /** Site image URLs from assets/images/site-images for selected record (admin). */
  getSiteImageUrls(): string[] {
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

  selectPermitAsUser(permit: Permit): void {
    const appId = permit.permitId;
    this.router.navigate(['/view-application'], { state: { appId } });
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

  confirmDecision(): void {
    const choice = this.decisionChoice();
    if (choice) {
      console.log('Decision confirmed:', choice, this.decisionComment || '');
      this.decisionConfirmed.set(true);
      this.decisionConfirmedChoice.set(choice);
      this.decisionConfirmedAt.set(new Date());
      if (choice === 'revision' || choice === 'reject') {
        this.decisionRevisionComment.set(this.decisionComment || '');
      }
      // Update selected record status so list and AI Decision reflect officer decision
      const record = this.selectedRecord();
      if (record) {
        const statusMap = { approve: 'Approved', reject: 'Rejected', revision: 'Requested Revision' } as const;
        record.status = statusMap[choice];
        const idx = this.adminRecords.findIndex((r) => r.permitId === record.permitId);
        if (idx !== -1) this.adminRecords[idx] = { ...this.adminRecords[idx], status: record.status };
      }
    }
  }

  getDecisionConfirmedTimestamp(): string {
    const d = this.decisionConfirmedAt();
    if (!d) return '';
    const datePart = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const h = d.getHours();
    const m = d.getMinutes();
    const timeStr = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
    const tz = d.toLocaleTimeString('en-US', { timeZoneName: 'short' }).split(' ').pop() ?? 'CST';
    return `${datePart} - ${timeStr} ${tz}`;
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
  }

  submitFeedback(): void {
    // Placeholder: send feedback to API for finetuning
    console.log('Feedback submitted:', this.feedbackText);
    this.closeFeedbackModal();
  }

  getStatusClass(status: string): string {
    return 'status-' + status.toLowerCase().replace(/\s+/g, '-');
  }
}
