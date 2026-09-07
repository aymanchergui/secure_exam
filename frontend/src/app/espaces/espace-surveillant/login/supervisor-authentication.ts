import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, EventEmitter, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule } from '@angular/common/http';
import { finalize, timeout } from 'rxjs';
import { PublicHeaderComponent } from '../../../components/public-header/public-header';

declare const lucide: any;

interface SupervisorLoginResponse {
  access_token: string;
  token_type: string;
  role: string;
  username: string;
}

@Component({
  selector: 'app-supervisor-authentication',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule, PublicHeaderComponent],
  templateUrl: './supervisor-authentication.html',
  styleUrl: './supervisor-authentication.css'
})
export class SupervisorAuthenticationComponent implements AfterViewInit {
  openSupport(): void {
    window.location.href = '/support';
  }







  @Output() authenticated = new EventEmitter<void>();
  @Output() backToDashboard = new EventEmitter<void>();
  @Output() supportRequested = new EventEmitter<void>();

  username = 'surveillant';
  password = '';
  authenticationError = '';
  isLoading = false;

  private apiUrl = `http://${window.location.hostname}:8000`;

  constructor(private http: HttpClient) {}

  ngAfterViewInit(): void {
    this.refreshIcons();
  }

  private refreshIcons(): void {
    setTimeout(() => {
      if (typeof lucide !== 'undefined') {
        lucide.createIcons();
      }
    });
  }
  submitAuthentication(): void {
    this.authenticationError = '';
    this.isLoading = false;

    const cleanUsername = this.username.trim();
    const cleanPassword = this.password.trim();

    const expectedUsername = 'surveillant';
    const expectedPassword = '1234';

    if (!cleanUsername) {
      this.authenticationError = 'Veuillez renseigner votre identifiant.';
      this.refreshIcons();
      return;
    }

    if (!cleanPassword) {
      this.authenticationError = 'Veuillez renseigner votre mot de passe.';
      this.refreshIcons();
      return;
    }

    if (cleanUsername !== expectedUsername) {
      this.authenticationError = 'Identifiant surveillant incorrect.';
      this.refreshIcons();
      return;
    }

    if (cleanPassword !== expectedPassword) {
      this.authenticationError = 'Mot de passe surveillant incorrect.';
      this.password = '';
      this.refreshIcons();
      return;
    }

    this.isLoading = true;

    const securityTimeout = window.setTimeout(() => {
      if (!this.isLoading) {
        return;
      }

      this.isLoading = false;
      this.authenticationError = 'Serveur injoignable. Vérifiez que le backend FastAPI est lancé.';
      this.refreshIcons();
    }, 8000);

    this.http.post<SupervisorLoginResponse>(`${this.apiUrl}/supervisor/login`, {
      username: cleanUsername,
      password: cleanPassword
    }).subscribe({
      next: (response) => {
        window.clearTimeout(securityTimeout);

        localStorage.setItem('secureexam_supervisor_token', response.access_token);
        localStorage.setItem('secureexam_supervisor_username', response.username);

        this.isLoading = false;
        this.refreshIcons();
        this.authenticated.emit();
      },
      error: (error) => {
        window.clearTimeout(securityTimeout);

        this.isLoading = false;

        if (error?.status === 0) {
          this.authenticationError = 'Connexion au serveur impossible. Vérifiez que le backend est lancé.';
        } else {
          this.authenticationError =
            error?.error?.detail || 'Connexion surveillant impossible.';
        }

        this.refreshIcons();
      }
    });
  }





  goBack(): void {
    this.backToDashboard.emit();
  }

}
