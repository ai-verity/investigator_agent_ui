import { Component, computed, signal, HostListener, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../services/auth.service';
import { ApplicationsApiService, ApplicationListItem } from '../../../services/applications-api.service';

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
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  title = 'Dashboard';

  // User view (existing)
  permits: Permit[] = [];
  userPermitsLoading = false;
  userPermitsError = '';

  // Admin view: filters + list + detail (loaded from list applications API)
  filterPermitType = signal<string>('');
  filterZoningType = signal<string>('');
  adminRecords: AdminRecord[] = [];
  adminRecordsLoading = false;
  adminRecordsError = '';

  selectedRecord = signal<AdminRecord | null>(null);
  otherDetailButtons = [
    { label: 'Overview', index: 0 },
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

  blueprintZoom = signal(1);
  blueprintPan = signal({ x: 0, y: 0 });
  blueprintDragging = false;
  private blueprintLastPan = { x: 0, y: 0 };
  private blueprintLastClient = { x: 0, y: 0 };

  permitTypeOptions = ['', 'New Construction', 'Remodel/Alteration', 'Demolition'];
  zoningTypeOptions = ['', 'Residential', 'Commercial', 'Industrial', 'Mixed-Use', 'Civic/Public'];

  filteredRecords = computed(() => {
    let permitType = (this.filterPermitType() || '').trim();
    let zoningType = (this.filterZoningType() || '').trim();
    if (permitType.toLowerCase() === 'all') permitType = '';
    if (zoningType.toLowerCase() === 'all') zoningType = '';
    return this.adminRecords.filter((r) => {
      if (permitType && this.normalizeForFilter(r.permitType) !== this.normalizeForFilter(permitType)) return false;
      if (zoningType && this.normalizeForFilter(r.zoningType) !== this.normalizeForFilter(zoningType)) return false;
      return true;
    });
  });

  /** Case-insensitive normalize for filter comparison; map API values to dropdown option values. */
  private normalizeForFilter(value: string | undefined): string {
    if (value === undefined || value === null) return '';
    const v = String(value).trim().toLowerCase();
    const permitMap: Record<string, string> = {
      new: 'new construction',
      'new construction': 'new construction',
      remodel: 'remodel/alteration',
      alteration: 'remodel/alteration',
      'remodel/alteration': 'remodel/alteration',
      demolition: 'demolition',
    };
    const zoningMap: Record<string, string> = {
      residential: 'residential',
      commercial: 'commercial',
      industrial: 'industrial',
      'mixed-use': 'mixed-use',
      'mixed use': 'mixed-use',
      'civic/public': 'civic/public',
      civic: 'civic/public',
      public: 'civic/public',
    };
    const p = permitMap[v];
    if (p) return p;
    const z = zoningMap[v];
    if (z) return z;
    return v;
  }

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
    };
  }

  private loadUserApplications(): void {
    this.userPermitsLoading = true;
    this.userPermitsError = '';
    this.applicationsApi.listApplications().subscribe({
      next: (items: ApplicationListItem[]) => {
        this.userPermitsLoading = false;
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

  viewPermit(permit: Permit): void {
    console.log('View permit', permit.permitId);
  }

  selectRecord(record: AdminRecord): void {
    this.selectedRecord.set(record);
    this.activeDetailContent.set(-1); // no tab selected until user clicks one
    this.decisionConfirmed.set(false);
    this.decisionConfirmedChoice.set(null);
    this.decisionConfirmedAt.set(null);
    this.decisionRevisionComment.set('');
    // Reset form state so AI Analysis panel reflects the new record
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
      // Placeholder: submit to API
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
    return `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`;
  }

  onBlueprintMouseDown(event: MouseEvent): void {
    this.blueprintDragging = true;
    this.blueprintLastClient = { x: event.clientX, y: event.clientY };
    this.blueprintLastPan = { ...this.blueprintPan() };
  }

  onBlueprintMouseMove(event: MouseEvent): void {
    if (!this.blueprintDragging) return;
    const dx = event.clientX - this.blueprintLastClient.x;
    const dy = event.clientY - this.blueprintLastClient.y;
    this.blueprintLastClient = { x: event.clientX, y: event.clientY };
    this.blueprintPan.set({
      x: this.blueprintLastPan.x + dx,
      y: this.blueprintLastPan.y + dy,
    });
  }

  onBlueprintMouseUp(): void {
    this.blueprintDragging = false;
    this.blueprintLastPan = { ...this.blueprintPan() };
  }

  @HostListener('window:mousemove', ['$event'])
  onWindowMouseMove(event: MouseEvent): void {
    if (this.blueprintDragging) this.onBlueprintMouseMove(event);
  }

  @HostListener('window:mouseup')
  onWindowMouseUp(): void {
    if (this.blueprintDragging) this.onBlueprintMouseUp();
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
