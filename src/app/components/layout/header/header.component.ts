import { Component } from '@angular/core';
import { AuthService } from '../../../services/auth.service';

@Component({
  selector: 'app-header',
  standalone: true,
  templateUrl: './header.component.html',
  styleUrl: './header.component.scss',
})
export class HeaderComponent {
  constructor(private auth: AuthService) {}

  get title(): string {
    return this.auth.headerTitle;
  }

  logout(): void {
    this.auth.logout();
  }
}
