import { Component, EventEmitter, Output, AfterViewInit } from '@angular/core';

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
export class HeaderComponent implements AfterViewInit {
  @Output() refreshRequested = new EventEmitter<void>();
  @Output() logoutRequested = new EventEmitter<void>();
  @Output() profileRequested = new EventEmitter<void>();
  @Output() sectionRequested = new EventEmitter<string>();

  activeSection = 'dashboard';
  teacherFullName = localStorage.getItem('secure_exam_teacher_full_name') || 'Professeur';

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

    setTimeout(() => this.syncTeacherFullNameFromProfilePage(), 250);
    setTimeout(() => this.syncTeacherFullNameFromProfilePage(), 700);

    this.loadIcons();
  }

  logout(): void {
    this.logoutRequested.emit();
    this.loadIcons();
  }
}