import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output, AfterViewInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { PublicHeaderComponent } from '../../../components/public-header/public-header';

declare global {
  interface Window {
    lucide?: {
      createIcons: () => void;
    };
  }
}

@Component({
  selector: 'app-authentication',
  standalone: true,
  imports: [CommonModule, FormsModule, PublicHeaderComponent],
  templateUrl: './authentication.html',
  styleUrl: './authentication.css'
})
export class AuthenticationComponent implements AfterViewInit {
  private openGeneralSupportIfRequested(): void {
    const shouldOpen =
      sessionStorage.getItem('secureexam_open_general_support') === '1'
      || new URLSearchParams(window.location.search).get('support') === '1';

    if (!shouldOpen) {
      return;
    }

    sessionStorage.removeItem('secureexam_open_general_support');

    setTimeout(() => {
      const supportMethod = (this as any)['submitAuthentication'];

      if (typeof supportMethod === 'function') {
        supportMethod.call(this);
        return;
      }

      (this as any).showSupport = true;
      (this as any).showSupportModal = true;
      (this as any).supportMode = true;
      (this as any).isSupportMode = true;
      (this as any).isSupportModalOpen = true;
      (this as any).supportModalOpen = true;
    }, 200);
  }


  goToMainDashboard(): void {
    window.location.href = '/accueil';
  }


  @Input() authenticationError = '';

  @Output() authenticationRequested = new EventEmitter<{
    username: string;
    password: string;
  }>();

  @Output() supportRequested = new EventEmitter<void>();

  username = '';
  password = '';

  ngAfterViewInit(): void {
    this.openGeneralSupportIfRequested();
    this.loadIcons();
  }

  loadIcons(): void {
    setTimeout(() => {
      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
      }
    }, 100);
  }

  submitAuthentication(): void {
    this.authenticationRequested.emit({
      username: this.username,
      password: this.password
    });

    this.loadIcons();
  }

  openSupport(): void {
    this.supportRequested.emit();
    this.loadIcons();
  }
}