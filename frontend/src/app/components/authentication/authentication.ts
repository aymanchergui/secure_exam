import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output, AfterViewInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HeaderAuthComponent } from '../header-auth/header-auth';

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
  imports: [CommonModule, FormsModule, HeaderAuthComponent],
  templateUrl: './authentication.html',
  styleUrl: './authentication.css'
})
export class AuthenticationComponent implements AfterViewInit {
  @Input() authenticationError = '';

  @Output() authenticationRequested = new EventEmitter<{
    username: string;
    password: string;
  }>();

  @Output() supportRequested = new EventEmitter<void>();

  username = '';
  password = '';

  ngAfterViewInit(): void {
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