import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, EventEmitter, Input, OnInit, Output, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule, HttpHeaders } from '@angular/common/http';
import { SupervisorHeaderComponent } from '../header/supervisor-header';

declare const lucide: any;

interface SupervisorProfile {
  full_name: string;
  email: string;
  phone: string;
  room: string;
  notes: string;
}

interface SupervisorSupportRequest {
  id: number;
  username: string;
  subject: string;
  category: string;
  priority: string;
  message: string;
  status: string;
  created_at: string;
}


interface SupervisorNixosConfigItem {
  id: number;
  exam_id: string;
  exam_name: string;
    professor_name: string;
exam_date: string;
  exam_time: string;
  nix_filename: string;
  created_at?: string;
  updated_at?: string;
}

interface SupervisorNixosPreview {
  id: number;
  exam_id: string;
  exam_name: string;
  professor_name: string;
  filename: string;
  content: string;
}


@Component({
  selector: 'app-supervisor-space',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule, SupervisorHeaderComponent],
  templateUrl: './supervisor-space.html',
  styleUrl: './supervisor-space.css'
})
export class SupervisorSpaceComponent implements OnInit, AfterViewInit {

  private readonly supervisorNixosHttp =
    inject(HttpClient);

  private readonly supervisorNixosApiUrl =
    'http://127.0.0.1:8000';

  supervisorNixosConfigs:
    SupervisorNixosConfigItem[] = [];

  supervisorNixosPreview:
    SupervisorNixosPreview | null = null;

  supervisorNixosLoading = false;
  supervisorNixosError = '';


  @Input() publicSupportMode = false;

  @Output() backToDashboard = new EventEmitter<void>();
  @Output() logoutRequested = new EventEmitter<void>();

  activeSection = this.resolveSectionFromPath();

  supervisorName = localStorage.getItem('secureexam_supervisor_username') || 'Surveillant';

  profile: SupervisorProfile = {
    full_name: 'Surveillant',
    email: 'surveillant@isen.fr',
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

  supportRequests: SupervisorSupportRequest[] = [];
  supportSuccess = '';
  supportError = '';
  supportLoading = false;

  private apiUrl = `http://${window.location.hostname}:8000`;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.loadSupervisorNixosConfigs();
    if (this.publicSupportMode) {
      this.activeSection = 'help';
      this.supervisorName = 'Support';
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
    const token = localStorage.getItem('secureexam_supervisor_token') || '';

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
      dashboard: '/espace_surveillant/dashboard',
      configs: '/espace_surveillant/configurations',
      machines: '/espace_surveillant/machines',
      help: '/espace_surveillant/support',
      profile: '/espace_surveillant/profil'
    };

    return routes[section] || '/espace_surveillant/dashboard';
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

  refreshSupervisorSpace(): void {
    if (!this.publicSupportMode) {
      this.loadProfile();
      this.loadSupportRequests();
    }
    this.refreshIcons();
  }

  loadProfile(): void {
    if (this.publicSupportMode) {
      return;
    }

    this.profileLoading = true;
    this.profileError = '';

    this.http.get<SupervisorProfile>(`${this.apiUrl}/supervisor/profile`, {
      headers: this.getAuthHeaders()
    }).subscribe({
      next: (profile) => {
        this.profile = profile;
        this.supervisorName = profile.full_name || 'Surveillant';
        this.profileLoading = false;
        this.refreshIcons();
      },
      error: (error) => {
        this.profileLoading = false;
        this.profileError = error?.error?.detail || 'Impossible de charger le profil surveillant.';
      }
    });
  }

  saveProfile(): void {
    this.profileSuccess = '';
    this.profileError = '';

    if (!this.profile.full_name.trim()) {
      this.profileError = 'Le nom du surveillant est obligatoire.';
      return;
    }

    this.profileLoading = true;

    this.http.put<SupervisorProfile>(`${this.apiUrl}/supervisor/profile`, this.profile, {
      headers: this.getAuthHeaders()
    }).subscribe({
      next: (profile) => {
        this.profile = profile;
        this.supervisorName = profile.full_name || 'Surveillant';
        localStorage.setItem('secureexam_supervisor_username', this.supervisorName);
        this.profileSuccess = 'Profil surveillant mis à jour.';
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

    this.http.get<SupervisorSupportRequest[]>(`${this.apiUrl}/supervisor/support`, {
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
      ? `${this.apiUrl}/supervisor/support/public`
      : `${this.apiUrl}/supervisor/support`;

    const options = this.publicSupportMode
      ? {}
      : { headers: this.getAuthHeaders() };

    this.http.post<SupervisorSupportRequest>(endpoint, this.supportForm, options).subscribe({
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

  private supervisorNixosToken(): string {
    return (
      localStorage.getItem(
        'secureexam_supervisor_token'
      ) || ''
    );
  }


  private supervisorNixosHeaders():
    Record<string, string> {

    const token =
      this.supervisorNixosToken();

    return {
      Authorization: `Bearer ${token}`
    };
  }


  loadSupervisorNixosConfigs(): void {

    if (this.publicSupportMode) {
      return;
    }

    const token =
      this.supervisorNixosToken();

    if (!token) {
      this.supervisorNixosConfigs = [];
      return;
    }

    this.supervisorNixosLoading = true;
    this.supervisorNixosError = '';

    this.supervisorNixosHttp
      .get<SupervisorNixosConfigItem[]>(
        `${this.supervisorNixosApiUrl}/supervisor/nixos-configs`,
        {
          headers:
            this.supervisorNixosHeaders()
        }
      )
      .subscribe({
        next: (configs) => {
          this.supervisorNixosConfigs =
            configs || [];

          this.supervisorNixosLoading = false;
        },

        error: (error) => {
          this.supervisorNixosLoading = false;

          this.supervisorNixosError =
            error?.error?.detail
            || 'Impossible de charger les configurations NixOS.';
        }
      });
  }


  viewSupervisorNixosConfig(
    config: SupervisorNixosConfigItem
  ): void {

    this.supervisorNixosError = '';

    this.supervisorNixosHttp
      .get<SupervisorNixosPreview>(
        `${this.supervisorNixosApiUrl}/supervisor/nixos-configs/${config.id}`,
        {
          headers:
            this.supervisorNixosHeaders()
        }
      )
      .subscribe({
        next: (preview) => {
          this.supervisorNixosPreview =
            preview;
        },

        error: (error) => {
          this.supervisorNixosError =
            error?.error?.detail
            || 'Impossible de charger le fichier NixOS.';
        }
      });
  }


  closeSupervisorNixosPreview(): void {
    this.supervisorNixosPreview = null;
  }


  downloadSupervisorNixosConfig(
    config: SupervisorNixosConfigItem
  ): void {

    this.supervisorNixosError = '';

    this.supervisorNixosHttp
      .get(
        `${this.supervisorNixosApiUrl}/supervisor/nixos-configs/${config.id}/download`,
        {
          headers:
            this.supervisorNixosHeaders(),
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
          this.supervisorNixosError =
            error?.error?.detail
            || 'Impossible de télécharger le fichier NixOS.';
        }
      });
  }


}
