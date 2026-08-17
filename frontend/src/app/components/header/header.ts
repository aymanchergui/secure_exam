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
    this.loadIcons();
  }

  logout(): void {
    this.logoutRequested.emit();
    this.loadIcons();
  }
}