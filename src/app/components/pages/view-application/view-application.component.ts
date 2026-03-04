import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';

/** Record data for view application page (passed from Dashboard). */
export interface ViewApplicationRecord {
  permitId: string;
  applicant: string;
  address: string;
  zoningType: string;
  landAreaSqFt?: number;
  existingBuiltUpArea?: number;
  proposedBuiltUpArea?: number;
  noOfFloors?: number;
  scopeOfWork?: string;
  permitType?: string;
  submittedDate?: string;
  submittedTime?: string;
  status?: string;
}

@Component({
  selector: 'app-view-application',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './view-application.component.html',
  styleUrl: './view-application.component.scss',
})
export class ViewApplicationComponent implements OnInit {
  currentStep = 1;
  totalSteps = 6;
  steps = [1, 2, 3, 4, 5, 6];

  record: ViewApplicationRecord | null = null;

  agentActivityEvents = [
    { agentName: 'Intake Agent', status: 'DONE', time: '11:43 am', description: "We're reviewing your uploaded documents and capturing key project information." },
    { agentName: 'Code Enforcement Agent', status: 'DONE', time: '11:45 am', description: "We're verifying your project against Austin building codes and safety standards." },
    { agentName: 'Planning Agent', status: 'DONE', time: '11:47 am', description: "We're evaluating zoning rules, height limits, parking requirements, and overlay restrictions." },
    { agentName: 'Inspector Agent', status: 'DONE', time: '11:49 am', description: "We're compiling the results of all checks into your pre-compliance report." },
  ];

  complianceFindings = [
    { agent: 'Intake', findings: 'Missing Fire Egress', status: 'Critical' },
    { agent: 'Code Enforcement', findings: 'Railing Height 34"', status: 'Violation' },
    { agent: 'Planner', findings: 'Impervious 44.2%', status: 'Warning' },
    { agent: 'Inspector', findings: 'Unpermitted Shed', status: 'Follow-up' },
  ];

  constructor(private router: Router) {}

  ngOnInit(): void {
    // getCurrentNavigation() is often null once the component initializes; use lastSuccessfulNavigation or history.state
    let state = this.router.lastSuccessfulNavigation?.extras?.state as { record?: ViewApplicationRecord } | undefined;
    if (!state?.record) {
      state = this.router.getCurrentNavigation()?.extras?.state as { record?: ViewApplicationRecord } | undefined;
    }
    if (!state?.record && typeof history !== 'undefined' && history.state?.record) {
      state = history.state as { record?: ViewApplicationRecord };
    }
    if (state?.record) {
      this.record = state.record;
    }
  }

  getStepTitle(step: number): string {
    const titles: Record<number, string> = {
      1: 'Applicant Information',
      2: 'Property Details',
      3: 'Scope of Work & Document Upload',
      4: 'AI Agents at Work',
      5: 'AI Pre-Compliance Report',
      6: 'Submission Confirmation',
    };
    return titles[step] ?? `Step ${step}`;
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

  returnToDashboard(): void {
    this.router.navigate(['/dashboard']);
  }

  getFindingStatusClass(status: string): string {
    return 'status-' + status.toLowerCase().replace(/\s+/g, '-');
  }

  getAgentDisplayName(agent: string): string {
    if (agent === 'Code') return 'Code Enforcement Agent';
    return agent;
  }
}
