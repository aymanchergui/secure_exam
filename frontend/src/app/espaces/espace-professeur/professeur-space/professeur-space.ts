import { CommonModule } from '@angular/common';
import { Component, OnInit, AfterViewInit, ChangeDetectorRef, HostListener } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

import { HeaderComponent } from '../header/header';
import { AuthenticationComponent } from '../login/authentication';
import { SupportComponent } from '../../../components/support/support';
import { ProfileComponent } from '../profil/profile';

interface Submission {
  filename: string;
  size_kb: number;
  created_at: string;
  download_url: string;
  exam_id?: string;
  student_id?: string;
  machine_id?: string;
  exam_created_at?: string;
  exam_updated_at?: string;
}

interface MachineStatus {
  exam_id: string;
  exam_name?: string;
  exam_date?: string;
  exam_time?: string;
  student_id?: string;
  machine_id?: string;
  step: string;
  status: string;
  message: string;
  created_at?: string;
}

interface ExamConfigFile {
  id?: number;
  filename: string;
  download_url: string;

  exam_id?: string;
  exam_name?: string;
  exam_date?: string;
  exam_time?: string;

  created_at?: string;
  updated_at?: string;

  // SECUREEXAM_TEACHER_DELIVERY_FIELDS_V2
  delivery_config_id?: number;
  roster_filename?: string | null;
  roster_count?: number;
  roster_status?: string;
  sent_at?: string | null;
}

interface ExamConfigDetail {
  exam_id: string;

  exam_name?: string;
  exam_date?: string;
  exam_time?: string;

  packages: string[];
  nix_packages?: string[];

  sudo: boolean;
  internet: boolean;
  educ_access: boolean;

  allowed_domains: string[];

  created_at?: string;
  updated_at?: string;

  // Conservés uniquement pour compatibilité backend.
  student_id?: string;
  machine_id?: string;
  workspace?: string;
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
  version?: string;
  verifiedNixPackage?: string;
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


type PackageTerminalLineKind =
  | 'command'
  | 'success'
  | 'error'
  | 'info';


interface PackageTerminalLine {
  kind: PackageTerminalLineKind;
  text: string;
}


interface PackageTerminalItem {
  id: number;
  name: string;
  nixName: string;
  displayName: string;
  description: string;
  isActive: boolean;
  version?: string;
  channel?: string;
  verified?: boolean;
  catalogCreated?: boolean;
}


interface PackageTerminalResponse {
  success: boolean;
  action: string;
  message: string;
  packages: string[];
  items: PackageTerminalItem[];
  package?: PackageTerminalItem;
  source?: string;
  onlineVerified?: boolean;
  channel?: string;
  added?: boolean;
  removed?: boolean;
}

interface PackageManagementItem extends PackageCatalogItem {
  usageCount: number;
  canDelete: boolean;
}

interface PackageManagementResponse {
  count: number;
  packages: PackageManagementItem[];
}


interface ExamEnvironmentPreset {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  icon: string;

  packageRefs: string[];

  sudo: boolean;
  internet: boolean;
  educAccess: boolean;

  allowedDomains: string[];
}


interface CustomExamEnvironment {
  id: number;
  name: string;
  packages: string[];
  created_at: string;
  updated_at: string;
}


interface CustomExamEnvironmentListResponse {
  count: number;
  environments: CustomExamEnvironment[];
}


interface CustomExamEnvironmentMutationResponse {
  message: string;
  environment: CustomExamEnvironment;
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
  selector: 'app-professeur-space',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    HeaderComponent,
    AuthenticationComponent,
    SupportComponent,
    ProfileComponent
  ],
  templateUrl: './professeur-space.html',
  styleUrl: './professeur-space.css'
})
export class ProfesseurSpaceComponent implements OnInit, AfterViewInit {

