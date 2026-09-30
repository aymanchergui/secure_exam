import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, EventEmitter, Input, OnInit, Output, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule, HttpHeaders } from '@angular/common/http';
import { AdminHeaderComponent } from '../header/admin-header';

declare const lucide: any;

interface AdminProfile {
  full_name: string;
  email: string;
  phone: string;
  room: string;
  notes: string;
}

interface AdminSupportRequest {
  id: number;
  username: string;
  subject: string;
  category: string;
  priority: string;
  message: string;
  status: string;
  created_at: string;
}


interface AdminNixosConfigItem {
  id: number;
  exam_id: string;
  exam_name: string;
    professor_name: string;
exam_date: string;
  exam_time: string;
  nix_filename: string;
  created_at?: string;
  updated_at?: string;

  roster_id?: number | null;
  roster_filename: string;
  roster_count: number;
  roster_status: string;
  sent_at?: string | null;
}

interface AdminRosterStudent {
  line_number: number;
  student_number: string;
  full_name: string;
  email: string;
}


interface AdminRosterPreview {
  config_id: number;
  exam_id: string;
  exam_name: string;
  filename: string;
  students_count: number;
  status: string;
  sent_at?: string | null;
  students: AdminRosterStudent[];
}


interface AdminNixosPreview {
  id: number;
  exam_id: string;
  exam_name: string;
  professor_name: string;
  filename: string;
  content: string;
}


@Component({
  selector: 'app-admin-space',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule, AdminHeaderComponent],
  templateUrl: './admin-space.html',
  styleUrl: './admin-space.css'
})
export class AdminSpaceComponent implements OnInit, AfterViewInit {

  private readonly adminNixosHttp =
    inject(HttpClient);

  private readonly adminNixosApiUrl =
    `/api`;

  adminNixosConfigs:
    AdminNixosConfigItem[] = [];

  adminNixosPreview:
    AdminNixosPreview | null = null;

  adminNixosLoading = false;
  adminNixosError = '';

  adminRosterPreview:
    AdminRosterPreview | null = null;

  adminDeliveryLoadingId = 0;
  adminDeliverySuccess = '';



  @Input() publicSupportMode = false;

  @Output() backToDashboard = new EventEmitter<void>();
  @Output() logoutRequested = new EventEmitter<void>();

  activeSection = this.resolveSectionFromPath();

  adminName = localStorage.getItem('secureexam_admin_username') || 'Administrateur';

  profile: AdminProfile = {
    full_name: 'Administrateur',
    email: 'administrateur@isen.fr',
    phone: '',
    room: '',
    notes: ''
  };

  profileSuccess = '';
  profileError = '';
  profileLoading = false;

  supportForm = {
    subject: '',
    category: 'Configuration NixOS',
    priority: 'Normale',
    message: ''
  };

  supportRequests: AdminSupportRequest[] = [];
  supportSuccess = '';
  supportError = '';
  supportLoading = false;

