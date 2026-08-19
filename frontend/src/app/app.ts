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
  nix_packages?: string[];
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
  nixName: string;
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
  verifiedNixPackage?: string;
  package: PackageCatalogItem;
}

interface PackageVerificationResponse {
  exists: boolean;
  catalogExists: boolean;
  name: string;
  nixName: string;
  displayName: string;
  verifiedNixPackage: string;
}

interface PackageSearchCandidate {
  name: string;
  nixName: string;
  displayName: string;
  version: string;
  description: string;
  verifiedNixPackage: string;
  catalogExists: boolean;
}

interface PackageSearchResponse {
  query: string;
  count: number;
  candidates: PackageSearchCandidate[];
}

interface PackageManagementItem extends PackageCatalogItem {
  usageCount: number;
  canDelete: boolean;
}

interface PackageManagementResponse {
  count: number;
  packages: PackageManagementItem[];
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

  private apiUrl = `http://${window.location.hostname}:8000`;
  headerTeacherFullName = localStorage.getItem('secure_exam_teacher_full_name') || 'Professeur';

  availablePackages: PackageCatalogItem[] = [];
  packageFilter: PackageFilter = 'all';
  showPackageCreationForm = false;

  packageVerificationStatus: 'idle' | 'checking' | 'valid' | 'invalid' = 'idle';
  packageVerificationMessage = '';
  verifiedPackageName = '';
  verifiedPackageDisplayName = '';
  verifiedPackageNixName = '';
  packageSearchCandidates: PackageSearchCandidate[] = [];
  selectedPackageCandidateNixName = '';

  showPackageDeleteModal = false;
  packageManagementLoading = false;
  packageManagementItems: PackageManagementItem[] = [];
  selectedPackageIdsToDelete = new Set<number>();
  private packageVerificationTimer?: number;

  newPackage = {
    name: '',
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
        setTimeout(() => this.refreshHeaderTeacherName(), 80);
        setTimeout(() => this.refreshHeaderTeacherName(), 350);
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
        setTimeout(() => this.refreshHeaderTeacherName(), 80);
        setTimeout(() => this.refreshHeaderTeacherName(), 350);
        this.publicPage = 'authentication';
        this.authenticatedPage = 'dashboard';

        localStorage.setItem('accessToken', data.access_token);
        setTimeout(() => this.refreshHeaderTeacherName(), 120);
        this.syncHeaderTeacherNameAfterLogin(localStorage.getItem('token') || localStorage.getItem('secure_exam_access_token') || localStorage.getItem('access_token') || '');
        window.dispatchEvent(new Event('secure-exam-authenticated'));

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


  syncHeaderTeacherNameAfterLogin(token: string): void {
    if (!token) {
      return;
    }

    setTimeout(() => {
      fetch(`${this.apiUrl}/teacher-profile`, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      })
        .then(response => {
          if (!response.ok) {
            throw new Error('Profil professeur non chargé');
          }

          return response.json();
        })
        .then(profile => {
          if (!profile?.fullName) {
            return;
          }

          localStorage.setItem('secure_exam_teacher_full_name', profile.fullName);

          window.dispatchEvent(
            new CustomEvent('secure-exam-teacher-name-updated', {
              detail: {
                fullName: profile.fullName
              }
            })
          );
        })
        .catch(() => {});
    }, 150);
  }


  getHeaderAuthToken(): string {
    const possibleKeys = [
      'token',
      'access_token',
      'authToken',
      'auth_token',
      'secure_exam_token',
      'secure_exam_access_token'
    ];

    for (const key of possibleKeys) {
      const value = localStorage.getItem(key);

      if (value && value.split('.').length === 3) {
        return value;
      }
    }

    for (let index = 0; index < localStorage.length; index++) {
      const key = localStorage.key(index);

      if (!key) {
        continue;
      }

      const value = localStorage.getItem(key);

      if (value && value.split('.').length === 3) {
        return value;
      }
    }

    return '';
  }

  applyHeaderTeacherFullName(fullName: string): void {
    const cleanName = fullName.trim();

    if (!cleanName) {
      return;
    }

    this.headerTeacherFullName = cleanName;
    localStorage.setItem('secure_exam_teacher_full_name', cleanName);

    const applyDom = () => {
      document.querySelectorAll('.profile-name').forEach((element) => {
        element.textContent = cleanName;
      });
    };

    applyDom();
    setTimeout(applyDom, 50);
    setTimeout(applyDom, 200);
    setTimeout(applyDom, 600);
  }

