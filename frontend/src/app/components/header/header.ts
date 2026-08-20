import { Component, EventEmitter, Output, AfterViewInit, OnInit, Input} from '@angular/core';

declare global {
  interface Window {
    lucide?: {
      createIcons: () => void;
    };
  }
}

@Component({
  selector: 'app-header',
  standalone: true,
  templateUrl: './header.html',
  styleUrl: './header.css'
})
export class HeaderComponent implements OnInit, AfterViewInit {
  @Output() refreshRequested = new EventEmitter<void>();
  @Output() logoutRequested = new EventEmitter<void>();
  @Output() profileRequested = new EventEmitter<void>();
  @Output() sectionRequested = new EventEmitter<string>();

  activeSection = 'dashboard';
  @Input() teacherFullName = 'Professeur';


  handleTeacherAuthenticated = (): void => {
    setTimeout(() => this.loadConnectedTeacherFullName(), 50);
    setTimeout(() => this.loadConnectedTeacherFullName(), 300);
  };


  applyStoredTeacherFullName(): void {
    const storedName = localStorage.getItem('secure_exam_teacher_full_name');

    if (storedName && storedName.trim()) {
      this.teacherFullName = storedName.trim();
    }
  }

  handleTeacherNameUpdated = (event: Event): void => {
    const customEvent = event as CustomEvent;
    const fullName = customEvent.detail?.fullName;

    if (fullName && fullName.trim()) {
      this.setTeacherFullName(fullName);
    }
  };

  ngOnInit(): void {
    window.addEventListener('secure-exam-teacher-name-updated', this.handleTeacherNameUpdated);
    this.applyStoredTeacherFullName();
    setTimeout(() => this.applyStoredTeacherFullName(), 100);
    setTimeout(() => this.applyStoredTeacherFullName(), 400);
    setTimeout(() => this.loadConnectedTeacherFullName(), 700);
    window.addEventListener('secure-exam-authenticated', this.handleTeacherAuthenticated);
    this.loadConnectedTeacherFullName();
    setTimeout(() => this.loadConnectedTeacherFullName(), 300);
  }

  ngAfterViewInit(): void {
    const currentHash = window.location.hash.replace('#', '');

    if (currentHash) {
      this.activeSection = currentHash;
    }

    this.loadIcons();
  }

  loadIcons(): void {
    setTimeout(() => {
      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
      }
    }, 100);
  }



  getApiBaseUrl(): string {
    return `http://${window.location.hostname}:8000`;
  }

  getStoredAuthToken(): string {
    const priorityKeys = [
      'token',
      'access_token',
      'authToken',
      'auth_token',
      'secure_exam_token',
      'secure_exam_access_token'
    ];

    for (const key of priorityKeys) {
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

  loadConnectedTeacherFullName(): void {
    const token = this.getStoredAuthToken();

    if (!token) {
      this.teacherFullName = 'Professeur';
      localStorage.removeItem('secure_exam_teacher_full_name');
      return;
    }

    fetch(`${this.getApiBaseUrl()}/teacher-profile`, {
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
        if (profile?.fullName) {
          this.setTeacherFullName(profile.fullName);
        }
      })
      .catch(() => {
        this.teacherFullName = 'Professeur';
      });
  }

  setTeacherFullName(value: string): void {
    const cleanValue = value.trim();

    if (!cleanValue) {
      return;
    }

    this.teacherFullName = cleanValue;
    localStorage.setItem('secure_exam_teacher_full_name', cleanValue);
  }

  findTeacherFullNameInput(): HTMLInputElement | null {
    const labels = Array.from(document.querySelectorAll('label'));

    for (const label of labels) {
      const labelText = (label.textContent || '')
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '');

      if (labelText.includes('nom complet')) {
        const input = label.querySelector('input') as HTMLInputElement | null;

        if (input) {
          return input;
        }
      }
    }

    return document.querySelector(
      'input[name="fullName"], input[id="fullName"], input[id="full-name"], input[formcontrolname="fullName"]'
    ) as HTMLInputElement | null;
  }

  syncTeacherFullNameFromProfilePage(): void {
    const input = this.findTeacherFullNameInput();

    if (!input) {
      return;
    }

    this.setTeacherFullName(input.value);

    if (input.dataset['teacherFullNameListener'] === 'true') {
      return;
    }

    input.dataset['teacherFullNameListener'] = 'true';

    input.addEventListener('input', () => {
      this.setTeacherFullName(input.value);
    });
  }

  goToSection(section: string, event?: Event): void {
    if (event) {
      event.preventDefault();
    }

    this.activeSection = section;
    this.sectionRequested.emit(section);
    this.loadIcons();
  }

  refresh(): void {
    this.refreshRequested.emit();
    this.loadIcons();
  }

  openProfile(): void {
    this.activeSection = 'profile';
    this.profileRequested.emit();

    this.loadConnectedTeacherFullName();
    setTimeout(() => this.syncTeacherFullNameFromProfilePage(), 250);
    setTimeout(() => this.syncTeacherFullNameFromProfilePage(), 700);

    this.loadIcons();
  }

  logout(): void {
    localStorage.removeItem('secure_exam_teacher_full_name');
    this.teacherFullName = 'Professeur';
    this.logoutRequested.emit();
    this.loadIcons();
  }

  goToDashboardFromLogo(): void {
    this.sectionRequested.emit('dashboard');
  }

}