  private apiUrl = `/api`;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.loadAdminNixosConfigs();
    if (this.publicSupportMode) {
      this.activeSection = 'help';
      this.adminName = 'Support';
    }
  }

  ngAfterViewInit(): void {
    this.refreshIcons();
    if (!this.publicSupportMode) {
      this.loadProfile();
      this.loadSupportRequests();
    }
  }

  private refreshIcons(): void {
    setTimeout(() => {
      if (typeof lucide !== 'undefined') {
        lucide.createIcons();
      }
    });
  }

  private getAuthHeaders(): HttpHeaders {
    const token = localStorage.getItem('secureexam_admin_token') || '';

    return new HttpHeaders({
      Authorization: `Bearer ${token}`
    });
  }

  private resolveSectionFromPath(): string {
    const path = window.location.pathname.toLowerCase();

    if (path.includes('/profil') || path.includes('/profile')) {
      return 'profile';
    }

    if (path.includes('/support') || path.includes('/assistance')) {
      return 'help';
    }

    if (path.includes('/config')) {
      return 'configs';
    }

    if (path.includes('/machines')) {
      return 'machines';
    }

    return 'dashboard';
  }

  private getPathFromSection(section: string): string {
    const routes: Record<string, string> = {
      dashboard: '/espace_admin/dashboard',
      configs: '/espace_admin/configurations',
      machines: '/espace_admin/machines',
      help: '/espace_admin/support',
      profile: '/espace_admin/profil'
    };

    return routes[section] || '/espace_admin/dashboard';
  }

  handleSectionRequested(section: string): void {
    this.activeSection = section;

    const nextPath = this.getPathFromSection(section);

    if (window.location.pathname !== nextPath) {
      window.history.pushState({}, '', nextPath);
    }

    window.scrollTo({ top: 0, behavior: 'auto' });

    if (section === 'profile') {
      this.loadProfile();
    }

    if (section === 'help') {
      this.loadSupportRequests();
    }

    this.refreshIcons();
  }

  refreshAdminSpace(): void {
    if (!this.publicSupportMode) {
      this.loadProfile();
      this.loadSupportRequests();
      this.loadAdminNixosConfigs();
    }

    this.refreshIcons();
  }

  loadProfile(): void {
    if (this.publicSupportMode) {
      return;
    }

    this.profileLoading = true;
    this.profileError = '';

    this.http.get<AdminProfile>(`${this.apiUrl}/admin/profile`, {
      headers: this.getAuthHeaders()
    }).subscribe({
      next: (profile) => {
        this.profile = profile;
        this.adminName = profile.full_name || 'Administrateur';
        this.profileLoading = false;
        this.refreshIcons();
      },
      error: (error) => {
        this.profileLoading = false;
        this.profileError = error?.error?.detail || 'Impossible de charger le profil administrateur.';
      }
    });
  }

  saveProfile(): void {
    this.profileSuccess = '';
    this.profileError = '';

    if (!this.profile.full_name.trim()) {
      this.profileError = 'Le nom du administrateur est obligatoire.';
      return;
    }

    this.profileLoading = true;

    this.http.put<AdminProfile>(`${this.apiUrl}/admin/profile`, this.profile, {
      headers: this.getAuthHeaders()
    }).subscribe({
      next: (profile) => {
        this.profile = profile;
        this.adminName = profile.full_name || 'Administrateur';
        localStorage.setItem('secureexam_admin_username', this.adminName);
        this.profileSuccess = 'Profil admin mis à jour.';
        this.profileLoading = false;
        this.refreshIcons();
      },
      error: (error) => {
        this.profileLoading = false;
        this.profileError = error?.error?.detail || 'Impossible de sauvegarder le profil.';
      }
    });
  }

  loadSupportRequests(): void {
    if (this.publicSupportMode) {
      this.supportRequests = [];
      return;
    }

    this.http.get<AdminSupportRequest[]>(`${this.apiUrl}/admin/support`, {
      headers: this.getAuthHeaders()
    }).subscribe({
      next: (requests) => {
        this.supportRequests = requests;
        this.refreshIcons();
      },
      error: () => {
        this.supportRequests = [];
      }
    });
  }

  sendSupportRequest(): void {
    this.supportSuccess = '';
    this.supportError = '';

    if (!this.supportForm.subject.trim() || !this.supportForm.message.trim()) {
      this.supportError = 'Veuillez renseigner le sujet et le message.';
      return;
    }

    this.supportLoading = true;

    const endpoint = this.publicSupportMode
      ? `${this.apiUrl}/admin/support/public`
      : `${this.apiUrl}/admin/support`;

    const options = this.publicSupportMode
      ? {}
      : { headers: this.getAuthHeaders() };

    this.http.post<AdminSupportRequest>(endpoint, this.supportForm, options).subscribe({
      next: () => {
        this.supportSuccess = 'Demande support envoyée.';
        this.supportForm = {
          subject: '',
          category: 'Configuration NixOS',
          priority: 'Normale',
          message: ''
        };
        this.supportLoading = false;
        this.loadSupportRequests();
        this.refreshIcons();
      },
      error: (error) => {
        this.supportLoading = false;
        this.supportError = error?.error?.detail || 'Impossible d’envoyer la demande support.';
      }
    });
  }

  private adminNixosToken(): string {
    return (
      localStorage.getItem(
        'secureexam_admin_token'
      ) || ''
    );
  }


  private adminNixosHeaders():
    Record<string, string> {

    const token =
      this.adminNixosToken();

    return {
      Authorization: `Bearer ${token}`
    };
  }


  loadAdminNixosConfigs(): void {

    if (
      this.publicSupportMode
    ) {
      return;
    }


    const token =
      this.adminNixosToken();


    if (!token) {

      this.adminNixosConfigs = [];

      return;
    }


    this.adminNixosLoading = true;
    this.adminNixosError = '';


    this.adminNixosHttp
      .get<AdminNixosConfigItem[]>(
        (
          `${this.adminNixosApiUrl}`
          + '/admin/exam-delivery'
        ),
        {
          headers:
            this.adminNixosHeaders()
        }
      )
      .subscribe({

        next: (configs) => {

          this.adminNixosConfigs =
            configs || [];

          this.adminNixosLoading =
            false;

          this.refreshIcons();
        },


        error: (error) => {

          this.adminNixosLoading =
            false;

          this.adminNixosError =
            error?.error?.detail
            || (
              'Impossible de charger '
              + 'les examens.'
            );
        }

      });
  }



  viewAdminNixosConfig(
    config: AdminNixosConfigItem
  ): void {

    this.adminNixosError = '';

    this.adminNixosHttp
      .get<AdminNixosPreview>(
        `${this.adminNixosApiUrl}/admin/nixos-configs/${config.id}`,
        {
          headers:
            this.adminNixosHeaders()
        }
      )
      .subscribe({
        next: (preview) => {
          this.adminNixosPreview =
            preview;
        },

        error: (error) => {
          this.adminNixosError =
            error?.error?.detail
            || 'Impossible de charger le fichier NixOS.';
        }
      });
  }


  closeAdminNixosPreview(): void {
    this.adminNixosPreview = null;
  }


  downloadAdminNixosConfig(
    config: AdminNixosConfigItem
  ): void {

    this.adminNixosError = '';

    this.adminNixosHttp
      .get(
        `${this.adminNixosApiUrl}/admin/nixos-configs/${config.id}/download`,
        {
          headers:
            this.adminNixosHeaders(),
          responseType: 'blob'
        }
      )
      .subscribe({
        next: (blob) => {

          const url =
            URL.createObjectURL(blob);

          const link =
            document.createElement('a');

          link.href = url;

          link.download =
            config.nix_filename;

          document.body.appendChild(link);

          link.click();
          link.remove();

          URL.revokeObjectURL(url);
        },

        error: (error) => {
          this.adminNixosError =
            error?.error?.detail
            || 'Impossible de télécharger le fichier NixOS.';
        }
      });
  }



  viewAdminRoster(
    config: AdminNixosConfigItem
  ): void {

    this.adminNixosError = '';
    this.adminDeliverySuccess = '';


    this.adminNixosHttp
      .get<AdminRosterPreview>(
        (
          `${this.adminNixosApiUrl}`
          + `/admin/exam-delivery/`
          + `${config.id}/roster`
        ),
        {
          headers:
            this.adminNixosHeaders()
        }
      )
      .subscribe({

        next: (roster) => {

          this.adminRosterPreview =
            roster;

          this.refreshIcons();
        },


        error: (error) => {

          this.adminNixosError =
            error?.error?.detail
            || (
              'Impossible de charger '
              + 'la liste des étudiants.'
            );
        }

      });
  }


  closeAdminRoster(): void {

    this.adminRosterPreview =
      null;
  }


  sendExamToStudents(
    config: AdminNixosConfigItem
  ): void {

    this.adminNixosError = '';
    this.adminDeliverySuccess = '';


    if (
      !config.roster_count
    ) {

      this.adminNixosError =
        (
          'Aucune liste étudiants '
          + 'associée à cet examen.'
        );

      return;
    }


    if (
      String(
        config.roster_status
        || ''
      ).toUpperCase()
      === 'SENT'
    ) {

      return;
    }


    const confirmed =
      window.confirm(
        (
          `Envoyer "${config.exam_name || config.exam_id}" `
          + `aux ${config.roster_count} étudiant(s) `
          + 'de la liste CSV ?'
        )
      );


    if (!confirmed) {
      return;
    }


    this.adminDeliveryLoadingId =
      config.id;


    this.adminNixosHttp
      .post<any>(
        (
          `${this.adminNixosApiUrl}`
          + `/admin/exam-delivery/`
          + `${config.id}/send`
        ),
        {},
        {
          headers:
            this.adminNixosHeaders()
        }
      )
      .subscribe({

        next: (response) => {

          this.adminDeliveryLoadingId =
            0;


          this.adminDeliverySuccess =
            (
              response?.already_sent
                ? (
                    `Examen déjà envoyé à `
                    + `${response.students_count} étudiant(s).`
                  )
                : (
                    response?.message
                    || (
                      `Examen envoyé à `
                      + `${response.students_count} étudiant(s).`
                    )
                  )
            );


          this.loadAdminNixosConfigs();

          this.refreshIcons();
        },


        error: (error) => {

          this.adminDeliveryLoadingId =
            0;


          const detail =
            error?.error?.detail;


          if (
            detail?.missing_students
            && Array.isArray(
              detail.missing_students
            )
          ) {

            const missing =
              detail.missing_students
                .map(
                  (student: any) =>
                    student.student_number
                )
                .join(', ');


            this.adminNixosError =
              (
                `${detail.message} `
                + `Compte(s) introuvable(s) : `
                + missing
              );

          } else {

            this.adminNixosError =
              (
                typeof detail === 'string'
                  ? detail
                  : (
                      detail?.message
                      || (
                        'Impossible d’envoyer '
                        + 'l’examen.'
                      )
                    )
              );
          }


          this.refreshIcons();
        }

      });
  }


  isAdminExamSent(
    config: AdminNixosConfigItem
  ): boolean {

    return (
      String(
        config.roster_status
        || ''
      ).toUpperCase()
      === 'SENT'
    );
  }


}
