import { CommonModule } from '@angular/common';
import { Component, HostListener } from '@angular/core';

import { AccueilComponent } from './pages/accueil/accueil';
import { SupportComponent } from './components/support/support';
import { ProfesseurSpaceComponent } from './espaces/espace-professeur/professeur-space/professeur-space';
import { AdminAuthenticationComponent } from './espaces/espace-admin/login/admin-authentication';
import { AdminSpaceComponent } from './espaces/espace-admin/dashboard/admin-space';
import { StudentAuthenticationComponent } from './espaces/espace-etudiant/login/student-authentication';
import { StudentSpaceComponent } from './espaces/espace-etudiant/dashboard/student-space';


type SecureExamSpace =
  | 'dashboard'
  | 'professor'
  | 'admin'
  | 'student'
  | 'support';


import { GlobalNotificationsComponent } from './components/global-notifications/global-notifications';

@Component({
  selector: 'app-root',
  standalone: true,

  imports: [
    GlobalNotificationsComponent,
    CommonModule,
    AccueilComponent,
    SupportComponent,
    ProfesseurSpaceComponent,
    AdminAuthenticationComponent,
    AdminSpaceComponent,
    StudentAuthenticationComponent,
    StudentSpaceComponent
  ],

  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {

  secureExamSpace: SecureExamSpace =
    this.resolveSecureExamSpaceFromPath();


  isAdminAuthenticated =
    localStorage.getItem(
      'secureexam_admin_token'
    ) !== null;


  isStudentAuthenticated =
    localStorage.getItem(
      'secureexam_student_token'
    ) !== null;


  private resolveSecureExamSpaceFromPath():
    SecureExamSpace {

    const path =
      window.location.pathname.toLowerCase();

    const studentToken =
      localStorage.getItem(
        'secureexam_student_token'
      );

    /*
     * Si le navigateur revient accidentellement
     * sur "/" alors qu'une session étudiant
     * existe, on restaure l'espace étudiant.
     */
    if (
      (
        path === '/'
        || path === ''
      )
      && studentToken
    ) {

      window.history.replaceState(
        {},
        '',
        '/espace_etudiant/dashboard'
      );

      return 'student';
    }

    /*
     * Un étudiant déjà connecté ne doit pas
     * rester sur /login après un refresh.
     */
    if (
      path === '/espace_etudiant/login'
      && studentToken
    ) {

      window.history.replaceState(
        {},
        '',
        '/espace_etudiant/dashboard'
      );

      return 'student';
    }


    if (
      path === '/'
      || path === ''
    ) {
      window.history.replaceState(
        {},
        '',
        '/accueil'
      );

      return 'dashboard';
    }


    if (
      path.startsWith('/accueil')
    ) {
      return 'dashboard';
    }


    if (
      path.startsWith('/support')
    ) {
      return 'support';
    }


    if (
      path.startsWith('/espace_prof')
    ) {
      return 'professor';
    }


    if (
      path.startsWith('/espace_admin')
    ) {
      return 'admin';
    }


    if (
      path.startsWith('/espace_etudiant')
    ) {
      return 'student';
    }


    window.history.replaceState(
      {},
      '',
      '/accueil'
    );

    return 'dashboard';
  }


  private setSecureExamSpace(
    path: string,
    space: SecureExamSpace
  ): void {

    this.secureExamSpace = space;

    if (
      window.location.pathname
      !== path
    ) {
      window.history.pushState(
        {},
        '',
        path
      );
    }

    window.scrollTo({
      top: 0,
      behavior: 'auto'
    });
  }


  openProfessorSpace(): void {

    this.setSecureExamSpace(
      '/espace_prof/login',
      'professor'
    );
  }


  openAdminSpace(): void {

    this.setSecureExamSpace(
      '/espace_admin/login',
      'admin'
    );
  }


  openStudentSpace(): void {

    this.setSecureExamSpace(
      '/espace_etudiant/login',
      'student'
    );
  }


  openPublicSupportPage(): void {

    this.setSecureExamSpace(
      '/support',
      'support'
    );
  }


  openAdminSupportFromLogin(): void {

    this.openPublicSupportPage();
  }


  handleAdminAuthenticated(): void {

    this.isAdminAuthenticated =
      true;

    this.secureExamSpace =
      'admin';

    if (
      window.location.pathname
      !== '/espace_admin/dashboard'
    ) {
      window.history.pushState(
        {},
        '',
        '/espace_admin/dashboard'
      );
    }

    window.scrollTo({
      top: 0,
      behavior: 'auto'
    });
  }


  logoutAdmin(): void {

    localStorage.removeItem(
      'secureexam_admin_token'
    );

    localStorage.removeItem(
      'secureexam_admin_username'
    );

    this.isAdminAuthenticated =
      false;

    this.setSecureExamSpace(
      '/espace_admin/login',
      'admin'
    );
  }


  handleStudentAuthenticated(): void {

    this.isStudentAuthenticated =
      true;

    this.secureExamSpace =
      'student';

    if (
      window.location.pathname
      !== '/espace_etudiant/dashboard'
    ) {
      window.history.pushState(
        {},
        '',
        '/espace_etudiant/dashboard'
      );
    }

    window.scrollTo({
      top: 0,
      behavior: 'auto'
    });
  }


  logoutStudent(): void {

    localStorage.removeItem(
      'secureexam_student_token'
    );

    localStorage.removeItem(
      'secureexam_student_username'
    );

    localStorage.removeItem(
      'secureexam_student_number'
    );

    localStorage.removeItem(
      'secureexam_student_full_name'
    );

    this.isStudentAuthenticated =
      false;

    this.setSecureExamSpace(
      '/espace_etudiant/login',
      'student'
    );
  }


  backToMainDashboard(): void {

    this.setSecureExamSpace(
      '/accueil',
      'dashboard'
    );
  }


  @HostListener('window:popstate')
  onPopState(): void {

    this.isAdminAuthenticated =
      localStorage.getItem(
        'secureexam_admin_token'
      ) !== null;

    this.isStudentAuthenticated =
      localStorage.getItem(
        'secureexam_student_token'
      ) !== null;

    this.secureExamSpace =
      this.resolveSecureExamSpaceFromPath();

    window.scrollTo({
      top: 0,
      behavior: 'auto'
    });
  }
}
