import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, EventEmitter, Input, Output } from '@angular/core';

declare const lucide: any;

@Component({
  selector: 'app-supervisor-header',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './supervisor-header.html',
  styleUrl: './supervisor-header.css'
})
export class SupervisorHeaderComponent implements AfterViewInit {
  @Input() supervisorName = 'Surveillant';
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

  goToSupervisorDashboard(): void {
    this.goToSection('dashboard');
  }

  refresh(): void {
    this.refreshRequested.emit();
  }

  logout(): void {
    this.logoutRequested.emit();
  }
}
