import { CommonModule } from '@angular/common';
import { Component, HostListener } from '@angular/core';

import { AccueilComponent } from './pages/accueil/accueil';
import { SupportComponent } from './components/support/support';
import { ProfesseurSpaceComponent } from './espaces/espace-professeur/professeur-space/professeur-space';
import { SupervisorAuthenticationComponent } from './espaces/espace-surveillant/login/supervisor-authentication';
import { SupervisorSpaceComponent } from './espaces/espace-surveillant/dashboard/supervisor-space';

type SecureExamSpace = 'dashboard' | 'professor' | 'supervisor' | 'support';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    AccueilComponent,
    SupportComponent,
    ProfesseurSpaceComponent,
    SupervisorAuthenticationComponent,
    SupervisorSpaceComponent
  ],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  secureExamSpace: SecureExamSpace = this.resolveSecureExamSpaceFromPath();

  isSupervisorAuthenticated = localStorage.getItem('secureexam_supervisor_token') !== null;

  private resolveSecureExamSpaceFromPath(): SecureExamSpace {
    const path = window.location.pathname.toLowerCase();

    if (path === '/' || path === '') {
      window.history.replaceState({}, '', '/accueil');
      return 'dashboard';
    }

    if (
      path.startsWith('/support') ||
      path.startsWith('/espace_prof/support') ||
      path.startsWith('/espace_surveillant/support')
    ) {
      if (window.location.pathname !== '/support') {
        window.history.replaceState({}, '', '/support');
      }

      return 'support';
    }

    if (path.startsWith('/accueil')) {
      return 'dashboard';
    }

    if (path.startsWith('/espace_prof')) {
      return 'professor';
    }

    if (path.startsWith('/espace_surveillant')) {
      const hasSupervisorToken = localStorage.getItem('secureexam_supervisor_token') !== null;

      if (hasSupervisorToken && path.startsWith('/espace_surveillant/login')) {
        window.history.replaceState({}, '', '/espace_surveillant/dashboard');
      }

      return 'supervisor';
    }

    window.history.replaceState({}, '', '/accueil');
    return 'dashboard';
  }

  private setSecureExamSpace(path: string, space: SecureExamSpace): void {
    this.secureExamSpace = space;

    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path);
    }

    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  openProfessorSpace(): void {
    this.setSecureExamSpace('/espace_prof/login', 'professor');
  }

  openSupervisorSpace(): void {
    this.setSecureExamSpace('/espace_surveillant/login', 'supervisor');
  }

  openPublicSupportPage(): void {
    this.setSecureExamSpace('/support', 'support');
  }

  openSupervisorSupportFromLogin(): void {
    this.openPublicSupportPage();
  }

  handleSupervisorAuthenticated(): void {
    this.isSupervisorAuthenticated = true;
    this.secureExamSpace = 'supervisor';

    if (window.location.pathname !== '/espace_surveillant/dashboard') {
      window.history.pushState({}, '', '/espace_surveillant/dashboard');
    }

    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  logoutSupervisor(): void {
    localStorage.removeItem('secureexam_supervisor_token');
    localStorage.removeItem('secureexam_supervisor_username');

    this.isSupervisorAuthenticated = false;
    this.secureExamSpace = 'supervisor';

    if (window.location.pathname !== '/espace_surveillant/login') {
      window.history.pushState({}, '', '/espace_surveillant/login');
    }

    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  backToMainDashboard(): void {
    this.setSecureExamSpace('/accueil', 'dashboard');
  }

  @HostListener('window:popstate')
  onPopState(): void {
    this.isSupervisorAuthenticated = localStorage.getItem('secureexam_supervisor_token') !== null;
    this.secureExamSpace = this.resolveSecureExamSpaceFromPath();

    window.scrollTo({ top: 0, behavior: 'auto' });
  }
}
