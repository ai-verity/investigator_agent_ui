import { Routes } from '@angular/router';
import { LayoutComponent } from './components/layout/layout/layout.component';
import { DashboardComponent } from './components/pages/dashboard/dashboard.component';
import { ApplicationsComponent } from './components/pages/applications/applications.component';
import { ViewApplicationComponent } from './components/pages/view-application/view-application.component';
import { LoginComponent } from './components/pages/login/login.component';
import { authGuard } from './guards/auth.guard';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  {
    path: 'dashboard',
    component: LayoutComponent,
    canActivate: [authGuard],
    children: [{ path: '', component: DashboardComponent }],
  },
  {
    path: 'applications',
    component: LayoutComponent,
    canActivate: [authGuard],
    children: [{ path: '', component: ApplicationsComponent }],
  },
  {
    path: 'view-application',
    component: LayoutComponent,
    canActivate: [authGuard],
    children: [{ path: '', component: ViewApplicationComponent }],
  },
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: '**', redirectTo: 'dashboard' },
];
