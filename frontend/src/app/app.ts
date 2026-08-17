import { Component, OnInit, AfterViewInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

import { HeaderComponent } from './components/header/header';
import { AuthenticationComponent } from './components/authentication/authentication';
import { SupportComponent } from './components/support/support';
import { ProfileComponent } from './components/profile/profile';

interface Submission {
  filename: string;
  size_kb: number;
  created_at: string;
  download_url: string;
}

interface MachineStatus {
  exam_id: string;
  student_id: string;
  machine_id: string;
  step: string;
  status: string;
  message: string;
  created_at?: string;
}

interface ExamConfigFile {
  filename: string;
  download_url: string;
}

interface ExamConfigDetail {
  exam_id: string;
  student_id: string;
  machine_id: string;
  packages: string[];
  sudo: boolean;
  internet: boolean;
  educ_access: boolean;
  allowed_domains: string[];
  workspace: string;
}

interface NixosConfig {
  filename: string;
  content: string;
}

interface PackageCatalogItem {
  id: number;
  name: string;
  displayName: string;
  description: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

interface PackageCatalogResponse {
  count: number;
  packages: PackageCatalogItem[];
}

interface PackageCreateResponse {
  message: string;
  package: PackageCatalogItem;
}

interface Dashboard {
  configs_count: number;
  submissions_count: number;
  machines_count: number;
  configs: ExamConfigFile[];
  submissions: Submission[];
  machine_statuses: MachineStatus[];
}

type PackageFilter = 'all' | 'active' | 'inactive';

type LucideWindow = Window & {
  lucide?: {
    createIcons: () => void;
  };
};

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    HeaderComponent,
    AuthenticationComponent,
    SupportComponent,
    ProfileComponent
  ],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App implements OnInit, AfterViewInit {
  dashboard?: Dashboard;

  selectedConfig?: ExamConfigDetail;
  selectedConfigFilename = '';

  statusHistory: MachineStatus[] = [];
  statusHistoryTitle = '';

  nixosConfig?: NixosConfig;

  loading = false;
  packagesLoading = false;
  packageCreating = false;
  packageActionLoadingId = 0;

  error = '';
  success = '';

  isAuthenticated = false;

  publicPage: 'authentication' | 'support' = 'authentication';
  authenticatedPage: 'dashboard' | 'profile' = 'dashboard';

  loginUsername = 'prof';
  loginPassword = '';
  loginError = '';
  accessToken = '';

  private apiUrl = 'http://127.0.0.1:8000';

  availablePackages: PackageCatalogItem[] = [];
  packageFilter: PackageFilter = 'all';
  showPackageCreationForm = false;

  newPackage = {
    name: '',
    displayName: '',
    description: ''
  };

  newConfig = {
    exam_id: 'EXAM-PYTHON-2026',
    student_id: 'etu001',
    machine_id: 'PC01',
    packages: [] as string[],
    sudo: false,
    internet: false,
    educ_access: true,
    allowed_domains_text: 'educ.isen.fr',
    workspace: '/home/exam/etu001/workspace'
  };

  constructor(
    private http: HttpClient,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    const savedToken = localStorage.getItem('accessToken');

    if (savedToken) {
      this.accessToken = savedToken;
      this.isAuthenticated = true;
      this.publicPage = 'authentication';
      this.authenticatedPage = 'dashboard';

      setTimeout(() => {
        this.loadActivePackages();
        this.loadDashboard();
      }, 100);
    } else {
      this.refreshLucideIcons();
    }
  }

  ngAfterViewInit(): void {
    this.refreshLucideIcons();
  }

  refreshLucideIcons(): void {
    setTimeout(() => {
      const lucide = (window as LucideWindow).lucide;

      if (lucide && typeof lucide.createIcons === 'function') {
        lucide.createIcons();
      }
    }, 100);
  }

  refreshView(): void {
    this.cdr.detectChanges();
    this.refreshLucideIcons();
  }

  openSupportPage(): void {
    this.publicPage = 'support';
    this.loginError = '';
    this.refreshView();
  }

  openAuthenticationPage(): void {
    this.publicPage = 'authentication';
    this.refreshView();
  }

  openProfilePage(): void {
    this.authenticatedPage = 'profile';
    this.error = '';
    this.success = '';
    this.refreshView();
  }

  openDashboardPage(): void {
    this.authenticatedPage = 'dashboard';
    this.error = '';
    this.success = '';
    this.refreshView();
  }

  openDashboardSection(section: string): void {
    this.authenticatedPage = 'dashboard';
    this.error = '';
    this.success = '';

    if (!this.dashboard) {
      this.loadDashboard();
    }

    this.refreshView();

    setTimeout(() => {
      window.location.hash = section;

      const element = document.getElementById(section);

      if (element) {
        element.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }

      this.refreshLucideIcons();
    }, 180);
  }

  onAuthenticationRequested(credentials: { username: string; password: string }): void {
    this.loginUsername = credentials.username;
    this.loginPassword = credentials.password;

    this.login();
  }

  getTeacherHeaders(): HttpHeaders {
    return new HttpHeaders({
      Authorization: `Bearer ${this.accessToken}`
    });
  }

  login(): void {
    this.loginError = '';
    this.error = '';
    this.success = '';

    const payload = {
      username: this.loginUsername,
      password: this.loginPassword
    };

    this.http.post<{ access_token: string; token_type: string }>(
      `${this.apiUrl}/auth/login`,
      payload
    ).subscribe({
      next: (data) => {
        this.accessToken = data.access_token;
        this.isAuthenticated = true;
        this.publicPage = 'authentication';
        this.authenticatedPage = 'dashboard';

        localStorage.setItem('accessToken', data.access_token);

        this.loadActivePackages();
        this.loadDashboard();
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.loginError = 'Identifiants enseignant incorrects.';
        this.loginPassword = '';

        this.refreshView();
      }
    });
  }

  logout(): void {
    this.accessToken = '';
    this.isAuthenticated = false;
    this.publicPage = 'authentication';
    this.authenticatedPage = 'dashboard';

    this.dashboard = undefined;
    this.selectedConfig = undefined;
    this.selectedConfigFilename = '';

    this.statusHistory = [];
    this.statusHistoryTitle = '';

    this.nixosConfig = undefined;
    this.availablePackages = [];

    this.newPackage = {
      name: '',
      displayName: '',
      description: ''
    };

    this.newConfig.packages = [];

    this.packageFilter = 'all';
    this.showPackageCreationForm = false;

    this.loginPassword = '';
    this.loginError = '';

    this.error = '';
    this.success = '';
    this.loading = false;
    this.packagesLoading = false;
    this.packageCreating = false;
    this.packageActionLoadingId = 0;

    localStorage.removeItem('accessToken');

    this.refreshView();
  }

  loadDashboard(): void {
    this.loading = true;
    this.error = '';

    const headers = this.getTeacherHeaders();

    this.http.get<Dashboard>(`${this.apiUrl}/dashboard`, { headers })
      .subscribe({
        next: (data) => {
          this.dashboard = data;
          this.loading = false;
          this.refreshView();
        },
        error: (err) => {
          console.error(err);

          this.error = 'Accès refusé ou session expirée. Reconnecte-toi.';
          this.loading = false;

          this.logout();
          this.refreshView();
        }
      });
  }

  loadActivePackages(): void {
    this.packagesLoading = true;

    const headers = this.getTeacherHeaders();

    this.http.get<PackageCatalogResponse>(
      `${this.apiUrl}/packages`,
      { headers }
    ).subscribe({
      next: (data) => {
        this.availablePackages = data.packages;
        this.newConfig.packages = this.getActivePackageNames();

        this.packagesLoading = false;
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.error = 'Impossible de charger le catalogue logiciel.';
        this.packagesLoading = false;

        this.refreshView();
      }
    });
  }

  getActivePackageNames(): string[] {
    return this.availablePackages
      .filter(packageItem => packageItem.isActive)
      .map(packageItem => packageItem.name);
  }

  get displayedPackages(): PackageCatalogItem[] {
    if (this.packageFilter === 'active') {
      return this.availablePackages.filter(packageItem => packageItem.isActive);
    }

    if (this.packageFilter === 'inactive') {
      return this.availablePackages.filter(packageItem => !packageItem.isActive);
    }

    return this.availablePackages;
  }

  setPackageFilter(filter: PackageFilter): void {
    this.packageFilter = filter;
    this.refreshView();
  }

  togglePackageCreationForm(): void {
    this.showPackageCreationForm = !this.showPackageCreationForm;
    this.refreshView();
  }

  createPackage(): void {
    this.error = '';
    this.success = '';

    const packageName = this.newPackage.name.trim().toLowerCase();
    const displayName = this.newPackage.displayName.trim();
    const description = this.newPackage.description.trim();

    if (!packageName) {
      this.error = 'Le nom technique du paquet est obligatoire.';
      this.refreshView();
      return;
    }

    if (!displayName) {
      this.error = 'Le nom affiché du paquet est obligatoire.';
      this.refreshView();
      return;
    }

    if (!description) {
      this.error = 'La description du paquet est obligatoire.';
      this.refreshView();
      return;
    }

    const payload = {
      name: packageName,
      displayName: displayName,
      description: description
    };

    const headers = this.getTeacherHeaders();

    this.packageCreating = true;

    this.http.post<PackageCreateResponse>(
      `${this.apiUrl}/packages`,
      payload,
      { headers }
    ).subscribe({
      next: (data) => {
        this.success = data.message;

        this.newPackage = {
          name: '',
          displayName: '',
          description: ''
        };

        this.packageCreating = false;
        this.showPackageCreationForm = false;
        this.packageFilter = 'all';

        this.loadActivePackages();
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        if (err.status === 409) {
          this.error = 'Ce paquet existe déjà dans le catalogue.';
        } else if (typeof err.error?.detail === 'string') {
          this.error = err.error.detail;
        } else {
          this.error = "Erreur lors de l'ajout du paquet logiciel.";
        }

        this.packageCreating = false;
        this.refreshView();
      }
    });
  }

  togglePackageActivation(packageItem: PackageCatalogItem): void {
    this.error = '';
    this.success = '';
    this.packageActionLoadingId = packageItem.id;

    const headers = this.getTeacherHeaders();
    const action = packageItem.isActive ? 'disable' : 'enable';

    this.http.patch<PackageCreateResponse>(
      `${this.apiUrl}/packages/${packageItem.id}/${action}`,
      {},
      { headers }
    ).subscribe({
      next: (data) => {
        this.success = data.message;
        this.packageActionLoadingId = 0;

        this.loadActivePackages();
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        if (typeof err.error?.detail === 'string') {
          this.error = err.error.detail;
        } else {
          this.error = "Erreur lors du changement d'état du paquet logiciel.";
        }

        this.packageActionLoadingId = 0;
        this.refreshView();
      }
    });
  }

  createConfig(): void {
    this.error = '';
    this.success = '';

    const activePackageNames = this.getActivePackageNames();

    if (activePackageNames.length === 0) {
      this.error = 'Aucun paquet logiciel actif disponible.';
      this.refreshView();
      return;
    }

    const headers = this.getTeacherHeaders();

    const payload = {
      exam_id: this.newConfig.exam_id,
      student_id: this.newConfig.student_id,
      machine_id: this.newConfig.machine_id,
      packages: activePackageNames,
      sudo: this.newConfig.sudo,
      internet: this.newConfig.internet,
      educ_access: this.newConfig.educ_access,
      allowed_domains: this.newConfig.allowed_domains_text
        .split(',')
        .map(domain => domain.trim())
        .filter(domain => domain.length > 0),
      workspace: this.newConfig.workspace
    };

    this.http.post(`${this.apiUrl}/configs`, payload, { headers })
      .subscribe({
        next: () => {
          this.success = 'Configuration créée avec succès.';
          this.loadDashboard();
          this.refreshView();
        },
        error: (err) => {
          console.error(err);

          if (err.error?.detail?.message === 'Paquets non autorisés') {
            const invalidPackages = err.error.detail.invalid_packages?.join(', ') || '';
            this.error = `Paquets non autorisés : ${invalidPackages}`;
          } else {
            this.error = 'Erreur lors de la création de la configuration.';
          }

          this.refreshView();
        }
      });
  }

  viewConfig(config: ExamConfigFile): void {
    this.error = '';

    const headers = this.getTeacherHeaders();

    this.http.get<ExamConfigDetail>(
      `${this.apiUrl}/configs-file/${encodeURIComponent(config.filename)}`,
      { headers }
    ).subscribe({
      next: (data) => {
        this.selectedConfig = data;
        this.selectedConfigFilename = config.filename;
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.error = 'Impossible de charger le détail de la configuration.';
        this.refreshView();
      }
    });
  }

  closeConfigDetails(): void {
    this.selectedConfig = undefined;
    this.selectedConfigFilename = '';
    this.refreshLucideIcons();
  }

  viewStatusHistory(machine: MachineStatus): void {
    this.error = '';

    const headers = this.getTeacherHeaders();

    const examId = encodeURIComponent(machine.exam_id);
    const studentId = encodeURIComponent(machine.student_id);
    const machineId = encodeURIComponent(machine.machine_id);

    this.http.get<MachineStatus[]>(
      `${this.apiUrl}/machine-status-history/${examId}/${studentId}/${machineId}`,
      { headers }
    ).subscribe({
      next: (data) => {
        this.statusHistory = data;
        this.statusHistoryTitle = `${machine.exam_id} / ${machine.student_id} / ${machine.machine_id}`;
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.error = "Impossible de charger l'historique de la machine.";
        this.refreshView();
      }
    });
  }

  closeStatusHistory(): void {
    this.statusHistory = [];
    this.statusHistoryTitle = '';
    this.refreshLucideIcons();
  }

  viewNixosConfig(): void {
    this.error = '';

    const headers = this.getTeacherHeaders();

    this.http.get<NixosConfig>(
      `${this.apiUrl}/nixos-config`,
      { headers }
    ).subscribe({
      next: (data) => {
        this.nixosConfig = data;
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.error = 'Impossible de charger la configuration NixOS. Lance start_exam.py pour la générer.';
        this.refreshView();
      }
    });
  }

  closeNixosConfig(): void {
    this.nixosConfig = undefined;
    this.refreshLucideIcons();
  }

  downloadConfig(config: ExamConfigFile): void {
    const headers = this.getTeacherHeaders();

    this.http.get(
      `${this.apiUrl}${config.download_url}`,
      {
        headers,
        responseType: 'blob'
      }
    ).subscribe({
      next: (blob) => {
        this.saveBlob(blob, config.filename);
        this.refreshLucideIcons();
      },
      error: (err) => {
        console.error(err);

        this.error = 'Impossible de télécharger la configuration.';
        this.refreshView();
      }
    });
  }

  downloadSubmission(submission: Submission): void {
    const headers = this.getTeacherHeaders();

    this.http.get(
      `${this.apiUrl}${submission.download_url}`,
      {
        headers,
        responseType: 'blob'
      }
    ).subscribe({
      next: (blob) => {
        this.saveBlob(blob, submission.filename);
        this.refreshLucideIcons();
      },
      error: (err) => {
        console.error(err);

        this.error = 'Impossible de télécharger le rendu étudiant.';
        this.refreshView();
      }
    });
  }

  downloadNixosConfig(): void {
    this.error = '';

    const headers = this.getTeacherHeaders();

    this.http.get(
      `${this.apiUrl}/nixos-config/download`,
      {
        headers,
        responseType: 'blob'
      }
    ).subscribe({
      next: (blob) => {
        this.saveBlob(blob, 'exam-configuration.nix');
        this.refreshLucideIcons();
      },
      error: (err) => {
        console.error(err);

        this.error = 'Impossible de télécharger la configuration NixOS.';
        this.refreshView();
      }
    });
  }

  saveBlob(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');

    link.href = url;
    link.download = filename;
    link.click();

    window.URL.revokeObjectURL(url);
  }

  deleteSubmission(submission: Submission): void {
    const confirmed = confirm(
      `Voulez-vous vraiment supprimer définitivement ce rendu ?\n\n${submission.filename}`
    );

    if (!confirmed) {
      return;
    }

    this.error = '';
    this.success = '';

    const headers = this.getTeacherHeaders();

    this.http.delete(
      `${this.apiUrl}/submissions/${encodeURIComponent(submission.filename)}`,
      { headers }
    ).subscribe({
      next: () => {
        this.success = 'Rendu supprimé avec succès.';
        this.loadDashboard();
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.error = 'Erreur lors de la suppression du rendu.';
        this.refreshView();
      }
    });
  }

  deleteConfig(config: ExamConfigFile): void {
    const confirmed = confirm(
      `Voulez-vous vraiment supprimer définitivement cette configuration ?\n\n${config.filename}`
    );

    if (!confirmed) {
      return;
    }

    this.error = '';
    this.success = '';

    const headers = this.getTeacherHeaders();

    this.http.delete(
      `${this.apiUrl}/configs/${encodeURIComponent(config.filename)}`,
      { headers }
    ).subscribe({
      next: () => {
        this.success = 'Configuration supprimée avec succès.';

        if (this.selectedConfigFilename === config.filename) {
          this.closeConfigDetails();
        }

        this.loadDashboard();
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.error = 'Erreur lors de la suppression de la configuration.';
        this.refreshView();
      }
    });
  }
}