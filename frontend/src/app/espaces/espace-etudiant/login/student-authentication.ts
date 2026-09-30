import {
  Component,
  EventEmitter,
  Output
} from '@angular/core';

import {
  CommonModule
} from '@angular/common';

import {
  FormsModule
} from '@angular/forms';

import {
  HttpClient
} from '@angular/common/http';

import {
  PublicHeaderComponent
} from '../../../components/public-header/public-header';


interface StudentLoginResponse {
  access_token: string;
  token_type: string;
  role: string;
  username: string;
  student_number: string;
  full_name: string;
}


@Component({
  selector: 'app-student-authentication',

  standalone: true,

  imports: [
    CommonModule,
    FormsModule,
    PublicHeaderComponent
  ],

  templateUrl: './student-authentication.html',

  styleUrl: './student-authentication.css'
})
export class StudentAuthenticationComponent {

  @Output()
  authenticated =
    new EventEmitter<void>();

  @Output()
  backToDashboard =
    new EventEmitter<void>();


  username = '';
  password = '';

  loading = false;
  error = '';

  private readonly apiUrl = '/api';


  constructor(
    private readonly http:
      HttpClient
  ) {}


  login(): void {

    if (
      !this.username.trim()
      || !this.password
    ) {
      this.error =
        'Veuillez saisir votre identifiant et votre mot de passe.';

      return;
    }

    this.loading = true;
    this.error = '';

    this.http
      .post<StudentLoginResponse>(
        `${this.apiUrl}/student/login`,
        {
          username:
            this.username.trim(),

          password:
            this.password
        }
      )
      .subscribe({

        next: (response) => {

          localStorage.setItem(
            'secureexam_student_token',
            response.access_token
          );

          localStorage.setItem(
            'secureexam_student_username',
            response.username
          );

          localStorage.setItem(
            'secureexam_student_number',
            response.student_number
          );

          localStorage.setItem(
            'secureexam_student_full_name',
            response.full_name
          );

          this.loading = false;

          this.authenticated.emit();
        },

        error: (error) => {

          this.loading = false;

          this.password = '';

          this.error =
            error?.error?.detail
            || 'Authentification étudiante impossible.';
        }
      });
  }


  back(): void {
    this.backToDashboard.emit();
  }
}