  private setProfessorUrl(path: string): void {
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path);
    }
  }


  openAdminSupportFromLogin(): void {
    sessionStorage.setItem('secureexam_open_general_support', '1');
    window.location.href = '/espace_prof/login?support=1';
  }


  isAdminAuthenticated = localStorage.getItem('secureexam_admin_token') !== null;

  isAdminPublicSupport =
    window.location.pathname.toLowerCase().startsWith('/espace_admin/support')
    && localStorage.getItem('secureexam_admin_token') === null;

  openAdminSpace(): void {
    this.isAdminPublicSupport = false;
    this.setSecureExamSpace('/espace_admin/login', 'admin');
  }


  handleAdminAuthenticated(): void {
    this.isAdminAuthenticated = true;
    this.isAdminPublicSupport = false;
    this.secureExamSpace = 'admin';

    if (window.location.pathname !== '/espace_admin/dashboard') {
      window.history.pushState({}, '', '/espace_admin/dashboard');
    }

    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  logoutAdmin(): void {
    localStorage.removeItem('secureexam_admin_token');
    localStorage.removeItem('secureexam_admin_username');

    this.isAdminAuthenticated = false;
    this.isAdminPublicSupport = false;
    this.secureExamSpace = 'admin';

    if (window.location.pathname !== '/espace_admin/login') {
      window.history.pushState({}, '', '/espace_admin/login');
    }

    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  backToMainDashboard(): void {
    this.isAdminPublicSupport = false;
    this.setSecureExamSpace('/accueil', 'dashboard');
  }





  private findProfessorSectionByText(labels: string[]): HTMLElement | null {
    const candidates = Array.from(
      document.querySelectorAll('h1, h2, h3, h4, .panel-title, .section-title, .card-title')
    ) as HTMLElement[];

    for (const label of labels) {
      const lowerLabel = label.toLowerCase();

      const title = candidates.find((element) =>
        element.textContent?.toLowerCase().includes(lowerLabel)
      );

      if (title) {
        return title.closest('.panel, .submission-exam-group, .card, section, article, div') as HTMLElement || title;
      }
    }

    return null;
  }

  private scrollToProfessorSection(section: string, behavior: ScrollBehavior = 'smooth'): void {
    const key = String(section || 'dashboard').toLowerCase();

    const textTargets: Record<string, string[]> = {
      dashboard: ['Configurations', 'Rendus reçus', 'Machines suivies'],
      configurations: ['Créer une configuration', 'Environnement d’examen', 'Configurations générées'],
      nixos: ['Configuration NixOS', 'NixOS générée', 'Fichier NixOS'],
      machines: ['Suivi des machines', 'Machines suivies', 'Machines'],
      rendus: ['Rendus étudiants', 'Rendus reçus', 'Rendus'],
      profile: ['Profil professeur', 'Profil'],
      profil: ['Profil professeur', 'Profil'],
      support: ['Support', 'Assistance']
    };

    let target = this.findProfessorSectionByText(textTargets[key] || []);

    if (!target) {
      const fallbackSelectors: Record<string, string[]> = {
        dashboard: ['.stats-grid', '.cards-grid', '.dashboard-cards', '.card'],
        configurations: ['.panel'],
        nixos: ['.nixos-section', '.nixos-panel'],
        machines: ['.machines-section'],
        rendus: ['.submissions-section', '.submission-exam-group'],
        profile: ['.profile-section'],
        profil: ['.profile-section'],
        support: ['.support-section']
      };

      for (const selector of fallbackSelectors[key] || []) {
        const element = document.querySelector(selector) as HTMLElement | null;

        if (element) {
          target = element;
          break;
        }
      }
    }

    if (!target || key === 'dashboard') {
      window.scrollTo({ top: 0, behavior });
      return;
    }

    const headerOffset = 118;
    const top = target.getBoundingClientRect().top + window.scrollY - headerOffset;

    window.scrollTo({
      top: Math.max(top, 0),
      behavior
    });
  }

  handleProfessorSectionRequested(section: string): void {
    (this as any).activeSection = section;
    this.secureExamSpace = 'professor';

    const nextPath = this.getProfessorPathFromSection(section);

    if (window.location.pathname !== nextPath) {
      window.history.pushState({}, '', nextPath);
    }

    setTimeout(() => {
      this.scrollToProfessorSection(section);
    }, 80);
  }

  @HostListener('window:popstate')
  onSecureExamPopState(): void {
    this.secureExamSpace = this.resolveSecureExamSpaceFromPath();
    this.isAdminPublicSupport =
      window.location.pathname.toLowerCase().startsWith('/espace_admin/support')
      && localStorage.getItem('secureexam_admin_token') === null;

    if (this.secureExamSpace === 'professor') {
      const section = this.getProfessorSectionFromPath();
      (this as any).activeSection = section;

      setTimeout(() => {
        this.scrollToProfessorSection(section, 'auto');
      }, 80);

      return;
    }

    window.scrollTo({ top: 0, behavior: 'auto' });
  }


  secureExamSpace: 'dashboard' | 'professor' | 'admin' = this.resolveSecureExamSpaceFromPath();

  private getProfessorPathFromSection(section: string): string {
    const key = String(section || 'dashboard').toLowerCase();

    const routes: Record<string, string> = {
      dashboard: '/espace_prof/dashboard',
      configurations: '/espace_prof/configurations',
      configuration: '/espace_prof/configurations',
      config: '/espace_prof/configurations',
      configs: '/espace_prof/configurations',
      nixos: '/espace_prof/nixos',
      machines: '/espace_prof/machines',
      rendus: '/espace_prof/rendus',
      submissions: '/espace_prof/rendus',
      profile: '/espace_prof/profil',
      profil: '/espace_prof/profil',
      support: '/espace_prof/support'
    };

    return routes[key] || '/espace_prof/dashboard';
  }

  private getProfessorSectionFromPath(): string {
    const path = window.location.pathname.toLowerCase();

    if (path.startsWith('/espace_prof/configurations')) {
      return 'configurations';
    }

    if (path.startsWith('/espace_prof/nixos')) {
      return 'nixos';
    }

    if (path.startsWith('/espace_prof/machines')) {
      return 'machines';
    }

    if (path.startsWith('/espace_prof/rendus')) {
      return 'rendus';
    }

    if (path.startsWith('/espace_prof/profil') || path.startsWith('/espace_prof/profile')) {
      return 'profile';
    }

    if (path.startsWith('/espace_prof/support')) {
      return 'support';
    }

    return 'dashboard';
  }

  private resolveSecureExamSpaceFromPath(): 'dashboard' | 'professor' | 'admin' {
    const path = window.location.pathname.toLowerCase();

    if (path === '/' || path === '') {
      window.history.replaceState({}, '', '/accueil');
      return 'dashboard';
    }

    if (path.startsWith('/accueil')) {
      return 'dashboard';
    }

    if (path.startsWith('/espace_prof')) {
      return 'professor';
    }

    if (path.startsWith('/espace_admin')) {
      return 'admin';
    }

    window.history.replaceState({}, '', '/accueil');
    return 'dashboard';
  }

  private setSecureExamSpace(path: string, space: 'dashboard' | 'professor' | 'admin'): void {
    this.secureExamSpace = space;

    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path);
    }

    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  openProfessorSpace(): void {
    this.setSecureExamSpace('/espace_prof/login', 'professor');
  }


  handleProfessorAuthenticated(): void {
    (this as any).isAuthenticated = true;
    (this as any).authenticated = true;
    (this as any).activeSection = 'dashboard';

    this.setSecureExamSpace('/espace_prof/dashboard', 'professor');
  }




  private isProfessorPath(path: string): boolean {
    const professorPaths = [
      '/espace_prof',
      '/espace_prof/login',
      '/espace_prof/dashboard',
      '/espace_prof/configurations',
      '/espace_prof/nixos',
      '/espace_prof/machines',
      '/espace_prof/rendus',
      '/espace_prof/profile',
      '/espace_prof/profil',
      '/espace_prof/support',

      // Sécurité pour les anciens chemins internes
      '/dashboard',
      '/configurations',
      '/nixos',
      '/machines',
      '/rendus',
      '/profile',
      '/profil'
    ];

    return professorPaths.some(professorPath => path.startsWith(professorPath));
  }











  showCreateConfigConfirmModal = false;
  pendingCreateConfigPreview: any = {};



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

  // SECUREEXAM_TEACHER_DELIVERY_STATE_V2
  teacherDeliveryLoadingExamId = '';

  error = '';
  success = '';

  isAuthenticated = false;

  publicPage: 'authentication' | 'support' = 'authentication';
  authenticatedPage: 'dashboard' | 'profile' = 'dashboard';

  loginUsername = 'prof';
  loginPassword = '';
  loginError = '';
  accessToken = '';

  private apiUrl = `/api`;
  headerTeacherFullName = localStorage.getItem('secure_exam_teacher_full_name') || 'Professeur';

  availablePackages: PackageCatalogItem[] = [];
  packageFilter: PackageFilter = 'all';
  packagePage = 1;
  packagePageSize = 9;
  packageVersionByNixName: Record<string, string> = {};
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

  examEnvironmentPresets:
    ExamEnvironmentPreset[] = [

    {
      id: 'python',

      title:
        'Python',

      subtitle:
        'Algorithmique & scripting',

      description:
        'Pour Python, algorithmique, structures de données et scripts.',

      icon:
        'code-2',

      packageRefs: [
        'python3',
        'vim'
      ],

      sudo: false,
      internet: false,
      educAccess: true,

      allowedDomains: []
    },


    {
      id: 'cpp',

      title:
        'C / C++',

      subtitle:
        'Compilation & débogage',

      description:
        'Pour programmation C/C++, compilation, mémoire et débogage.',

      icon:
        'braces',

      packageRefs: [
        'gcc',
        'gdb',
        'gnumake',
        'vim'
      ],

      sudo: false,
      internet: false,
      educAccess: true,

      allowedDomains: []
    },


    {
      id: 'java',

      title:
        'Java / POO',

      subtitle:
        'Programmation objet',

      description:
        'Pour Java, programmation objet et projets Maven.',

      icon:
        'coffee',

      packageRefs: [
        'jdk21',
        'maven',
        'vim'
      ],

      sudo: false,
      internet: false,
      educAccess: true,

      allowedDomains: []
    },


    {
      id: 'web',

      title:
        'Web',

      subtitle:
        'Frontend & JavaScript',

      description:
        'Pour HTML, CSS, JavaScript et applications Node.js locales.',

      icon:
        'globe-2',

      packageRefs: [
        'nodejs',
        'vim'
      ],

      sudo: false,
      internet: false,
      educAccess: true,

      allowedDomains: []
    },


    {
      id: 'database',

      title:
        'SQL / BDD',

      subtitle:
        'Bases de données',

      description:
        'Pour SQL, modélisation et bases de données locales.',

      icon:
        'database',

      packageRefs: [
        'sqlite',
        'postgresql',
        'vim'
      ],

      sudo: false,
      internet: false,
      educAccess: true,

      allowedDomains: []
    },


    {
      id: 'linux',

      title:
        'Linux / Shell',

      subtitle:
        'Systèmes & scripts',

      description:
        'Pour Bash, commandes Unix et traitement de texte.',

      icon:
        'terminal',

      packageRefs: [
        'bash',
        'coreutils',
        'gnugrep',
        'gnused',
        'gawk',
        'vim'
      ],

      sudo: false,
      internet: false,
      educAccess: true,

      allowedDomains: []
    }

  ];


  selectedEnvironmentId =
    'python';

  selectedEnvironmentCustomized =
    false;

  environmentInitialized =
    false;


  packageLibraryOpen =
    false;

  packageLibrarySearch =
    '';


  packageLibraryMode:
    'catalog'
    | 'custom' = 'catalog';



  packageTerminalPopupOpen = false;

  packageTerminalContext:
    'custom'
    | 'catalog' = 'custom';

  packageTerminalCatalogPackages:
    string[] = [];

  packageTerminalCommand = '';

  packageTerminalLoading = false;

  packageTerminalChannel = 'unstable';

  packageTerminalHistory:
    PackageTerminalLine[] = [];


  customEnvironmentNameModalOpen =
    false;

  customEnvironmentName =
    '';

  customEnvironmentBaseId:
    string | null = null;

  customEnvironmentEditingId:
    number | null = null;

  customEnvironmentSaving =
    false;


  customEnvironmentModalError =
    '';


  customEnvironments:
    CustomExamEnvironment[] = [];

  customEnvironmentsLoading =
    false;

  myCustomEnvironmentsOpen =
    false;


  newPackage = {
    name: '',
    description: ''
  };

  studentRosterFile:
    File | null = null;

  studentRosterFilename = '';
  studentRosterCount = 0;
  studentRosterError = '';

  studentRosterPreview:
    Array<{
      student_number: string;
      full_name: string;
      email: string;
    }> = [];


  get hasValidStudentRoster():
    boolean {

    return (
      this.studentRosterFile
      !== null
      && this.studentRosterCount > 0
      && !this.studentRosterError
    );
  }


  newConfig = {
    exam_id: 'EXAM-PYTHON-2026',
        exam_name: '',
        exam_date: '',
        exam_time: '',
    student_id: 'GLOBAL',
    machine_id: 'ALL_MACHINES',
    packages: [] as string[],
    sudo: false,
    internet: false,
    educ_access: true,
    allowed_domains_text: 'educ.isen.fr',
    workspace: '/home/exam/workspace'
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
        this.setProfessorUrl('/espace_prof/dashboard');
        setTimeout(() => this.refreshHeaderTeacherName(), 80);
        setTimeout(() => this.refreshHeaderTeacherName(), 350);
      this.publicPage = 'authentication';
      this.authenticatedPage = 'dashboard';

      setTimeout(() => {
        this.loadActivePackages();
        this.loadDashboard();
        this.loadCustomExamEnvironments();
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
    window.location.href = '/support';
  }



  openAuthenticationPage(): void {
    this.setProfessorUrl('/espace_prof/login');
    this.publicPage = 'authentication';
    this.refreshView();
  }

  openProfilePage(): void {
    this.setProfessorUrl('/espace_prof/profil');
    this.authenticatedPage = 'profile';
    this.error = '';
    this.success = '';
    this.refreshView();
  }

  openDashboardPage(): void {
    this.setProfessorUrl('/espace_prof/dashboard');
    this.authenticatedPage = 'dashboard';
    this.error = '';
    this.success = '';
    this.refreshView();
  }

  openDashboardSection(section: string): void {
    this.setProfessorUrl(this.getProfessorPathFromSection(section));
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
    this.loading = false;

    const cleanUsername = this.loginUsername.trim();
    const cleanPassword = this.loginPassword.trim();

    if (!cleanUsername) {
      this.loginError = 'Veuillez renseigner votre identifiant.';
      this.refreshView();
      return;
    }

    if (!cleanPassword) {
      this.loginError = 'Veuillez renseigner votre mot de passe.';
      this.refreshView();
      return;
    }

    this.loading = true;
    this.refreshView();

    const securityTimeout = window.setTimeout(() => {
      if (!this.loading) {
        return;
      }

      this.loading = false;
      this.loginError = 'Serveur injoignable. Vérifiez que le backend FastAPI est lancé.';
      this.refreshView();
    }, 8000);

    const payload = {
      username: cleanUsername,
      password: cleanPassword
    };

    this.http.post<{ access_token: string; token_type: string }>(
      `${this.apiUrl}/auth/login`,
      payload
    ).subscribe({
      next: (data) => {
        window.clearTimeout(securityTimeout);

        this.accessToken = data.access_token;
        this.isAuthenticated = true;
        this.loading = false;

        this.setProfessorUrl('/espace_prof/dashboard');

        setTimeout(() => this.refreshHeaderTeacherName(), 80);
        setTimeout(() => this.refreshHeaderTeacherName(), 350);

        this.publicPage = 'authentication';
        this.authenticatedPage = 'dashboard';

        localStorage.setItem('accessToken', data.access_token);
        setTimeout(() => this.refreshHeaderTeacherName(), 120);

        this.syncHeaderTeacherNameAfterLogin(data.access_token);
        window.dispatchEvent(new Event('secure-exam-authenticated'));

        this.loadActivePackages();
        this.loadDashboard();
        this.loadCustomExamEnvironments();
        this.refreshView();
      },
      error: (err) => {
        window.clearTimeout(securityTimeout);

        console.error(err);

        this.loading = false;

        if (err?.status === 0) {
          this.loginError = 'Connexion au serveur impossible. Vérifiez que le backend est lancé.';
        } else {
          this.loginError =
            err?.error?.detail || 'Connexion enseignant impossible.';
        }

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
    this.setProfessorUrl('/espace_prof/login');
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

          // SECUREEXAM_TEACHER_DELIVERY_LOAD_V2
          this.loadTeacherExamDeliveryStatus();

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

    const headers =
      this.getTeacherHeaders();


    this.http
      .get<PackageCatalogResponse>(
        `${this.apiUrl}/packages`,
        {
          headers
        }
      )
      .subscribe({

        next: data => {

          this.availablePackages =
            data.packages || [];


          /*
           * Au premier chargement, on sélectionne
           * l'environnement Python par défaut.
           *
           * On ne met PLUS automatiquement tous
           * les paquets actifs dans l'examen.
           */
          if (
            !this.environmentInitialized
          ) {

            const defaultEnvironment =
              this.examEnvironmentPresets.find(
                environment =>
                  environment.id
                  === 'python'
              );


            if (defaultEnvironment) {

              this.applyExamEnvironment(
                defaultEnvironment,
                false
              );
            }


            this.environmentInitialized =
              true;
          }


          this.enrichPackageVersions();

          this.packagesLoading =
            false;

          this.refreshView();
        },


        error: err => {

          console.error(
            err
          );

          this.error =
            'Impossible de charger la bibliothèque de logiciels.';

          this.packagesLoading =
            false;

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
    this.packagePage = 1;
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


  private normalizePackageKey(
    value: string
  ): string {

    return String(
      value || ''
    )
      .trim()
      .toLowerCase()
      .replace(
        /[\s_.-]+/g,
        ''
      );
  }


  private getRequirementAliases(
    requirement: string
  ): string[] {

    const key =
      this.normalizePackageKey(
        requirement
      );


    const aliases:
      Record<string, string[]> = {

      python3: [
        'python3',
        'python'
      ],

      gcc: [
        'gcc'
      ],

      gdb: [
        'gdb'
      ],

      gnumake: [
        'gnumake',
        'make'
      ],

      vim: [
        'vim'
      ],

      nano: [
        'nano'
      ],

      java: [
        'java',
        'jdk',
        'jdk17',
        'jdk21',
        'openjdk',
        'openjdk17',
        'openjdk21'
      ],

      maven: [
        'maven',
        'mvn'
      ],

      nodejs: [
        'nodejs',
        'node',
        'nodejs20',
        'nodejs22'
      ],

      npm: [
        'npm',
        'nodejs',
        'node'
      ],

      sqlite: [
        'sqlite',
        'sqlite3'
      ],

      postgresql: [
        'postgresql',
        'postgres',
        'postgresql16',
        'postgresql17'
      ]
    };


    return (
      aliases[key]
      || [requirement]
    ).map(
      value =>
        this.normalizePackageKey(
          value
        )
    );
  }


  findCatalogPackageForRequirement(
    requirement: string,
    activeOnly = true
  ):
    PackageCatalogItem | undefined {

    const aliases =
      this.getRequirementAliases(
        requirement
      );


    return this.availablePackages.find(
      packageItem => {

        if (
          activeOnly
          && !packageItem.isActive
        ) {
          return false;
        }


        const values = [
          packageItem.name,
          packageItem.nixName,
          packageItem.displayName
        ]
          .map(
            value =>
              this.normalizePackageKey(
                value
              )
          );


        return aliases.some(
          alias =>
            values.includes(
              alias
            )
        );
      }
    );
  }


  getEnvironmentMissingPackages(
    environment:
      ExamEnvironmentPreset
  ): string[] {

    return environment.packageRefs.filter(
      requirement =>
        !this.findCatalogPackageForRequirement(
          requirement,
          true
        )
    );
  }


  isEnvironmentReady(
    environment:
      ExamEnvironmentPreset
  ): boolean {

    return (
      this.getEnvironmentMissingPackages(
        environment
      ).length
      === 0
    );
  }


  getEnvironmentResolvedPackages(
    environment:
      ExamEnvironmentPreset
  ): string[] {

    const result:
      string[] = [];


    for (
      const requirement
      of environment.packageRefs
    ) {

      const packageItem =
        this.findCatalogPackageForRequirement(
          requirement,
          true
        );


      if (
        packageItem
        && !result.includes(
          packageItem.name
        )
      ) {

        result.push(
          packageItem.name
        );
      }
    }


    return result;
  }


  getEnvironmentPackageLabel(
    requirement: string
  ): string {

    const packageItem =
      this.findCatalogPackageForRequirement(
        requirement,
        false
      );


    if (packageItem) {

      return (
        packageItem.displayName
        || packageItem.name
      );
    }


    const labels:
      Record<string, string> = {

      python3:
        'Python 3',

      gcc:
        'GCC',

      gdb:
        'GDB',

      gnumake:
        'Make',

      vim:
        'Vim',

      nano:
        'Nano',

      java:
        'JDK',

      maven:
        'Maven',

      nodejs:
        'Node.js',

      npm:
        'npm',

      sqlite:
        'SQLite',

      postgresql:
        'PostgreSQL'
    };


    return (
      labels[requirement]
      || requirement
    );
  }


  applyExamEnvironment(
    environment:
      ExamEnvironmentPreset,
    customized = false
  ): void {

    this.selectedEnvironmentId =
      environment.id;


    this.selectedEnvironmentCustomized =
      customized;


    /*
     * IMPORTANT :
     * Un environnement logiciel ne modifie JAMAIS
     * sudo / internet / EDUC / domaines.
     *
     * Ces options restent dans la section
     * "Options autorisées" de l'examen.
     */
    this.newConfig.packages =
      this.getEnvironmentResolvedPackages(
        environment
      );


    this.error =
      '';


    this.refreshView();
  }



  resetCustomEnvironmentDraft(): void {

    /*
     * Abandon complet de toute configuration
     * personnalisée non finalisée.
     */

    this.customEnvironmentNameModalOpen =
      false;

    this.customEnvironmentName =
      '';

    this.customEnvironmentBaseId =
      null;

    this.customEnvironmentEditingId =
      null;

    this.customEnvironmentSaving =
      false;


    this.packageLibraryOpen =
      false;

    this.packageLibraryMode =
      'catalog';


    this.showPackageCreationForm =
      false;


    this.resetPackageTerminalState();


    document.body.style.overflow =
      '';


    this.selectedEnvironmentCustomized =
      false;


    this.error =
      '';
  }


  selectExamEnvironment(
    environment:
      ExamEnvironmentPreset
  ): void {

    const missing =
      this.getEnvironmentMissingPackages(
        environment
      );


    if (
      missing.length > 0
    ) {

      this.error =
        (
          'Configuration '
          + environment.title
          + ' indisponible. Il manque : '
          + missing
            .map(
              item =>
                this.getEnvironmentPackageLabel(
                  item
                )
            )
            .join(', ')
        );


      this.refreshView();

      return;
    }


    /*
     * Le professeur abandonne éventuellement
     * un brouillon personnalisé.
     *
     * Une config officielle repart TOUJOURS
     * de sa définition SecureExam propre.
     */
    this.resetCustomEnvironmentDraft();


    this.applyExamEnvironment(
      environment,
      false
    );


    this.refreshView();
  }



  customizeExamEnvironment(
    environment:
      ExamEnvironmentPreset
  ): void {

    const missing =
      this.getEnvironmentMissingPackages(
        environment
      );


    if (
      missing.length > 0
    ) {

      this.error =
        (
          'Impossible de personnaliser '
          + environment.title
          + '. Paquet(s) manquant(s) : '
          + missing
            .map(
              value =>
                this.getEnvironmentPackageLabel(
                  value
                )
            )
            .join(', ')
        );


      this.refreshView();

      return;
    }


    /*
     * On ne modifie JAMAIS le preset officiel.
     * On prépare une nouvelle config perso basée
     * sur celui-ci.
     */
    this.resetCustomEnvironmentDraft();


    this.customEnvironmentBaseId =
      environment.id;


    this.customEnvironmentName =
      `${environment.title} personnalisé`;


    this.customEnvironmentEditingId =
      null;


    this.customEnvironmentNameModalOpen =
      true;


    this.packageLibraryMode =
      'custom';


    this.refreshView();
  }




  createCustomExamEnvironment():
    void {

    /*
     * Une nouvelle configuration personnalisée
     * repart toujours de zéro.
     */
    this.resetCustomEnvironmentDraft();


    this.customEnvironmentName =
      '';


    this.customEnvironmentBaseId =
      null;


    this.customEnvironmentEditingId =
      null;


    this.customEnvironmentNameModalOpen =
      true;


    this.packageLibraryMode =
      'custom';


    this.error =
      '';


    this.refreshView();
  }




  get selectedEnvironment():
    ExamEnvironmentPreset | undefined {

    return this.examEnvironmentPresets.find(
      environment =>
        environment.id
        === this.selectedEnvironmentId
    );
  }


  get selectedEnvironmentTitle():
    string {

    if (
      this.selectedEnvironmentId
        .startsWith(
          'custom-'
        )
    ) {

      const id =
        Number(
          this.selectedEnvironmentId
            .replace(
              'custom-',
              ''
            )
        );


      const custom =
        this.customEnvironments
          .find(
            environment =>
              environment.id
              === id
          );


      if (custom) {

        return custom.name;
      }


      if (
        this.customEnvironmentName
          .trim()
      ) {

        return (
          this.customEnvironmentName
            .trim()
        );
      }


      return (
        'Configuration personnalisée'
      );
    }


    if (
      this.selectedEnvironmentId
      === 'custom-draft'
    ) {

      return (
        this.customEnvironmentName
          .trim()
        || 'Configuration personnalisée'
      );
    }


    const environment =
      this.selectedEnvironment;


    if (!environment) {

      return (
        'Configuration personnalisée'
      );
    }


    return (
      environment.title
      + (
          this.selectedEnvironmentCustomized
            ? ' · modifiée pour cet examen'
            : ''
        )
    );
  }



  getSelectedEnvironmentPackageNames():
    string[] {

    const activeNames =
      new Set(
        this.availablePackages
          .filter(
            packageItem =>
              packageItem.isActive
          )
          .map(
            packageItem =>
              packageItem.name
          )
      );


    return Array.from(
      new Set(
        this.newConfig.packages.filter(
          packageName =>
            activeNames.has(
              packageName
            )
        )
      )
    );
  }


  getSelectedEnvironmentPackageItems():
    PackageCatalogItem[] {

    const selected =
      new Set(
        this.newConfig.packages
      );


    return this.availablePackages.filter(
      packageItem =>
        selected.has(
          packageItem.name
        )
    );
  }



  openPackageTerminalPopup(
    context:
      'custom'
      | 'catalog'
  ): void {

    this.packageTerminalContext =
      context;


    this.resetPackageTerminalState();


    if (
      context
      === 'catalog'
    ) {
      this.packageTerminalCatalogPackages = [];
    }


    this.ensurePackageTerminalWelcome();


    this.packageTerminalPopupOpen =
      true;


    document.body.style.overflow =
      'hidden';


    this.refreshView();


    setTimeout(() => {

      const input =
        document.querySelector(
          '.secureexam-terminal-popup-modal .secureexam-package-terminal-inputbar input'
        ) as HTMLInputElement | null;


      input?.focus();

    }, 60);
  }


  closePackageTerminalPopup(): void {

    this.packageTerminalPopupOpen =
      false;


    this.packageTerminalCommand =
      '';


    if (
      !this.packageLibraryOpen
      && !this.customEnvironmentNameModalOpen
      && !this.myCustomEnvironmentsOpen
    ) {
      document.body.style.overflow = '';
    }


    this.refreshView();
  }


  removeCustomEnvironmentPackage(
    packageName: string
  ): void {

    this.newConfig.packages =
      this.newConfig.packages.filter(
        item =>
          item !== packageName
      );


    this.selectedEnvironmentCustomized =
      true;


    this.refreshView();
  }


  private resetPackageTerminalState(): void {

    this.packageTerminalCommand = '';
    this.packageTerminalLoading = false;
    this.packageTerminalChannel = 'unstable';
    this.packageTerminalHistory = [];
  }


  private ensurePackageTerminalWelcome(): void {

    if (
      this.packageTerminalHistory.length > 0
    ) {
      return;
    }


    this.packageTerminalHistory = [
      {
        kind: 'info',
        text:
          'Terminal prêt. Les paquets ajoutés sont vérifiés dans Nixpkgs avant leur utilisation.'
      },
      {
        kind: 'info',
        text:
          'Syntaxe : add <logiciel> [version] · remove <paquet> · list · clear · help'
      }
    ];
  }


  private scrollPackageTerminalToBottom(): void {

    setTimeout(() => {

      const terminal =
        document.querySelector(
          '.secureexam-package-terminal-screen'
        ) as HTMLElement | null;


      if (!terminal) {
        return;
      }


      terminal.scrollTop =
        terminal.scrollHeight;

    }, 30);
  }


  private upsertPackageTerminalItems(
    items: PackageTerminalItem[]
  ): void {

    for (const item of items || []) {

      if (!item?.name) {
        continue;
      }


      const existingIndex =
        this.availablePackages.findIndex(
          packageItem =>
            packageItem.name === item.name
            || packageItem.nixName === item.nixName
        );


      const existing =
        existingIndex >= 0
          ? this.availablePackages[existingIndex]
          : undefined;


      const normalized:
        PackageCatalogItem = {

        id:
          item.id,

        name:
          item.name,

        nixName:
          item.nixName || item.name,

        displayName:
          item.displayName || item.name,

        description:
          item.description || '',

        isActive:
          item.isActive !== false,

        version:
          item.version || existing?.version,

        verifiedNixPackage:
          item.nixName || item.name,

        createdAt:
          existing?.createdAt || '',

        updatedAt:
          existing?.updatedAt || ''
      };


      if (existingIndex >= 0) {

        this.availablePackages =
          this.availablePackages.map(
            (packageItem, index) =>
              index === existingIndex
                ? {
                    ...packageItem,
                    ...normalized
                  }
                : packageItem
          );

      } else {

        this.availablePackages = [
          ...this.availablePackages,
          normalized
        ];
      }
    }
  }


  setPackageTerminalCommand(
    command: string
  ): void {

    if (this.packageTerminalLoading) {
      return;
    }


    this.packageTerminalCommand =
      command;


    this.refreshView();


    setTimeout(() => {

      const input =
        document.querySelector(
          '.secureexam-terminal-popup-modal .secureexam-package-terminal-inputbar input'
        ) as HTMLInputElement | null;


      input?.focus();

    }, 30);
  }


  executePackageTerminalCommand(
    commandOverride?: string
  ): void {

    if (
      !this.packageTerminalPopupOpen
      || this.packageTerminalLoading
    ) {
      return;
    }


    const command =
      String(
        commandOverride
        ?? this.packageTerminalCommand
        ?? ''
      ).trim();


    if (!command) {
      return;
    }


    this.customEnvironmentModalError = '';
    this.error = '';


    this.packageTerminalHistory = [
      ...this.packageTerminalHistory,
      {
        kind: 'command',
        text: command
      }
    ];


    if (!commandOverride) {
      this.packageTerminalCommand = '';
    }


    this.packageTerminalLoading = true;

    this.refreshView();
    this.scrollPackageTerminalToBottom();


    const payload = {
      command,
      packages:
        this.packageTerminalContext
        === 'custom'
          ? [
              ...this.newConfig.packages
            ]
          : [
              ...this.packageTerminalCatalogPackages
            ]
    };


    this.http
      .post<PackageTerminalResponse>(
        `${this.apiUrl}/exam-environments/package-terminal`,
        payload,
        {
          headers:
            this.getTeacherHeaders()
        }
      )
      .subscribe({

        next: data => {

          this.packageTerminalLoading = false;


          this.packageTerminalChannel =
            data.channel
            || this.packageTerminalChannel
            || 'unstable';


          const resolvedPackages =
            Array.from(
              new Set(
                data.packages || []
              )
            );


          if (
            this.packageTerminalContext
            === 'custom'
          ) {

            this.newConfig.packages =
              resolvedPackages;

          } else {

            this.packageTerminalCatalogPackages =
              resolvedPackages;
          }


          const terminalItems = [
            ...(data.items || [])
          ];


          if (data.package) {

            const alreadyIncluded =
              terminalItems.some(
                item =>
                  item.name
                  === data.package!.name
              );


            if (!alreadyIncluded) {
              terminalItems.push(
                data.package
              );
            }
          }


          this.upsertPackageTerminalItems(
            terminalItems
          );


          if (
            this.packageTerminalContext
            === 'custom'
          ) {
            this.selectedEnvironmentCustomized =
              true;
          }


          this.packageTerminalHistory = [
            ...this.packageTerminalHistory,
            {
              kind:
                data.success
                  ? 'success'
                  : 'info',
              text:
                data.message
                || 'Commande exécutée.'
            }
          ];


          if (
            data.action === 'list'
            && (data.items || []).length > 0
          ) {

            this.packageTerminalHistory = [
              ...this.packageTerminalHistory,
              ...data.items.map(
                item => ({
                  kind: 'info' as PackageTerminalLineKind,
                  text:
                    `${item.displayName} → ${item.nixName}`
                })
              )
            ];
          }


          if (
            this.packageTerminalContext
            === 'catalog'
            && data.action
            === 'add'
          ) {
            this.loadActivePackages();
          }


          this.refreshView();
          this.scrollPackageTerminalToBottom();
        },


        error: err => {

          console.error(
            'PACKAGE TERMINAL ERROR',
            err
          );


          this.packageTerminalLoading = false;


          const detail =
            err?.error?.detail;


          let message =
            'Impossible d’exécuter cette commande.';


          if (
            typeof detail === 'string'
          ) {

            message = detail;

          } else if (
            detail?.message
          ) {

            message = detail.message;

          } else if (
            err?.status === 0
          ) {

            message =
              'Backend SecureExam injoignable sur le port 8000.';
          }


          this.packageTerminalHistory = [
            ...this.packageTerminalHistory,
            {
              kind: 'error',
              text: message
            }
          ];


          if (
            this.packageTerminalContext
            === 'custom'
          ) {
            this.customEnvironmentModalError =
              message;
          }


          this.refreshView();
          this.scrollPackageTerminalToBottom();
        }

      });
  }


  getCustomEnvironmentPackageNixName(
    packageName: string
  ): string {

    const packageItem =
      this.availablePackages.find(
        item =>
          item.name === packageName
          || item.nixName === packageName
      );


    return (
      packageItem?.nixName
      || packageName
    );
  }


  openPackageLibrary(): void {

    this.packageLibraryOpen =
      true;


    this.packageLibrarySearch =
      '';


    if (
      this.packageLibraryMode
      === 'custom'
    ) {

      this.ensurePackageTerminalWelcome();
    }


    document.body.style.overflow =
      'hidden';


    this.refreshView();


    this.refreshLucideIcons();
  }


  closePackageLibrary(): void {

    this.packageLibraryOpen =
      false;


    this.packageTerminalPopupOpen =
      false;


    document.body.style.overflow =
      '';


    this.refreshView();
  }


  get packageLibraryItems():
    PackageCatalogItem[] {

    const query =
      this.packageLibrarySearch
        .trim()
        .toLowerCase();


    if (!query) {

      return this.availablePackages;
    }


    return this.availablePackages.filter(
      packageItem => {

        const text =
          [
            packageItem.displayName,
            packageItem.name,
            packageItem.nixName,
            packageItem.description || ''
          ]
            .join(' ')
            .toLowerCase();


        return text.includes(
          query
        );
      }
    );
  }


  isPackageSelectedInEnvironment(
    packageItem:
      PackageCatalogItem
  ): boolean {

    return this.newConfig.packages.includes(
      packageItem.name
    );
  }


  toggleEnvironmentPackage(
    packageItem:
      PackageCatalogItem
  ): void {

    /*
     * Le catalogue général ne modifie jamais
     * la configuration sélectionnée.
     */
    if (
      this.packageLibraryMode
      !== 'custom'
    ) {

      return;
    }


    if (
      !packageItem.isActive
    ) {

      return;
    }


    const packages =
      new Set(
        this.newConfig.packages
      );


    if (
      packages.has(
        packageItem.name
      )
    ) {

      packages.delete(
        packageItem.name
      );

    } else {

      packages.add(
        packageItem.name
      );
    }


    this.newConfig.packages =
      Array.from(
        packages
      );


    this.selectedEnvironmentCustomized =
      true;


    this.refreshView();
  }




  finishPackageLibrarySelection():
    void {

    /*
     * En mode catalogue, aucun changement de
     * configuration d'examen.
     */
    if (
      this.packageLibraryMode
      === 'catalog'
    ) {

      this.closePackageLibrary();

      return;
    }


    const packages =
      this.getSelectedEnvironmentPackageNames();


    if (
      packages.length === 0
    ) {

      this.error =
        (
          'Sélectionnez au moins un logiciel '
          + 'pour cette configuration.'
        );


      this.refreshView();

      return;
    }


    this.newConfig.packages =
      packages;


    /*
     * Configuration personnalisée sauvegardée.
     */
    if (
      this.customEnvironmentName
        .trim()
    ) {

      this.saveCurrentCustomEnvironment();

      return;
    }


    this.error =
      '';


    this.closePackageLibrary();
  }




  closeCustomEnvironmentNameModal():
    void {

    this.customEnvironmentNameModalOpen =
      false;


    this.customEnvironmentBaseId =
      null;


    this.customEnvironmentEditingId =
      null;


    this.customEnvironmentName =
      '';


    this.refreshView();
  }


  private normalizeCustomEnvironmentNameForComparison(
    value: string
  ): string {

    return String(
      value
      || ''
    )
      .trim()
      .toLowerCase()
      .replace(
        /[^a-z0-9+]+/g,
        ''
      );
  }


  getCustomEnvironmentNameValidationMessage():
    string {

    const name =
      this.customEnvironmentName
        .trim();


    if (!name) {

      return '';
    }


    const normalized =
      this.normalizeCustomEnvironmentNameForComparison(
        name
      );


    /*
     * Noms officiels SecureExam.
     */
    const officialConflict =
      this.examEnvironmentPresets
        .find(
          environment =>
            this.normalizeCustomEnvironmentNameForComparison(
              environment.title
            )
            === normalized
        );


    if (officialConflict) {

      return (
        `Le nom "${officialConflict.title}" `
        + 'est réservé à une configuration '
        + 'officielle SecureExam.'
      );
    }


    /*
     * Noms personnalisés déjà utilisés
     * par CE professeur.
     *
     * En modification, le nom actuel
     * reste évidemment autorisé.
     */
    const customConflict =
      this.customEnvironments
        .find(
          environment => {

            if (
              this.customEnvironmentEditingId
              !== null
              && environment.id
              === this.customEnvironmentEditingId
            ) {

              return false;
            }


            return (
              this
                .normalizeCustomEnvironmentNameForComparison(
                  environment.name
                )
              === normalized
            );
          }
        );


    if (customConflict) {

      return (
        `Vous avez déjà une configuration `
        + `"${customConflict.name}".`
      );
    }


    return '';
  }


  confirmCustomEnvironmentName():
    void {

    const name =
      this.customEnvironmentName
        .trim();


    this.customEnvironmentModalError =
      '';


    if (!name) {

      this.customEnvironmentModalError =
        (
          'Donnez un nom à la '
          + 'configuration personnalisée.'
        );


      this.refreshView();

      return;
    }


    if (
      name.length > 80
    ) {

      this.customEnvironmentModalError =
        (
          'Le nom ne peut pas dépasser '
          + '80 caractères.'
        );


      this.refreshView();

      return;
    }


    const validationMessage =
      this
        .getCustomEnvironmentNameValidationMessage();


    if (validationMessage) {

      this.customEnvironmentModalError =
        validationMessage;


      this.refreshView();

      return;
    }


    /*
     * Modification d'une config perso existante :
     * ses paquets ont déjà été chargés.
     */
    if (
      this.customEnvironmentEditingId
      !== null
    ) {

      this.selectedEnvironmentId =
        `custom-${this.customEnvironmentEditingId}`;

    }


    /*
     * Personnalisation d'un preset officiel.
     */
    else if (
      this.customEnvironmentBaseId
    ) {

      const base =
        this.examEnvironmentPresets
          .find(
            environment =>
              environment.id
              === this.customEnvironmentBaseId
          );


      if (!base) {

        this.customEnvironmentModalError =
          (
            'La configuration de base '
            + 'est introuvable.'
          );


        this.refreshView();

        return;
      }


      this.newConfig.packages =
        this.getEnvironmentResolvedPackages(
          base
        );


      this.selectedEnvironmentId =
        'custom-draft';

    }


    /*
     * Nouvelle configuration personnelle.
     */
    else {

      this.newConfig.packages =
        [];


      this.selectedEnvironmentId =
        'custom-draft';
    }


    this.selectedEnvironmentCustomized =
      true;


    this.packageLibraryMode =
      'custom';


    this.customEnvironmentNameModalOpen =
      false;


    this.resetPackageTerminalState();


    this.error =
      '';


    this.openPackageLibrary();


    this.refreshView();
  }




  openPackageCatalog(): void {

    this.packageLibraryMode =
      'catalog';


    this.showPackageCreationForm =
      false;


    this.openPackageLibrary();
  }


  openCustomDraftLibrary(): void {

    if (
      this.selectedEnvironmentId
      !== 'custom-draft'
    ) {

      return;
    }


    this.packageLibraryMode =
      'custom';


    this.openPackageLibrary();
  }


  openCurrentExamPackageLibrary():
    void {

    /*
     * Ancien comportement supprimé :
     * une configuration officielle ne peut plus
     * être modifiée directement pour un examen.
     *
     * Ce bouton ouvre désormais uniquement
     * le catalogue logiciel.
     */
    this.openPackageCatalog();
  }



  loadCustomExamEnvironments():
    void {

    if (!this.accessToken) {

      return;
    }


    this.customEnvironmentsLoading =
      true;


    this.http
      .get<CustomExamEnvironmentListResponse>(
        (
          `${this.apiUrl}`
          + '/exam-environments/custom'
        ),
        {
          headers:
            this.getTeacherHeaders()
        }
      )
      .subscribe({

        next: data => {

          this.customEnvironments =
            data.environments
            || [];


          this.customEnvironmentsLoading =
            false;


          this.refreshView();
        },


        error: err => {

          console.error(
            err
          );


          this.customEnvironmentsLoading =
            false;


          this.refreshView();
        }

      });
  }


  openMyCustomEnvironments():
    void {

    this.myCustomEnvironmentsOpen =
      true;


    this.loadCustomExamEnvironments();


    document.body.style.overflow =
      'hidden';


    this.refreshView();
  }


  closeMyCustomEnvironments():
    void {

    this.myCustomEnvironmentsOpen =
      false;


    document.body.style.overflow =
      '';


    this.refreshView();
  }


  useCustomExamEnvironment(
    environment:
      CustomExamEnvironment
  ): void {

    const activeNames =
      new Set(
        this.availablePackages
          .filter(
            packageItem =>
              packageItem.isActive
          )
          .map(
            packageItem =>
              packageItem.name
          )
      );


    const missing =
      environment.packages
        .filter(
          packageName =>
            !activeNames.has(
              packageName
            )
        );


    if (
      missing.length > 0
    ) {

      this.error =
        (
          'Cette configuration utilise '
          + 'des logiciels actuellement '
          + 'indisponibles : '
          + missing.join(', ')
        );


      this.refreshView();

      return;
    }


    this.newConfig.packages =
      [
        ...environment.packages
      ];


    this.selectedEnvironmentId =
      `custom-${environment.id}`;


    this.selectedEnvironmentCustomized =
      false;


    this.customEnvironmentEditingId =
      null;


    this.customEnvironmentName =
      '';


    this.closeMyCustomEnvironments();


    this.refreshView();
  }


  editCustomExamEnvironment(
    environment:
      CustomExamEnvironment
  ): void {

    this.resetPackageTerminalState();


    /*
     * Charger immédiatement les paquets existants.
     * Ils seront conservés pendant la modification
     * du nom.
     */
    this.newConfig.packages = [
      ...environment.packages
    ];


    this.selectedEnvironmentId =
      `custom-${environment.id}`;


    this.selectedEnvironmentCustomized =
      true;


    /*
     * ID existant = le save fera un PUT
     * et non un nouveau POST.
     */
    this.customEnvironmentEditingId =
      environment.id;


    /*
     * Nom actuel prérempli dans la popup.
     */
    this.customEnvironmentName =
      environment.name;


    this.customEnvironmentBaseId =
      null;


    this.customEnvironmentModalError =
      '';


    /*
     * Fermer "Mes configurations"
     * avant d'ouvrir l'éditeur.
     */
    this.myCustomEnvironmentsOpen =
      false;


    this.packageLibraryOpen =
      false;


    this.packageLibraryMode =
      'custom';


    /*
     * Première étape de modification :
     * le professeur peut changer le nom.
     */
    this.customEnvironmentNameModalOpen =
      true;


    document.body.style.overflow =
      'hidden';


    this.refreshView();


    setTimeout(() => {

      this.refreshLucideIcons();

    }, 50);
  }



  deleteCustomExamEnvironment(
    environment:
      CustomExamEnvironment
  ): void {

    const confirmed =
      window.confirm(
        (
          'Supprimer définitivement '
          + `la configuration "${environment.name}" ?`
        )
      );


    if (!confirmed) {

      return;
    }


    this.error =
      '';


    this.http
      .delete<any>(
        (
          `${this.apiUrl}`
          + '/exam-environments/custom/'
          + environment.id
        ),
        {
          headers:
            this.getTeacherHeaders()
        }
      )
      .subscribe({

        next: response => {

          /*
           * La carte disparaît immédiatement.
           */
          this.customEnvironments =
            this.customEnvironments
              .filter(
                item =>
                  item.id
                  !== environment.id
              );


          /*
           * Si la config supprimée était sélectionnée,
           * retour propre sur Python.
           */
          if (
            this.selectedEnvironmentId
            === `custom-${environment.id}`
          ) {

            const defaultEnvironment =
              this.examEnvironmentPresets
                .find(
                  item =>
                    item.id
                    === 'python'
                );


            this.selectedEnvironmentId =
              'python';


            this.selectedEnvironmentCustomized =
              false;


            this.customEnvironmentName =
              '';


            this.customEnvironmentEditingId =
              null;


            this.customEnvironmentBaseId =
              null;


            if (
              defaultEnvironment
            ) {

              this.applyExamEnvironment(
                defaultEnvironment,
                false
              );
            }
          }


          /*
           * Si elle était actuellement en édition,
           * on ferme aussi l'éditeur.
           */
          if (
            this.customEnvironmentEditingId
            === environment.id
          ) {

            this.customEnvironmentEditingId =
              null;


            this.customEnvironmentName =
              '';


            this.customEnvironmentBaseId =
              null;


            this.customEnvironmentNameModalOpen =
              false;


            this.packageLibraryOpen =
              false;


            document.body.style.overflow =
              '';
          }


          this.success =
            response?.message
            || (
              'Configuration personnalisée '
              + 'supprimée.'
            );


          this.error =
            '';


          /*
           * Confirmation depuis SQLite.
           */
          this.loadCustomExamEnvironments();


          this.refreshView();
        },


        error: err => {

          console.error(
            'CUSTOM ENVIRONMENT DELETE ERROR',
            err
          );


          const detail =
            err?.error?.detail;


          if (
            typeof detail
            === 'string'
          ) {

            this.error =
              detail;

          } else if (
            detail?.message
          ) {

            this.error =
              detail.message;

          } else if (
            err?.status === 404
          ) {

            this.error =
              (
                'La configuration est introuvable '
                + 'ou ne vous appartient pas.'
              );

          } else if (
            err?.status === 401
            || err?.status === 403
          ) {

            this.error =
              (
                'Votre session professeur '
                + 'a expiré.'
              );

          } else {

            this.error =
              (
                'Impossible de supprimer '
                + 'la configuration personnalisée.'
              );
          }


          this.refreshView();
        }

      });
  }



  saveCurrentCustomEnvironment():
    void {

    const name =
      this.customEnvironmentName
        .trim();


    const packages =
      this.getSelectedEnvironmentPackageNames();


    this.customEnvironmentModalError =
      '';


    if (!name) {

      this.customEnvironmentModalError =
        (
          'Donnez un nom à la '
          + 'configuration personnalisée.'
        );

      this.refreshView();

      return;
    }


    if (
      packages.length === 0
    ) {

      this.customEnvironmentModalError =
        (
          'Sélectionnez au moins '
          + 'un logiciel.'
        );

      this.refreshView();

      return;
    }


    const token =
      this.accessToken
      || localStorage.getItem(
        'accessToken'
      )
      || '';


    if (!token) {

      this.customEnvironmentModalError =
        (
          'Votre session professeur '
          + 'a expiré. Reconnectez-vous.'
        );

      this.refreshView();

      return;
    }


    const headers =
      new HttpHeaders({
        Authorization:
          `Bearer ${token}`
      });


    const payload = {

      name:
        name,

      packages:
        packages

    };


    this.customEnvironmentSaving =
      true;


    this.refreshView();


    const url =
      this.customEnvironmentEditingId
        ? (
            `${this.apiUrl}`
            + '/exam-environments/custom/'
            + this.customEnvironmentEditingId
          )
        : (
            `${this.apiUrl}`
            + '/exam-environments/custom'
          );


    const request =
      this.customEnvironmentEditingId
        ? this.http.put<any>(
            url,
            payload,
            {
              headers
            }
          )
        : this.http.post<any>(
            url,
            payload,
            {
              headers
            }
          );


    request.subscribe({

      next: response => {

        this.customEnvironmentSaving =
          false;


        const saved =
          response?.environment;


        if (
          !saved
          || !saved.id
        ) {

          this.customEnvironmentModalError =
            (
              'Le serveur n’a pas retourné '
              + 'la configuration enregistrée.'
            );

          this.refreshView();

          return;
        }


        /*
         * 1. La carte apparaît immédiatement.
         */
        const existingIndex =
          this.customEnvironments.findIndex(
            environment =>
              environment.id
              === saved.id
          );


        if (
          existingIndex >= 0
        ) {

          this.customEnvironments =
            this.customEnvironments.map(
              environment =>
                environment.id
                === saved.id
                  ? saved
                  : environment
            );

        } else {

          this.customEnvironments = [
            saved,
            ...this.customEnvironments
          ];
        }


        /*
         * 2. Elle devient immédiatement
         *    la configuration sélectionnée.
         */
        this.selectedEnvironmentId =
          `custom-${saved.id}`;


        this.selectedEnvironmentCustomized =
          false;


        this.newConfig.packages = [
          ...saved.packages
        ];


        /*
         * 3. Fermer réellement la popup.
         */
        this.packageLibraryOpen =
          false;


        this.packageLibraryMode =
          'catalog';


        this.showPackageCreationForm =
          false;


        document.body.style.overflow =
          '';


        /*
         * 4. Nettoyer uniquement le brouillon.
         *    La configuration sélectionnée reste.
         */
        this.customEnvironmentEditingId =
          null;


        this.customEnvironmentBaseId =
          null;


        this.customEnvironmentName =
          '';


        this.customEnvironmentModalError =
          '';


        this.success =
          response?.message
          || (
            'Configuration personnalisée '
            + 'enregistrée.'
          );


        this.error =
          '';


        this.refreshView();


        /*
         * Recharger depuis SQLite pour confirmer
         * que la liste locale correspond au backend.
         */
        this.loadCustomExamEnvironments();


        setTimeout(() => {

          this.refreshLucideIcons();

        }, 50);
      },


      error: err => {

        console.error(
          'CUSTOM ENVIRONMENT SAVE ERROR',
          err
        );


        this.customEnvironmentSaving =
          false;


        const detail =
          err?.error?.detail;


        if (
          typeof detail
          === 'string'
        ) {

          this.customEnvironmentModalError =
            detail;

        } else if (
          detail?.message
        ) {

          this.customEnvironmentModalError =
            detail.message;

        } else if (
          err?.status === 404
        ) {

          this.customEnvironmentModalError =
            (
              'La route de sauvegarde des '
              + 'configurations personnalisées '
              + 'est introuvable sur le backend.'
            );

        } else if (
          err?.status === 401
          || err?.status === 403
        ) {

          this.customEnvironmentModalError =
            (
              'Session professeur expirée. '
              + 'Reconnectez-vous.'
            );

        } else if (
          err?.status === 0
        ) {

          this.customEnvironmentModalError =
            (
              'Impossible de joindre le backend '
              + 'SecureExam sur le port 8000.'
            );

        } else {

          this.customEnvironmentModalError =
            (
              'Impossible d’enregistrer '
              + 'la configuration personnalisée.'
            );
        }


        this.error =
          this.customEnvironmentModalError;


        this.refreshView();
      }

    });
  }



  togglePackageCreationForm(): void {

    /*
     * L'ancien formulaire manuel est remplacé
     * par le terminal Nixpkgs en popup.
     */
    this.showPackageCreationForm =
      false;


    this.resetPackageVerification();


    this.openPackageTerminalPopup(
      'catalog'
    );
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

        // AUTO_SELECT_CREATED_LIBRARY_PACKAGE
        if (
          this.packageLibraryOpen
          && this.packageLibraryMode === 'custom'
          && data.package
          && data.package.isActive
          && !this.newConfig.packages.includes(
            data.package.name
          )
        ) {

          this.newConfig.packages = [
            ...this.newConfig.packages,
            data.package.name
          ];
        }

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



  private normalizeStudentRosterHeader(
    value: string
  ): string {

    return String(
      value || ''
    )
      .normalize('NFD')
      .replace(
        /[\u0300-\u036f]/g,
        ''
      )
      .toLowerCase()
      .replace(
        /[^a-z0-9]+/g,
        '_'
      )
      .replace(
        /^_+|_+$/g,
        ''
      );
  }


  private parseStudentRosterCsvLine(
    line: string,
    delimiter: string
  ): string[] {

    const result: string[] = [];

    let current = '';
    let quoted = false;


    for (
      let index = 0;
      index < line.length;
      index++
    ) {

      const char =
        line[index];


      if (char === '"') {

        if (
          quoted
          && line[index + 1]
          === '"'
        ) {

          current += '"';
          index++;

        } else {

          quoted = !quoted;
        }

        continue;
      }


      if (
        char === delimiter
        && !quoted
      ) {

        result.push(
          current.trim()
        );

        current = '';

        continue;
      }


      current += char;
    }


    result.push(
      current.trim()
    );


    return result;
  }


  onStudentRosterSelected(
    event: Event
  ): void {

    this.studentRosterError = '';
    this.studentRosterCount = 0;
    this.studentRosterPreview = [];

    const input =
      event.currentTarget as HTMLInputElement;

    const file =
      input.files?.[0]
      || null;


    if (!file) {

      this.studentRosterFile = null;
      this.studentRosterFilename = '';

      this.refreshView();

      return;
    }


    if (
      !file.name
        .toLowerCase()
        .endsWith('.csv')
    ) {

      this.studentRosterFile = null;

      this.studentRosterError =
        'Le fichier doit être au format CSV.';

      input.value = '';

      this.refreshView();

      return;
    }


    this.studentRosterFile = file;

    this.studentRosterFilename =
      file.name;


    const reader =
      new FileReader();


    reader.onload = () => {

      const content =
        String(
          reader.result || ''
        );


      const lines =
        content
          .split(/\r?\n/)
          .map(
            line =>
              line.trim()
          )
          .filter(
            line =>
              line.length > 0
          );


      if (
        lines.length < 2
      ) {

        this.studentRosterError =
          'Le CSV ne contient aucun étudiant.';

        this.studentRosterCount = 0;

        this.refreshView();

        return;
      }


      const firstLine =
        lines[0];


      const delimiter =
        (
          firstLine.split(';').length
          >
          firstLine.split(',').length
        )
          ? ';'
          : ',';


      const headers =
        this.parseStudentRosterCsvLine(
          firstLine,
          delimiter
        )
          .map(
            value =>
              this.normalizeStudentRosterHeader(
                value
              )
          );


      const numberAliases = [
        'student_number',
        'numero_etudiant',
        'num_etudiant',
        'student_id',
        'identifiant',
        'numero'
      ];

      const nameAliases = [
        'full_name',
        'nom_complet',
        'nom_prenom',
        'name'
      ];

      const emailAliases = [
        'email',
        'mail',
        'adresse_email'
      ];


      const findIndex = (
        aliases: string[]
      ): number => {

        for (
          const alias
          of aliases
        ) {

          const index =
            headers.indexOf(
              alias
            );

          if (
            index >= 0
          ) {
            return index;
          }
        }

        return -1;
      };


      const numberIndex =
        findIndex(
          numberAliases
        );

      const nameIndex =
        findIndex(
          nameAliases
        );

      const emailIndex =
        findIndex(
          emailAliases
        );


      const firstNameIndex =
        headers.indexOf(
          'prenom'
        ) >= 0
          ? headers.indexOf(
              'prenom'
            )
          : headers.indexOf(
              'first_name'
            );


      const lastNameIndex =
        headers.indexOf(
          'nom'
        ) >= 0
          ? headers.indexOf(
              'nom'
            )
          : headers.indexOf(
              'last_name'
            );


      if (
        numberIndex < 0
        || emailIndex < 0
        || (
          nameIndex < 0
          && (
            firstNameIndex < 0
            || lastNameIndex < 0
          )
        )
      ) {

        this.studentRosterError =
          (
            'Colonnes obligatoires : '
            + 'student_number, full_name, email.'
          );

        this.studentRosterCount = 0;

        this.refreshView();

        return;
      }


      const preview:
        Array<{
          student_number: string;
          full_name: string;
          email: string;
        }> = [];


      const seen =
        new Set<string>();


      for (
        let index = 1;
        index < lines.length;
        index++
      ) {

        const values =
          this.parseStudentRosterCsvLine(
            lines[index],
            delimiter
          );


        const studentNumber =
          String(
            values[
              numberIndex
            ]
            || ''
          ).trim();


        let fullName = '';

        if (
          nameIndex >= 0
        ) {

          fullName =
            String(
              values[
                nameIndex
              ]
              || ''
            ).trim();

        } else {

          fullName =
            (
              String(
                values[
                  firstNameIndex
                ]
                || ''
              ).trim()
              + ' '
              + String(
                values[
                  lastNameIndex
                ]
                || ''
              ).trim()
            ).trim();
        }


        const email =
          String(
            values[
              emailIndex
            ]
            || ''
          ).trim();


        if (
          !studentNumber
          && !fullName
          && !email
        ) {
          continue;
        }


        if (
          !studentNumber
          || !fullName
          || !email
          || !email.includes('@')
        ) {

          this.studentRosterError =
            (
              `Ligne ${index + 1} `
              + 'du CSV invalide.'
            );

          this.studentRosterCount = 0;

          this.refreshView();

          return;
        }


        const key =
          studentNumber.toLowerCase();


        if (
          seen.has(key)
        ) {

          this.studentRosterError =
            (
              'Étudiant dupliqué : '
              + studentNumber
            );

          this.studentRosterCount = 0;

          this.refreshView();

          return;
        }


        seen.add(key);


        preview.push({
          student_number:
            studentNumber,

          full_name:
            fullName,

          email:
            email
        });
      }


      if (
        preview.length === 0
      ) {

        this.studentRosterError =
          'Le CSV ne contient aucun étudiant.';

        this.studentRosterCount = 0;

        this.refreshView();

        return;
      }


      this.studentRosterCount =
        preview.length;

      this.studentRosterPreview =
        preview.slice(
          0,
          6
        );


      this.refreshView();
    };


    reader.onerror = () => {

      this.studentRosterError =
        'Impossible de lire le fichier CSV.';

      this.studentRosterCount = 0;

      this.refreshView();
    };


    reader.readAsText(
      file,
      'UTF-8'
    );
  }


  clearStudentRoster(): void {

    this.studentRosterFile = null;
    this.studentRosterFilename = '';
    this.studentRosterCount = 0;
    this.studentRosterError = '';
    this.studentRosterPreview = [];

    const input =
      document.querySelector(
        '.student-roster-input'
      ) as HTMLInputElement | null;

    if (input) {
      input.value = '';
    }

    this.refreshView();
  }


  downloadStudentRosterTemplate(): void {

    const content =
      [
        'student_number,full_name,email',
        'etu001,Etudiant Test,etu001@isen.fr',
        'etu002,Jean Dupont,jean.dupont@isen.fr'
      ].join('\n');


    const blob =
      new Blob(
        [content],
        {
          type:
            'text/csv;charset=utf-8'
        }
      );


    this.saveBlob(
      blob,
      'modele_etudiants_secureexam.csv'
    );
  }


  executeCreateConfig(): void {

    this.error = '';
    this.success = '';


    const selectedPackageNames =
      this.getSelectedEnvironmentPackageNames();


    if (
      selectedPackageNames.length
      === 0
    ) {

      this.error =
        'Sélectionnez au moins un logiciel pour cet examen.';

      this.refreshView();

      return;
    }


    const rosterFile =
      this.studentRosterFile;


    if (
      !rosterFile
      || !this.hasValidStudentRoster
    ) {

      this.error =
        (
          'Le fichier CSV des étudiants '
          + 'est obligatoire.'
        );

      this.refreshView();

      return;
    }


    const formData =
      new FormData();


    formData.append(
      'exam_id',
      this.newConfig.exam_id
    );

    formData.append(
      'exam_name',
      (
        this.newConfig.exam_name
        || this.newConfig.exam_id
      )
    );

    formData.append(
      'exam_date',
      this.newConfig.exam_date
    );

    formData.append(
      'exam_time',
      this.newConfig.exam_time
    );

    formData.append(
      'packages_json',
      JSON.stringify(
        selectedPackageNames
      )
    );

    formData.append(
      'sudo',
      String(
        this.newConfig.sudo
      )
    );

    formData.append(
      'internet',
      String(
        this.newConfig.internet
      )
    );

    formData.append(
      'educ_access',
      String(
        this.newConfig.educ_access
      )
    );

    formData.append(
      'allowed_domains_json',
      JSON.stringify(
        this.newConfig.allowed_domains_text
          .split(',')
          .map(
            domain =>
              domain.trim()
          )
          .filter(
            domain =>
              domain.length > 0
          )
      )
    );

    formData.append(
      'roster_file',
      rosterFile,
      rosterFile.name
    );


    const headers =
      this.getTeacherHeaders();


    this.loading = true;


    this.http.post<any>(
      `${this.apiUrl}/configs`,
      formData,
      {
        headers
      }
    )
      .subscribe({

        next: (data) => {

          this.loading = false;

          this.success =
            (
              'Configuration créée avec succès. '
              + `${data?.roster?.students_count || this.studentRosterCount} `
              + 'étudiant(s) enregistrés.'
            );


          this.clearStudentRoster();

          this.loadDashboard();

          this.refreshView();
        },


        error: (err) => {

          console.error(
            err
          );


          this.loading = false;


          const configErrorMessage =
            this.getApiErrorMessage(
              err,
              (
                'Erreur lors de la création '
                + 'de la configuration.'
              )
            );


          if (
            err.status === 409
          ) {

            window.alert(
              configErrorMessage
            );
          }


          this.error =
            configErrorMessage;


          if (
            err.error?.detail?.message
            === 'Paquets non autorisés'
          ) {

            const invalidPackages =
              err.error.detail
                .invalid_packages
                ?.join(', ')
              || '';


            this.error =
              (
                'Paquets non autorisés : '
                + invalidPackages
              );
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
    const studentId = encodeURIComponent(machine.student_id || 'GLOBAL');
    const machineId = encodeURIComponent(machine.machine_id || 'ALL_MACHINES');

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



  private getNixosTargetConfig(): ExamConfigFile | undefined {

    const configs =
      this.dashboard?.configs || [];

    if (configs.length === 0) {
      return undefined;
    }

    /*
     * Le dashboard renvoie les configurations
     * de la plus récente à la plus ancienne.
     *
     * La section NixOS travaille donc sur
     * la dernière configuration générée.
     */
    return configs[0];
  }


  viewNixosConfig(): void {

    this.error = '';

    const config =
      this.getNixosTargetConfig();

    if (!config) {

      this.error =
        'Aucune configuration d’examen disponible.';

      this.refreshView();

      return;
    }

    const headers =
      this.getTeacherHeaders();

    const filename =
      encodeURIComponent(
        config.filename
      );

    this.http.get<NixosConfig>(
      `${this.apiUrl}/configs/${filename}/nixos-config`,
      {
        headers
      }
    ).subscribe({

      next: (data) => {

        this.nixosConfig = data;

        this.refreshView();
      },

      error: (err) => {

        console.error(err);

        this.error =
          'Impossible de générer la configuration NixOS pour cet examen.';

        this.refreshView();
      }

    });
  }


  closeNixosConfig(): void {

    this.nixosConfig = undefined;

    this.refreshLucideIcons();
  }





  // ======================================================
  // TÉLÉCHARGER CONFIGURATION JSON
  // ======================================================

  downloadConfig(
    config: ExamConfigFile
  ): void {

    this.error = '';

    const headers =
      this.getTeacherHeaders();

    const filename =
      encodeURIComponent(
        config.filename
      );

    this.http.get(
      `${this.apiUrl}/configs/${filename}/download`,
      {
        headers,
        responseType: 'blob'
      }
    ).subscribe({

      next: (blob) => {

        this.saveBlob(
          blob,
          config.filename
        );

        this.refreshLucideIcons();
      },

      error: (err) => {

        console.error(err);

        this.error =
          'Impossible de télécharger la configuration.';

        this.refreshView();
      }

    });
  }


  // ======================================================
  // TÉLÉCHARGER CONFIGURATION NIXOS
  // ======================================================

  downloadNixosConfig(): void {

    this.error = '';

    const configs =
      this.dashboard?.configs || [];

    if (configs.length === 0) {

      this.error =
        'Aucune configuration d’examen disponible.';

      this.refreshView();

      return;
    }

    /*
     * La liste des configurations est triée
     * de la plus récente à la plus ancienne.
     */
    const config = configs[0];

    const headers =
      this.getTeacherHeaders();

    const filename =
      encodeURIComponent(
        config.filename
      );

    this.http.get(
      `${this.apiUrl}/configs/${filename}/nixos-config/download`,
      {
        headers,
        responseType: 'blob'
      }
    ).subscribe({

      next: (blob) => {

        const nixFilename =
          config.filename
            .replace(
              /\.json$/i,
              ''
            )
          + '_exam-configuration.nix';

        this.saveBlob(
          blob,
          nixFilename
        );

        this.refreshLucideIcons();
      },

      error: (err) => {

        console.error(err);

        this.error =
          'Impossible de télécharger la configuration NixOS.';

        this.refreshView();
      }

    });
  }


  // ======================================================
  // TÉLÉCHARGER UNE SOUMISSION
  // ======================================================

  downloadSubmission(
    submission: any
  ): void {

    this.error = '';

    const filename =
      submission?.filename;

    if (!filename) {

      this.error =
        'Fichier de soumission introuvable.';

      this.refreshView();

      return;
    }

    const headers =
      this.getTeacherHeaders();

    const safeFilename =
      encodeURIComponent(
        filename
      );

    this.http.get(
      `${this.apiUrl}/submissions/${safeFilename}/download`,
      {
        headers,
        responseType: 'blob'
      }
    ).subscribe({

      next: (blob) => {

        this.saveBlob(
          blob,
          filename
        );

        this.refreshLucideIcons();
      },

      error: (err) => {

        console.error(err);

        this.error =
          'Impossible de télécharger la soumission.';

        this.refreshView();
      }

    });
  }



  // ======================================================
  // SECUREEXAM_TEACHER_DELIVERY_METHODS_V3
  // ======================================================

  loadTeacherExamDeliveryStatus(): void {

    if (
      !this.dashboard
      || !this.accessToken
    ) {
      return;
    }

    const headers =
      this.getTeacherHeaders();

    this.http.get<any[]>(
      `${this.apiUrl}/teacher/exam-delivery`,
      {
        headers
      }
    ).subscribe({

      next: (items) => {

        const deliveryByExam =
          new Map<string, any>();

        for (
          const item
          of items || []
        ) {

          const examId =
            String(
              item?.exam_id
              || ''
            ).trim();

          if (examId) {

            deliveryByExam.set(
              examId,
              item
            );
          }
        }


        if (this.dashboard) {

          this.dashboard.configs =
            (
              this.dashboard.configs
              || []
            ).map(
              config => {

                const examId =
                  String(
                    config.exam_id
                    || config.filename.replace(
                      /\.json$/i,
                      ''
                    )
                    || ''
                  ).trim();


                const delivery =
                  deliveryByExam.get(
                    examId
                  );


                if (!delivery) {

                  return {
                    ...config,

                    roster_count:
                      config.roster_count
                      || 0,

                    roster_status:
                      config.roster_status
                      || 'READY',

                    sent_at:
                      config.sent_at
                      || null
                  };
                }


                return {
                  ...config,

                  delivery_config_id:
                    delivery.config_id,

                  roster_filename:
                    delivery.roster_filename
                    || null,

                  roster_count:
                    Number(
                      delivery.roster_count
                      || 0
                    ),

                  roster_status:
                    String(
                      delivery.roster_status
                      || 'READY'
                    ),

                  sent_at:
                    delivery.sent_at
                    || null
                };
              }
            );
        }


        this.refreshView();
      },


      error: (err) => {

        console.error(
          'Erreur statut diffusion professeur',
          err
        );

        this.refreshView();
      }

    });
  }



  isTeacherExamSent(
    config: ExamConfigFile
  ): boolean {

    return (
      String(
        config.roster_status
        || ''
      ).toUpperCase()
      === 'SENT'
    );
  }



  sendExamToStudentsFromTeacher(
    config: ExamConfigFile
  ): void {

    this.error = '';
    this.success = '';


    const examId =
      String(
        config.exam_id
        || config.filename.replace(
          /\.json$/i,
          ''
        )
        || ''
      ).trim();


    if (!examId) {

      this.error =
        'Code examen introuvable.';

      this.refreshView();

      return;
    }


    if (
      this.isTeacherExamSent(
        config
      )
    ) {

      this.success =
        'Cet examen a d?j? ?t? envoy?.';

      this.refreshView();

      return;
    }


    const examLabel =
      config.exam_name
      || examId;


    const count =
      Number(
        config.roster_count
        || 0
      );


    let confirmText =
      `Envoyer "${examLabel}" aux ?tudiants ?`;


    if (count > 0) {

      confirmText =
        `Envoyer "${examLabel}" `
        + `aux ${count} ?tudiant(s) `
        + 'de la liste CSV ?';
    }


    confirmText +=
      '\n\n'
      + 'L?examen appara?tra dans '
      + 'leur espace ?tudiant.';


    const confirmed =
      window.confirm(
        confirmText
      );


    if (!confirmed) {
      return;
    }


    this.teacherDeliveryLoadingExamId =
      examId;

    this.refreshView();


    const headers =
      this.getTeacherHeaders();


    this.http.post<any>(
      (
        `${this.apiUrl}`
        + '/teacher/exam-delivery/'
        + `${encodeURIComponent(examId)}`
        + '/send'
      ),
      {},
      {
        headers
      }
    ).subscribe({

      next: (response) => {

        this.teacherDeliveryLoadingExamId =
          '';


        config.roster_status =
          'SENT';


        config.sent_at =
          response?.sent_at
          || config.sent_at
          || null;


        if (
          response?.already_sent
        ) {

          this.success =
            (
              'Cet examen avait d?j? ?t? '
              + 'envoy? aux ?tudiants.'
            );

        } else {

          this.success =
            response?.message
            || (
              'Examen envoy? avec succ?s '
              + 'aux ?tudiants.'
            );
        }


        this.loadTeacherExamDeliveryStatus();

        this.refreshView();
      },


      error: (err) => {

        console.error(err);

        this.teacherDeliveryLoadingExamId =
          '';


        const detail =
          err?.error?.detail;


        if (
          detail
          && typeof detail === 'object'
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
              .filter(
                (value: any) =>
                  !!value
              )
              .join(', ');


          this.error =
            (
              detail.message
              || 'Envoi impossible.'
            )
            + (
                missing
                  ? (
                      ' Compte(s) ?tudiant(s) '
                      + 'introuvable(s) : '
                      + missing
                      + '.'
                    )
                  : ''
              );

        } else {

          this.error =
            this.getApiErrorMessage(
              err,
              (
                'Impossible d?envoyer '
                + 'l?examen aux ?tudiants.'
              )
            );
        }


        this.refreshView();
      }

    });
  }



  // ======================================================
  // NIXOS_LIST_PER_EXAM_V1
  // ======================================================

  getNixosFilename(
    config: ExamConfigFile
  ): string {

    return config.filename
      .replace(
        /\.json$/i,
        ''
      )
      + '_exam-configuration.nix';
  }


  viewNixosConfigFor(
    config: ExamConfigFile
  ): void {

    this.error = '';

    const headers =
      this.getTeacherHeaders();

    const filename =
      encodeURIComponent(
        config.filename
      );

    this.http.get<NixosConfig>(
      `${this.apiUrl}/configs/${filename}/nixos-config`,
      {
        headers
      }
    ).subscribe({

      next: (data) => {

        this.nixosConfig = data;

        this.refreshView();
      },

      error: (err) => {

        console.error(err);

        this.error =
          'Impossible d’afficher la configuration NixOS.';

        this.refreshView();
      }

    });
  }


  downloadNixosConfigFor(
    config: ExamConfigFile
  ): void {

    this.error = '';

    const headers =
      this.getTeacherHeaders();

    const filename =
      encodeURIComponent(
        config.filename
      );

    this.http.get(
      `${this.apiUrl}/configs/${filename}/nixos-config/download`,
      {
        headers,
        responseType: 'blob'
      }
    ).subscribe({

      next: (blob) => {

        this.saveBlob(
          blob,
          this.getNixosFilename(
            config
          )
        );

        this.refreshLucideIcons();
      },

      error: (err) => {

        console.error(err);

        this.error =
          'Impossible de télécharger la configuration NixOS.';

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

  getExamIdFromArchiveName(filename: string): string {
    if (!filename) {
      return 'Examen inconnu';
    }

    const parts = filename.split('_');

    return parts[0] || 'Examen inconnu';
  }

  formatDashboardDate(value: any): string {
    if (!value) {
      return 'Date non disponible';
    }

    const normalizedValue = String(value).replace(' ', 'T');
    const date = new Date(normalizedValue);

    if (Number.isNaN(date.getTime())) {
      return String(value);
    }

    return date.toLocaleString('fr-FR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  }


  profileSupportModalOpen = false;
  profileSupportLoading = false;
  profileSupportError = '';
  profileSupportSuccess = '';

  profileSupportRequest = {
    fullName: '',
    email: '',
    subject: 'Problème de connexion',
    message: ''
  };

  openProfileSupportModal(): void {
    const self = this as any;

    this.profileSupportError = '';
    this.profileSupportSuccess = '';

    this.profileSupportRequest = {
      fullName:
        self.teacherProfile?.fullName ||
        self.profile?.fullName ||
        self.profileForm?.fullName ||
        '',
      email:
        self.teacherProfile?.email ||
        self.profile?.email ||
        self.profileForm?.email ||
        '',
      subject: 'Problème de connexion',
      message: ''
    };

    this.profileSupportModalOpen = true;

    setTimeout(() => {
      if (typeof self.refreshIcons === 'function') {
        self.refreshIcons();
      }

      if (typeof self.initializeIcons === 'function') {
        self.initializeIcons();
      }

      if ((window as any).lucide) {
        (window as any).lucide.createIcons();
      }
    }, 50);
  }

  closeProfileSupportModal(): void {
    if (this.profileSupportLoading) {
      return;
    }

    this.profileSupportModalOpen = false;
    this.profileSupportError = '';
    this.profileSupportSuccess = '';
  }

  async submitProfileSupportRequest(): Promise<void> {
    this.profileSupportError = '';
    this.profileSupportSuccess = '';

    const request = {
      fullName: this.profileSupportRequest.fullName.trim(),
      email: this.profileSupportRequest.email.trim(),
      subject: this.profileSupportRequest.subject.trim(),
      message: this.profileSupportRequest.message.trim()
    };

    if (!request.fullName || !request.email || !request.message) {
      this.profileSupportError = 'Veuillez remplir le nom, l’email et le message.';
      this.refreshProfileSupportIcons();
      return;
    }

    const token =
      (this as any).accessToken ||
      localStorage.getItem('secure_exam_access_token') ||
      localStorage.getItem('secure_exam_token') ||
      '';

    if (!token) {
      this.profileSupportError = 'Session expirée. Reconnectez-vous.';
      this.refreshProfileSupportIcons();
      return;
    }

    this.profileSupportLoading = true;
    this.refreshProfileSupportIcons();

    try {
      const response = await fetch(`${this.getProfileSupportApiUrl()}/teacher-support-requests`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(request)
      });

      const responseText = await response.text();

      if (!response.ok) {
        let message = 'Impossible d’envoyer la demande support.';

        try {
          const data = JSON.parse(responseText);
          message = data?.detail || message;
        } catch {
          message = responseText || message;
        }

        throw new Error(message);
      }

      this.profileSupportLoading = false;
      this.profileSupportSuccess = 'Demande support envoyée avec succès.';
      this.profileSupportRequest.message = '';

      const self = this as any;

      if (typeof self.loadSupportRequests === 'function') {
        self.loadSupportRequests();
      }

      this.refreshProfileSupportIcons();

      setTimeout(() => {
        this.closeProfileSupportModal();
      }, 1200);
    } catch (error: any) {
      this.profileSupportLoading = false;
      this.profileSupportError =
        error?.message || 'Impossible d’envoyer la demande support.';
      this.refreshProfileSupportIcons();
    }
  }


  getProfileSupportApiUrl(): string {
    return this.apiUrl || `/api`;
  }

  refreshProfileSupportIcons(): void {
    setTimeout(() => {
      const lucide = (window as any).lucide;

      if (lucide && typeof lucide.createIcons === 'function') {
        lucide.createIcons();
      }
    }, 50);
  }


  submissionExamFilter = 'all';
  submissionDateFilter = '';

  getSubmissionExamOptions(): string[] {
    const submissions = this.dashboard?.submissions || [];
    const exams = new Set<string>();

    for (const submission of submissions as any[]) {
      const examId = submission.exam_id || this.getExamIdFromArchiveName(submission.filename);

      if (examId) {
        exams.add(examId);
      }
    }

    return Array.from(exams).sort((a, b) => a.localeCompare(b));
  }

  getFilteredSubmissions(): any[] {
    const submissions = this.dashboard?.submissions || [];

    return (submissions as any[]).filter((submission) => {
      const examId = submission.exam_id || this.getExamIdFromArchiveName(submission.filename);

      const matchExam =
        this.submissionExamFilter === 'all' ||
        examId === this.submissionExamFilter;

      const matchDate =
        !this.submissionDateFilter ||
        this.getDateOnly(submission.created_at) === this.submissionDateFilter ||
        this.getDateOnly(submission.exam_created_at) === this.submissionDateFilter ||
        this.getDateOnly(submission.exam_updated_at) === this.submissionDateFilter;

      return matchExam && matchDate;
    });
  }

  getGroupedSubmissions(): any[] {
    const submissions = this.getFilteredSubmissions();
    const groups: Record<string, any> = {};

    for (const submission of submissions) {
      const examId = submission.exam_id || this.getExamIdFromArchiveName(submission.filename);
      const examDate =
        submission.exam_created_at ||
        submission.exam_updated_at ||
        submission.created_at ||
        '';

      const key = `${examId}__${examDate}`;

      if (!groups[key]) {
        groups[key] = {
          exam_id: examId,
          exam_created_at: examDate,
          submissions: []
        };
      }

      groups[key].submissions.push(submission);
    }

    return Object.values(groups).sort((a: any, b: any) => {
      const dateA = new Date(String(a.exam_created_at || '').replace(' ', 'T')).getTime() || 0;
      const dateB = new Date(String(b.exam_created_at || '').replace(' ', 'T')).getTime() || 0;

      return dateB - dateA;
    });
  }

  getDateOnly(value: any): string {
    if (!value) {
      return '';
    }

    const text = String(value);

    if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
      return text.slice(0, 10);
    }

    const date = new Date(text.replace(' ', 'T'));

    if (Number.isNaN(date.getTime())) {
      return '';
    }

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');

    return `${year}-${month}-${day}`;
  }

  resetSubmissionFilters(): void {
    this.submissionExamFilter = 'all';
    this.submissionDateFilter = '';
    this.refreshView();
  }


  enrichPackageVersions(): void {
    const headers = this.getTeacherHeaders();

    for (const packageItem of this.availablePackages) {
      if (!packageItem?.name || !packageItem?.nixName) {
        continue;
      }

      if (this.packageVersionByNixName[packageItem.nixName]) {
        continue;
      }

      this.http.get<PackageSearchResponse>(
        `${this.apiUrl}/packages/search/${encodeURIComponent(packageItem.name)}`,
        { headers }
      ).subscribe({
        next: (data) => {
          const exactCandidate =
            data.candidates.find(candidate => candidate.nixName === packageItem.nixName) ||
            data.candidates.find(candidate => candidate.name === packageItem.name);

          if (exactCandidate?.version) {
            this.packageVersionByNixName[packageItem.nixName] = exactCandidate.version;
          } else {
            this.packageVersionByNixName[packageItem.nixName] = 'Non renseignée';
          }

          this.refreshView();
        },
        error: () => {
          this.packageVersionByNixName[packageItem.nixName] = 'Non renseignée';
          this.refreshView();
        }
      });
    }
  }

  getPackageVersionLabel(packageItem: any): string {
    if (packageItem?.version) {
      return packageItem.version;
    }

    if (packageItem?.nixName && this.packageVersionByNixName[packageItem.nixName]) {
      return this.packageVersionByNixName[packageItem.nixName];
    }

    return 'Chargement...';
  }


  get paginatedPackages(): PackageCatalogItem[] {
    const totalPages = this.getPackageTotalPages();

    if (this.packagePage > totalPages) {
      this.packagePage = totalPages;
    }

    if (this.packagePage < 1) {
      this.packagePage = 1;
    }

    const start = (this.packagePage - 1) * this.packagePageSize;
    const end = start + this.packagePageSize;

    return this.displayedPackages.slice(start, end);
  }

  getPackageTotalPages(): number {
    return Math.max(1, Math.ceil(this.displayedPackages.length / this.packagePageSize));
  }

  getPackagePages(): number[] {
    const totalPages = this.getPackageTotalPages();

    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  goToPackagePage(page: number): void {
    const totalPages = this.getPackageTotalPages();

    if (page < 1 || page > totalPages) {
      return;
    }

    this.packagePage = page;
    this.refreshView();
  }

  getPackagePaginationStart(): number {
    if (this.displayedPackages.length === 0) {
      return 0;
    }

    return ((this.packagePage - 1) * this.packagePageSize) + 1;
  }

  getPackagePaginationEnd(): number {
    return Math.min(this.packagePage * this.packagePageSize, this.displayedPackages.length);
  }



  createConfig(): void {

    this.openCreateConfigConfirmation();
  }


  openCreateConfigConfirmation(
    formValue?: any
  ): void {

    this.error = '';


    if (
      !this.hasValidStudentRoster
    ) {

      this.error =
        'La liste CSV des étudiants est obligatoire '
        + 'avant de créer l’examen.';

      this.refreshView();

      return;
    }


    this.pendingCreateConfigPreview =
      this.getCreateConfigSnapshot(
        formValue
      );


    this.showCreateConfigConfirmModal =
      true;


    this.refreshCreateConfigModalIcons();

    this.refreshView();
  }


  closeCreateConfigConfirmation(): void {
    this.showCreateConfigConfirmModal = false;
    this.pendingCreateConfigPreview = {};
    (this as any).refreshView?.();
  }

  confirmCreateConfigCreation(): void {
    this.showCreateConfigConfirmModal = false;
    (this as any).refreshView?.();
    this.executeCreateConfig();
  }

  refreshCreateConfigModalIcons(): void {
    setTimeout(() => {
      (window as any).lucide?.createIcons?.();
    }, 50);
  }

  getCreateConfigPreviewValue(...keys: string[]): string {
    for (const key of keys) {
      const value = this.pendingCreateConfigPreview?.[key];

      if (Array.isArray(value) && value.length > 0) {
        return value.join(', ');
      }

      if (value !== undefined && value !== null && String(value).trim() !== '') {
        return String(value).trim();
      }
    }

    return 'Non renseigné';
  }

  getCreateConfigPreviewBoolean(...keys: string[]): string {
    for (const key of keys) {
      const value = this.pendingCreateConfigPreview?.[key];

      if (value === true || value === 'true' || value === 'on' || value === '1') {
        return 'Oui';
      }

      if (value === false || value === 'false' || value === undefined || value === null || value === '') {
        return 'Non';
      }
    }

    return 'Non';
  }

  getCreateConfigPreviewDomainsList(): string[] {
    const raw =
      this.pendingCreateConfigPreview?.allowed_domains ??
      this.pendingCreateConfigPreview?.allowedDomains ??
      this.pendingCreateConfigPreview?.authorized_domains ??
      this.pendingCreateConfigPreview?.domains ??
      this.pendingCreateConfigPreview?.domain ??
      this.pendingCreateConfigPreview?.domaines ??
      this.pendingCreateConfigPreview?.domaines_autorises ??
      this.getCreateConfigDomainInputFromDom();

    if (Array.isArray(raw)) {
      return raw
        .map((item: any) => String(item).trim())
        .filter(Boolean);
    }

    return String(raw || '')
      .split(/[\n,;]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  getCreateConfigPreviewDomains(): string {
    const domains = this.getCreateConfigPreviewDomainsList();
    return domains.length ? domains.join(', ') : 'Aucun domaine';
  }



  getCreateConfigDomainInputFromDom(): string {
    const normalize = (value: string): string => {
      return String(value || '').trim();
    };

    const isValidDomainValue = (value: string): boolean => {
      const cleanValue = normalize(value);

      if (!cleanValue) {
        return false;
      }

      const lower = cleanValue.toLowerCase();

      if (
        lower.startsWith('exam-') ||
        lower.includes('/home/exam') ||
        lower.startsWith('etu') ||
        lower.startsWith('pc')
      ) {
        return false;
      }

      return true;
    };

    const getFieldValue = (field: Element | null): string => {
      const input = field as HTMLInputElement | HTMLTextAreaElement | null;
      const value = normalize(input?.value || '');
      return isValidDomainValue(value) ? value : '';
    };

    const labels = Array.from(document.querySelectorAll('label'));

    for (const label of labels) {
      const labelText = normalize(label.textContent || '').toLowerCase();

      if (
        labelText.includes('domaines autorisés') ||
        labelText.includes('domaines autorises') ||
        labelText.includes('domaine') ||
        labelText.includes('domain')
      ) {
        const htmlFor = label.getAttribute('for');

        if (htmlFor) {
          const linkedField = document.getElementById(htmlFor);
          const linkedValue = getFieldValue(linkedField);

          if (linkedValue) {
            return linkedValue;
          }
        }

        let sibling = label.nextElementSibling;
        let safety = 0;

        while (sibling && safety < 6) {
          const directValue = getFieldValue(sibling);

          if (directValue) {
            return directValue;
          }

          const nestedField = sibling.querySelector('input, textarea');
          const nestedValue = getFieldValue(nestedField);

          if (nestedValue) {
            return nestedValue;
          }

          sibling = sibling.nextElementSibling;
          safety += 1;
        }

        const parent = label.parentElement;
        const parentFields = Array.from(parent?.querySelectorAll('input, textarea') || []);

        for (const field of parentFields) {
          const relation = label.compareDocumentPosition(field);

          if (relation & Node.DOCUMENT_POSITION_FOLLOWING) {
            const value = getFieldValue(field);

            if (value) {
              return value;
            }
          }
        }
      }
    }

    const preciseSelectors = [
      'input[name="allowed_domains"]',
      'textarea[name="allowed_domains"]',
      'input[name="allowedDomains"]',
      'textarea[name="allowedDomains"]',
      'input[name="authorized_domains"]',
      'textarea[name="authorized_domains"]',
      'input[name="domains"]',
      'textarea[name="domains"]',
      'input[name="domaines"]',
      'textarea[name="domaines"]',
      'input[name="domaines_autorises"]',
      'textarea[name="domaines_autorises"]',
      'input[ng-reflect-name="allowed_domains"]',
      'textarea[ng-reflect-name="allowed_domains"]',
      'input[ng-reflect-name="domains"]',
      'textarea[ng-reflect-name="domains"]',
      'input[placeholder*="domaine" i]',
      'textarea[placeholder*="domaine" i]',
      'input[placeholder*="domain" i]',
      'textarea[placeholder*="domain" i]'
    ];

    for (const selector of preciseSelectors) {
      const field = document.querySelector(selector);
      const value = getFieldValue(field);

      if (value) {
        return value;
      }
    }

    return '';
  }



  findCreateConfigPackageDetails(packageValue: any): any {
    const rawName =
      typeof packageValue === 'string'
        ? packageValue
        : (
            packageValue?.nixName ??
            packageValue?.nix_name ??
            packageValue?.name ??
            packageValue?.displayName ??
            packageValue?.display_name ??
            packageValue?.package ??
            ''
          );

    const cleanName = String(rawName || '').trim().toLowerCase();

    const catalogs = [
      (this as any).packageCatalog,
      (this as any).packages,
      (this as any).availablePackages,
      (this as any).catalogPackages,
      (this as any).filteredPackages,
      (this as any).paginatedPackages,
      (this as any).activePackages,
      (this as any).dashboard?.packages
    ];

    const flatCatalog = catalogs
      .filter(Array.isArray)
      .flat();

    if (!cleanName) {
      return typeof packageValue === 'object' ? packageValue : {};
    }

    const found = flatCatalog.find((item: any) => {
      const candidates = [
        item?.nixName,
        item?.nix_name,
        item?.name,
        item?.displayName,
        item?.display_name,
        item?.package
      ].map((value) => String(value || '').trim().toLowerCase());

      return candidates.includes(cleanName);
    });

    return found || (typeof packageValue === 'object' ? packageValue : { nixName: rawName, name: rawName });
  }

  getCreateConfigPackageDisplayName(packageValue: any): string {
    const details = this.findCreateConfigPackageDetails(packageValue);

    return String(
      details?.displayName ??
      details?.display_name ??
      details?.label ??
      details?.title ??
      details?.name ??
      details?.nixName ??
      details?.nix_name ??
      packageValue ??
      'Paquet'
    ).trim();
  }

  getCreateConfigPackageVersionLabel(packageValue: any): string {
    const details = this.findCreateConfigPackageDetails(packageValue);

    const nixName = String(
      details?.nixName ??
      details?.nix_name ??
      details?.name ??
      packageValue ??
      ''
    ).trim();

    const versionMap = (this as any).packageVersionByNixName || {};

    const version =
      details?.version ??
      details?.packageVersion ??
      details?.package_version ??
      details?.latestVersion ??
      details?.latest_version ??
      versionMap[nixName] ??
      versionMap[nixName.toLowerCase()] ??
      '';

    const cleanVersion = String(version || '').trim();

    return cleanVersion || 'Non renseignée';
  }

  getCreateConfigPreviewPackagesList(): Array<{ displayName: string; nixName: string; version: string }> {
    const possibleLists = [
      this.pendingCreateConfigPreview?.packages,
      (this as any).selectedPackages,
      (this as any).selectedPackageNames,
      (this as any).newConfig?.packages,
      (this as any).config?.packages,
      (this as any).examConfig?.packages,
      (this as any).currentConfig?.packages
    ];

    let selectedPackages: any[] = [];

    for (const list of possibleLists) {
      if (Array.isArray(list) && list.length > 0) {
        selectedPackages = list;
        break;
      }
    }

    const normalized = selectedPackages
      .map((packageValue: any) => {
        const details = this.findCreateConfigPackageDetails(packageValue);

        const nixName = String(
          details?.nixName ??
          details?.nix_name ??
          details?.name ??
          packageValue ??
          ''
        ).trim();

        return {
          displayName: this.getCreateConfigPackageDisplayName(packageValue),
          nixName: nixName || this.getCreateConfigPackageDisplayName(packageValue),
          version: this.getCreateConfigPackageVersionLabel(packageValue)
        };
      })
      .filter((item) => item.displayName && item.displayName !== 'Paquet');

    const seen = new Set<string>();

    return normalized.filter((item) => {
      const key = `${item.displayName}|${item.nixName}`.toLowerCase();

      if (seen.has(key)) {
        return false;
      }

      seen.add(key);
      return true;
    });
  }

  getSelectedPackagesCountForPreview(): number {
    return this.getCreateConfigPreviewPackagesList().length;
  }

  getCreateConfigSnapshot(formValue?: any): any {
    const sources = [
      formValue,
      (this as any).newConfig,
      (this as any).config,
      (this as any).examConfig,
      (this as any).currentConfig,
      (this as any)
    ].filter(Boolean);

    const pick = (...keys: string[]): any => {
      for (const source of sources) {
        for (const key of keys) {
          const value = source?.[key];

          if (Array.isArray(value) && value.length > 0) {
            return value;
          }

          if (typeof value === 'boolean') {
            return value;
          }

          if (value !== undefined && value !== null && String(value).trim() !== '') {
            return value;
          }
        }
      }

      return '';
    };

    const domainsFromDom =
      typeof this.getCreateConfigDomainInputFromDom === 'function'
        ? this.getCreateConfigDomainInputFromDom()
        : '';

    const domainFromData = pick(
      'allowed_domains',
      'allowedDomains',
      'authorized_domains',
      'authorizedDomains',
      'domains',
      'domain',
      'domaines',
      'domaines_autorises',
      'allowedDomainsInput',
      'allowedDomainsText',
      'domainsInput',
      'domainsText'
    );

    const packages =
      pick('packages', 'selectedPackages', 'selected_packages') ||
      (this as any).selectedPackages ||
      [];

    return {
      exam_id: pick('exam_id', 'examId', 'exam'),
      student_id: pick('student_id', 'studentId', 'student'),
      machine_id: pick('machine_id', 'machineId', 'machine'),
      workspace: pick('workspace'),
      sudo: pick('sudo', 'sudo_allowed', 'sudoAllowed'),
      internet: pick('internet', 'internet_allowed', 'internetAllowed'),
      educ_access: pick('educ_access', 'educAccess', 'educ', 'educ_enabled'),
      allowed_domains: domainsFromDom || domainFromData || '',
      packages: Array.isArray(packages) ? packages : []
    };
  }

}
