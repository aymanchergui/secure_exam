import { CommonModule } from '@angular/common';
import { Component, AfterViewInit, EventEmitter, Output, ChangeDetectorRef } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { finalize, timeout } from 'rxjs';

declare global {
  interface Window {
    lucide?: {
      createIcons: () => void;
    };
  }
}

@Component({
  selector: 'app-support',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './support.html',
  styleUrl: './support.css'
})
export class SupportComponent implements AfterViewInit {
  @Output() backRequested = new EventEmitter<void>();

  private apiUrl = 'http://127.0.0.1:8000';

  loading = false;
  successMessage = '';
  errorMessage = '';

  supportRequest = {
    fullName: '',
    email: '',
    subject: 'Problème de connexion',
    message: ''
  };

  constructor(
    private http: HttpClient,
    private cdr: ChangeDetectorRef
  ) {}

  ngAfterViewInit(): void {
    this.refreshView();
  }

  refreshView(): void {
    this.cdr.detectChanges();

    setTimeout(() => {
      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
      }

      this.cdr.detectChanges();
    }, 50);
  }

  goBackToAuthentication(): void {
    this.backRequested.emit();
    this.refreshView();
  }

  submitSupportRequest(): void {
    if (this.loading) {
      return;
    }

    this.successMessage = '';
    this.errorMessage = '';

    if (!this.supportRequest.fullName.trim()) {
      this.errorMessage = 'Veuillez saisir votre nom complet.';
      this.refreshView();
      return;
    }

    if (!this.supportRequest.email.trim()) {
      this.errorMessage = 'Veuillez saisir votre adresse email.';
      this.refreshView();
      return;
    }

    if (!this.supportRequest.message.trim()) {
      this.errorMessage = 'Veuillez décrire le problème rencontré.';
      this.refreshView();
      return;
    }

    this.loading = true;
    this.refreshView();

    this.http.post<{ message: string }>(
      `${this.apiUrl}/support-requests`,
      this.supportRequest
    )
    .pipe(
      timeout(30000),
      finalize(() => {
        this.loading = false;
        this.refreshView();
      })
    )
    .subscribe({
      next: (response) => {
        this.successMessage =
          response.message || 'Votre demande de support a été envoyée avec succès.';

        this.errorMessage = '';

        this.supportRequest = {
          fullName: '',
          email: '',
          subject: 'Problème de connexion',
          message: ''
        };

        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.errorMessage =
          err?.error?.detail || "Impossible d'envoyer la demande de support.";

        this.successMessage = '';

        this.refreshView();
      }
    });
  }
}