  refreshHeaderTeacherName(): void {
    const token = this.getHeaderAuthToken();

    if (!token) {
      this.headerTeacherFullName = 'Professeur';
      localStorage.removeItem('secure_exam_teacher_full_name');
      return;
    }

    fetch(`${this.apiUrl}/teacher-profile`, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error('Profil professeur non chargé');
        }

        return response.json();
      })
      .then((profile) => {
        if (profile?.fullName) {
          this.applyHeaderTeacherFullName(profile.fullName);
        }
      })
      .catch(() => {});
  }

  logout(): void {
    this.accessToken = '';
    this.isAuthenticated = false;
    this.headerTeacherFullName = 'Professeur';
    localStorage.removeItem('secure_exam_teacher_full_name');
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

  openPackageDeleteModal(): void {
    this.showPackageDeleteModal = true;
    document.body.style.overflow = 'hidden';
    this.selectedPackageIdsToDelete.clear();
    this.loadPackageManagementItems();
    this.refreshView();
  }

  closePackageDeleteModal(): void {
    this.showPackageDeleteModal = false;
    document.body.style.overflow = '';
    this.selectedPackageIdsToDelete.clear();
    this.refreshView();
  }

  loadPackageManagementItems(): void {
    const headers = this.getTeacherHeaders();

    this.packageManagementLoading = true;

    this.http.get<PackageManagementResponse>(
      `${this.apiUrl}/packages/management`,
      { headers }
    ).subscribe({
      next: (data) => {
        this.packageManagementItems = data.packages;
        this.packageManagementLoading = false;
        this.refreshView();
      },
      error: (err) => {
        console.error(err);
        this.error = "Erreur lors du chargement des paquets.";
        this.packageManagementLoading = false;
        this.refreshView();
      }
    });
  }

  isPackageSelectedForDeletion(packageId: number): boolean {
    return this.selectedPackageIdsToDelete.has(packageId);
  }

  togglePackageManagementSelection(packageId: number, checked: boolean): void {
    if (checked) {
      this.selectedPackageIdsToDelete.add(packageId);
    } else {
      this.selectedPackageIdsToDelete.delete(packageId);
    }

    this.refreshView();
  }

  getSelectedPackageDeleteCount(): number {
    return this.selectedPackageIdsToDelete.size;
  }

  deletePackageManagementItem(packageItem: PackageManagementItem): void {
    this.error = '';
    this.success = '';

    if (!packageItem.canDelete) {
      this.error = "Ce paquet est utilisé dans une configuration. Désactive-le au lieu de le supprimer.";
      this.refreshView();
      return;
    }

    const confirmed = window.confirm(
      `Supprimer définitivement le paquet "${packageItem.displayName}" du catalogue ?`
    );

    if (!confirmed) {
      return;
    }

    const headers = this.getTeacherHeaders();

    this.packageManagementLoading = true;

    this.http.delete<{ message: string }>(
      `${this.apiUrl}/packages/${packageItem.id}`,
      { headers }
    ).subscribe({
      next: (data) => {
        this.success = data.message;
        this.selectedPackageIdsToDelete.delete(packageItem.id);
        this.loadActivePackages();
        this.loadPackageManagementItems();
        this.packageManagementLoading = false;
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        if (err.status === 409 && err.error?.detail?.message) {
          this.error = err.error.detail.message;
        } else if (typeof err.error?.detail === 'string') {
          this.error = err.error.detail;
        } else {
          this.error = "Suppression impossible.";
        }

        this.packageManagementLoading = false;
        this.refreshView();
      }
    });
  }

  deleteSelectedPackages(): void {
    const selectedPackages = this.packageManagementItems.filter(
      packageItem =>
        this.selectedPackageIdsToDelete.has(packageItem.id) &&
        packageItem.canDelete
    );

    if (selectedPackages.length === 0) {
      this.error = "Sélectionne au moins un paquet supprimable.";
      this.refreshView();
      return;
    }

    const confirmed = window.confirm(
      `Supprimer définitivement ${selectedPackages.length} paquet(s) du catalogue ?`
    );

    if (!confirmed) {
      return;
    }

    const headers = this.getTeacherHeaders();

    this.packageManagementLoading = true;

    const deleteNext = (index: number): void => {
      if (index >= selectedPackages.length) {
        this.success = "Paquets sélectionnés supprimés avec succès.";
        this.selectedPackageIdsToDelete.clear();
        this.loadActivePackages();
        this.loadPackageManagementItems();
        this.packageManagementLoading = false;
        this.refreshView();
        return;
      }

      const packageItem = selectedPackages[index];

      this.http.delete<{ message: string }>(
        `${this.apiUrl}/packages/${packageItem.id}`,
        { headers }
      ).subscribe({
        next: () => {
          deleteNext(index + 1);
        },
        error: (err) => {
          console.error(err);
          this.error = `Suppression interrompue sur ${packageItem.displayName}.`;
          this.packageManagementLoading = false;
          this.refreshView();
        }
      });
    };

    deleteNext(0);
  }

  disablePackageManagementItem(packageItem: PackageManagementItem): void {
    const headers = this.getTeacherHeaders();

    this.packageManagementLoading = true;

    this.http.patch<{ message: string }>(
      `${this.apiUrl}/packages/${packageItem.id}/disable`,
      {},
      { headers }
    ).subscribe({
      next: (data) => {
        this.success = data.message;
        this.loadActivePackages();
        this.loadPackageManagementItems();
        this.packageManagementLoading = false;
        this.refreshView();
      },
      error: (err) => {
        console.error(err);
        this.error = "Désactivation impossible.";
        this.packageManagementLoading = false;
        this.refreshView();
      }
    });
  }


  togglePackageCreationForm(): void {
    this.showPackageCreationForm = !this.showPackageCreationForm;

    if (!this.showPackageCreationForm) {
      this.resetPackageVerification();
    }

    this.refreshView();
  }

  resetPackageVerification(): void {
    if (this.packageVerificationTimer) {
      window.clearTimeout(this.packageVerificationTimer);
      this.packageVerificationTimer = undefined;
    }

    this.packageVerificationStatus = 'idle';
    this.packageVerificationMessage = '';
    this.verifiedPackageName = '';
    this.verifiedPackageDisplayName = '';
    this.verifiedPackageNixName = '';
    this.packageSearchCandidates = [];
    this.selectedPackageCandidateNixName = '';
  }

  onPackageNameChanged(): void {
    const packageName = this.newPackage.name.trim().toLowerCase();

    if (this.packageVerificationTimer) {
      window.clearTimeout(this.packageVerificationTimer);
      this.packageVerificationTimer = undefined;
    }

    this.packageSearchCandidates = [];
    this.selectedPackageCandidateNixName = '';
    this.verifiedPackageName = '';
    this.verifiedPackageDisplayName = '';
    this.verifiedPackageNixName = '';

    if (!packageName) {
      this.packageVerificationStatus = 'idle';
      this.packageVerificationMessage = '';
      this.refreshView();
      return;
    }

    if (packageName.length < 2) {
      this.packageVerificationStatus = 'idle';
      this.packageVerificationMessage = 'Saisis au moins 2 caractères.';
      this.refreshView();
      return;
    }

    this.packageVerificationStatus = 'checking';
    this.packageVerificationMessage = 'Vérification du paquet et chargement des versions...';
    this.refreshView();

    this.packageVerificationTimer = window.setTimeout(() => {
      this.searchPackageCandidates(packageName);
    }, 700);
  }

  searchPackageCandidates(packageName: string): void {
    const headers = this.getTeacherHeaders();

    this.http.get<PackageSearchResponse>(
      `${this.apiUrl}/packages/search/${encodeURIComponent(packageName)}`,
      { headers }
    ).subscribe({
      next: (data) => {
        const currentPackageName = this.newPackage.name.trim().toLowerCase();

        if (currentPackageName !== packageName) {
          return;
        }

        this.packageSearchCandidates = data.candidates;

        if (data.candidates.length === 0) {
          this.packageVerificationStatus = 'invalid';
          this.packageVerificationMessage = 'Paquet introuvable.';
          this.refreshView();
          return;
        }

        const firstAvailable = data.candidates.find(candidate => !candidate.catalogExists);
        const selectedCandidate = firstAvailable || data.candidates[0];

        this.selectedPackageCandidateNixName = selectedCandidate.nixName;
        this.applySelectedPackageCandidate();

        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.packageVerificationStatus = 'invalid';
        this.packageVerificationMessage = typeof err.error?.detail === 'string'
          ? err.error.detail
          : 'Paquet introuvable.';

        this.packageSearchCandidates = [];
        this.selectedPackageCandidateNixName = '';
        this.verifiedPackageName = '';
        this.verifiedPackageDisplayName = '';
        this.verifiedPackageNixName = '';

        this.refreshView();
      }
    });
  }

  getSelectedPackageCandidate(): PackageSearchCandidate | undefined {
    return this.packageSearchCandidates.find(
      candidate => candidate.nixName === this.selectedPackageCandidateNixName
    );
  }

  getPackageCandidateLabel(candidate: PackageSearchCandidate): string {
    const versionText = candidate.version ? candidate.version : candidate.verifiedNixPackage;
    const status = candidate.catalogExists ? 'déjà présent' : 'disponible';

    return `${versionText} — ${candidate.nixName} (${status})`;
  }

  onPackageCandidateSelected(): void {
    this.applySelectedPackageCandidate();
    this.refreshView();
  }

  applySelectedPackageCandidate(): void {
    const selectedCandidate = this.getSelectedPackageCandidate();

    if (!selectedCandidate) {
      this.packageVerificationStatus = 'invalid';
      this.packageVerificationMessage = 'Choisis une version disponible.';
      this.verifiedPackageName = '';
      this.verifiedPackageDisplayName = '';
      this.verifiedPackageNixName = '';
      return;
    }

    this.verifiedPackageName = selectedCandidate.name;
    this.verifiedPackageDisplayName = selectedCandidate.displayName;
    this.verifiedPackageNixName = selectedCandidate.nixName;

    if (selectedCandidate.catalogExists) {
      this.packageVerificationStatus = 'invalid';
      this.packageVerificationMessage = 'Cette version existe déjà dans le catalogue.';
    } else {
      this.packageVerificationStatus = 'valid';
      this.packageVerificationMessage = `Version sélectionnée : ${selectedCandidate.verifiedNixPackage}`;
    }
  }

  getPackageDisplayFieldValue(): string {
    if (this.packageVerificationStatus === 'checking') {
      return 'Vérification en cours...';
    }

    if (this.packageVerificationStatus === 'valid') {
      return this.verifiedPackageDisplayName;
    }

    if (this.packageVerificationStatus === 'invalid') {
      return 'Paquet introuvable';
    }

    return '';
  }

  getGeneratedPackageDisplayName(): string {
    const packageName = this.newPackage.name.trim().toLowerCase();

    const displayNames: Record<string, string> = {
      gcc: 'GCC',
      gdb: 'GDB',
      git: 'Git',
      gnumake: 'Make',
      htop: 'Htop',
      make: 'Make',
      nano: 'Nano',
      python3: 'Python 3',
      vim: 'Vim'
    };

    if (!packageName) {
      return '';
    }

    if (displayNames[packageName]) {
      return displayNames[packageName];
    }

    return packageName
      .replace(/[-_.]+/g, ' ')
      .split(' ')
      .filter(word => word.length > 0)
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  createPackage(): void {
    this.error = '';
    this.success = '';

    const description = this.newPackage.description.trim();
    const selectedCandidate = this.getSelectedPackageCandidate();

    if (!description) {
      this.error = 'La description du paquet est obligatoire.';
      this.refreshView();
      return;
    }

    if (
      this.packageVerificationStatus !== 'valid' ||
      !selectedCandidate ||
      selectedCandidate.catalogExists
    ) {
      this.error = 'Choisis une version valide avant ajout.';
      this.refreshView();
      return;
    }

    const payload = {
      name: selectedCandidate.name,
      nixName: selectedCandidate.nixName,
      displayName: selectedCandidate.displayName,
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
        this.success = data.verifiedNixPackage
          ? `${data.message} Paquet NixOS vérifié : ${data.verifiedNixPackage}`
          : data.message;

        this.newPackage = {
          name: '',
          description: ''
        };

        this.resetPackageVerification();

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
        } else if (err.error?.detail?.message) {
          this.error = `${err.error.detail.message} ${err.error.detail.nixName || ''}`.trim();
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


  formatConfigDate(config: any): string {
    const rawDate = config?.created_at || config?.createdAt || config?.updated_at || config?.updatedAt;

    if (!rawDate) {
      return '—';
    }

    const parsedDate = new Date(rawDate);

    if (Number.isNaN(parsedDate.getTime())) {
      return rawDate;
    }

    return parsedDate.toLocaleString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  getApiErrorMessage(err: any, fallback: string): string {
    if (typeof err?.error?.detail === 'string') {
      return err.error.detail;
    }

    if (err?.error?.detail?.message) {
      return err.error.detail.message;
    }

    return fallback;
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

        const configErrorMessage = this.getApiErrorMessage(
          err,
          "Erreur lors de la création de la configuration."
        );

        if (err.status === 409) {
          window.alert(configErrorMessage);
        }

        this.error = configErrorMessage;

          if (err.error?.detail?.message === 'Paquets non autorisés') {
            const invalidPackages = err.error.detail.invalid_packages?.join(', ') || '';
            this.error = `Paquets non autorisés : ${invalidPackages}`;
          } else {
            this.error = this.getApiErrorMessage(err, "Erreur lors de la création de la configuration.");
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

        this.error = this.getApiErrorMessage(err, "Erreur lors de la création de la configuration.");
        this.refreshView();
      }
    });
  }
}
