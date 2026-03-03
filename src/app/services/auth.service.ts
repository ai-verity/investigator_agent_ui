import { Injectable } from '@angular/core';
import { Router } from '@angular/router';

const AUTH_KEY = 'investigator-agent-auth';
const AUTH_ROLE_KEY = 'investigator-agent-role';

export type AuthRole = 'user' | 'admin';

export interface LoginCredentials {
  username: string;
  password: string;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private isAuthenticated = false;
  private role: AuthRole = 'user';

  constructor(private router: Router) {
    const stored = this.getStoredAuth();
    this.isAuthenticated = stored.authenticated;
    this.role = stored.role;
  }

  get isLoggedIn(): boolean {
    return this.isAuthenticated;
  }

  get currentRole(): AuthRole {
    return this.role;
  }

  /** Header title: "Permit Application" for user, "Investigator Agent" for admin */
  get headerTitle(): string {
    return this.role === 'admin' ? 'Investigator Agent' : 'Permit Application';
  }

  login(credentials: LoginCredentials): boolean {
    const u = credentials.username?.trim();
    const p = credentials.password;

    if (u === 'user' && p === 'password') {
      this.isAuthenticated = true;
      this.role = 'user';
      sessionStorage.setItem(AUTH_KEY, 'true');
      sessionStorage.setItem(AUTH_ROLE_KEY, 'user');
      return true;
    }
    if (u === 'admin' && p === 'password') {
      this.isAuthenticated = true;
      this.role = 'admin';
      sessionStorage.setItem(AUTH_KEY, 'true');
      sessionStorage.setItem(AUTH_ROLE_KEY, 'admin');
      return true;
    }
    return false;
  }

  logout(): void {
    this.isAuthenticated = false;
    this.role = 'user';
    sessionStorage.removeItem(AUTH_KEY);
    sessionStorage.removeItem(AUTH_ROLE_KEY);
    this.router.navigate(['/login']);
  }

  private getStoredAuth(): { authenticated: boolean; role: AuthRole } {
    const auth = sessionStorage.getItem(AUTH_KEY) === 'true';
    const role = (sessionStorage.getItem(AUTH_ROLE_KEY) as AuthRole) || 'user';
    return { authenticated: auth, role };
  }
}
