import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, EventEmitter, Input, Output } from '@angular/core';

declare const lucide: any;

@Component({
  selector: 'app-admin-header',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './admin-header.html',
  styleUrl: './admin-header.css'
})
export class AdminHeaderComponent implements AfterViewInit {
  @Input() adminName = 'Administrateur';
  @Input() activeSection = 'dashboard';

  @Output() sectionRequested = new EventEmitter<string>();
  @Output() refreshRequested = new EventEmitter<void>();
  @Output() logoutRequested = new EventEmitter<void>();
  @Output() backToDashboard = new EventEmitter<void>();

  ngAfterViewInit(): void {
    setTimeout(() => {
      if (typeof lucide !== 'undefined') {
        lucide.createIcons();
      }
    });
  }

  goToSection(section: string, event?: Event): void {
    event?.preventDefault();
    this.activeSection = section;
    this.sectionRequested.emit(section);

    setTimeout(() => {
      if (typeof lucide !== 'undefined') {
        lucide.createIcons();
      }
    });
  }

  goToAdminDashboard(): void {
    this.goToSection('dashboard');
  }

  refresh(): void {
    this.refreshRequested.emit();
  }

  logout(): void {
    this.logoutRequested.emit();
  }
}
