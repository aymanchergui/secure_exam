import { CommonModule } from '@angular/common';
import {
  Component,
  AfterViewInit,
  EventEmitter,
  Output,
  ChangeDetectorRef
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { PublicHeaderComponent } from '../public-header/public-header';
import { timeout } from 'rxjs';


declare global {
  interface Window {
    lucide?: {
      createIcons: () => void;
    };
  }
}


type SupportSpace =
  | 'student'
  | 'professor'
  | 'admin';


@Component({
  selector: 'app-support',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    PublicHeaderComponent
  ],
  templateUrl: './support.html',
  styleUrl: './support.css'
})
export class SupportComponent implements AfterViewInit {

  @Output()
  backRequested =
    new EventEmitter<void>();

  private apiUrl = `/api`;

  loading = false;
  successMessage = '';
  errorMessage = '';

  supportSpace: SupportSpace =
    'student';

  readonly problemOptionsBySpace:
    Record<SupportSpace, string[]> = {

      student: [
        'Problème de connexion',
        'Accès ENT / mot de passe',
        'Épreuve non visible',
        'Session SecureExam / environnement',
        'Plateforme indisponible',
        'Autre problème'
      ],

      professor: [
        'Problème de connexion',
        'Création ou préparation d’examen',
        'Configuration NixOS',
        'Affectation des étudiants',
        'Récupération des rendus',
        'Plateforme indisponible',
        'Autre problème'
      ],

      admin: [
        'Problème de connexion',
        'Configuration NixOS',
        'Diffusion d’un examen',
        'Machine d’examen',
        'Liste des étudiants',
        'Plateforme indisponible',
        'Autre problème'
      ]
    };


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


  get problemOptions(): string[] {
    return this.problemOptionsBySpace[
      this.supportSpace
    ];
  }


  get supportSpaceLabel(): string {

    switch (this.supportSpace) {

      case 'student':
        return 'Espace Étudiant';

      case 'professor':
        return 'Espace Professeur';

      case 'admin':
        return 'Espace Administrateur';
    }
  }


  selectSupportSpace(
    space: SupportSpace
  ): void {

    if (this.supportSpace === space) {
      return;
    }

    this.supportSpace = space;

    this.supportRequest.subject =
      this.problemOptionsBySpace[space][0];

    this.successMessage = '';
    this.errorMessage = '';

    this.refreshView();
  }


  refreshView(): void {

    this.cdr.detectChanges();

    setTimeout(() => {

      if (
        window.lucide
        && typeof window.lucide.createIcons === 'function'
      ) {
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

      this.errorMessage =
        'Veuillez saisir votre nom complet.';

      this.refreshView();

      return;
    }

    if (!this.supportRequest.email.trim()) {

      this.errorMessage =
        'Veuillez saisir votre adresse email.';

      this.refreshView();

      return;
    }

    if (!this.supportRequest.message.trim()) {

      this.errorMessage =
        'Veuillez décrire le problème rencontré.';

      this.refreshView();

      return;
    }


    const payload = {

      fullName:
        this.supportRequest.fullName.trim(),

      email:
        this.supportRequest.email.trim(),

      subject:
        `${this.supportSpaceLabel} — ${this.supportRequest.subject}`,

      message:
        this.supportRequest.message.trim()
    };


    this.loading = true;

    this.refreshView();


    this.http.post<{ message: string }>(
      `${this.apiUrl}/support-requests`,
      payload
    )
    .pipe(timeout(15000))
    .subscribe({

      next: (response) => {

        this.loading = false;

        this.successMessage =
          response.message
          || 'Votre demande de support a été envoyée avec succès.';

        this.errorMessage = '';

        this.supportRequest = {
          fullName: '',
          email: '',
          subject:
            this.problemOptionsBySpace[
              this.supportSpace
            ][0],
          message: ''
        };

        this.refreshView();
      },


      error: (err) => {

        this.loading = false;

        console.error(err);

        this.errorMessage =
          err?.error?.detail
          || "Impossible d'envoyer la demande de support.";

        this.successMessage = '';

        this.refreshView();
      }
    });
  }
}