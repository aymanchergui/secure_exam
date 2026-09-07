import { CommonModule } from '@angular/common';
import { Component, AfterViewInit, EventEmitter, Input, Output, OnInit, ChangeDetectorRef } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpHeaders } from '@angular/common/http';

declare global {
  interface Window {
    lucide?: {
      createIcons: () => void;
    };
  }
}

interface TeacherProfile {
  fullName: string;
  email: string;
  role: string;
  department: string;
  school: string;
  hasPhoto?: boolean;
  photoUrl?: string;
}

interface SupportRequest {
  filename: string;
  created_at: string;
  fullName: string;
  email: string;
  subject: string;
  message: string;
}

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './profile.html',
  styleUrl: './profile.css'
})
export class ProfileComponent implements OnInit, AfterViewInit {
  @Input() accessToken = '';

  @Output() backRequested = new EventEmitter<void>();

  private apiUrl = `http://${window.location.hostname}:8000`;

  loading = false;
  saving = false;
  uploadingPhoto = false;

  successMessage = '';
  errorMessage = '';

  photoLoadError = false;
  photoUrl = '';

  profile: TeacherProfile = {
    fullName: '',
    email: '',
    role: '',
    department: '',
    school: ''
  };

  supportRequests: SupportRequest[] = [];

  constructor(
    private http: HttpClient,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadProfile();
    this.loadSupportRequests();
  }

  ngAfterViewInit(): void {
    this.refreshView();
  }

  getHeaders(): HttpHeaders {
    return new HttpHeaders({
      Authorization: `Bearer ${this.accessToken}`
    });
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

  goBack(): void {
    this.backRequested.emit();
    this.refreshView();
  }

  loadProfile(): void {
    this.loading = true;
    this.errorMessage = '';

    this.http.get<TeacherProfile>(
      `${this.apiUrl}/teacher-profile`,
      {
        headers: this.getHeaders()
      }
    ).subscribe({
      next: (profile) => {
        this.profile = profile;
        this.photoLoadError = false;

        if (profile.hasPhoto) {
          this.photoUrl = `${this.apiUrl}/teacher-profile/photo?ts=${Date.now()}`;
        }

        this.loading = false;
        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.errorMessage = "Impossible de charger le profil professeur.";
        this.loading = false;

        this.refreshView();
      }
    });
  }

  saveProfile(): void {
    this.successMessage = '';
    this.errorMessage = '';
    this.saving = true;

    this.http.put<{ message: string }>(
      `${this.apiUrl}/teacher-profile`,
      {
        fullName: this.profile.fullName,
        email: this.profile.email,
        role: this.profile.role,
        department: this.profile.department,
        school: this.profile.school
      },
      {
        headers: this.getHeaders()
      }
    ).subscribe({
      next: (response) => {
        this.successMessage = response.message;
        this.saving = false;

        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.errorMessage = "Impossible d'enregistrer le profil.";
        this.saving = false;

        this.refreshView();
      }
    });
  }

  onPhotoSelected(event: Event): void {
    const input = event.target as HTMLInputElement;

    if (!input.files || input.files.length === 0) {
      return;
    }

    const file = input.files[0];

    const formData = new FormData();
    formData.append('photo', file);

    this.successMessage = '';
    this.errorMessage = '';
    this.uploadingPhoto = true;

    this.http.post<{ message: string; photoUrl: string }>(
      `${this.apiUrl}/teacher-profile/photo`,
      formData,
      {
        headers: this.getHeaders()
      }
    ).subscribe({
      next: (response) => {
        this.successMessage = response.message;
        this.photoLoadError = false;
        this.photoUrl = `${this.apiUrl}/teacher-profile/photo?ts=${Date.now()}`;
        this.uploadingPhoto = false;

        this.refreshView();
      },
      error: (err) => {
        console.error(err);

        this.errorMessage = "Impossible de modifier la photo de profil.";
        this.uploadingPhoto = false;

        this.refreshView();
      }
    });
  }

  loadSupportRequests(): void {
    const token =
      (this as any).accessToken ||
      localStorage.getItem('secure_exam_access_token') ||
      localStorage.getItem('secure_exam_token') ||
      '';

    if (!token) {
      (this as any).supportRequests = [];
      return;
    }

    fetch(`${this.getProfileSupportApiUrl()}/support-requests-list`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error('Impossible de charger les demandes support.');
        }

        return response.json();
      })
      .then((data) => {
        (this as any).supportRequests = data.support_requests || [];
        this.refreshProfileSupportIcons();
      })
      .catch(() => {
        (this as any).supportRequests = [];
        this.refreshProfileSupportIcons();
      });
  }

  profileSupportModalOpen = false;
  profileSupportLoading = false;
  profileSupportError = '';
  profileSupportSuccess = '';

  profileSupportRequest = {
    fullName: '',
    email: '',
    subject: 'Problème de connexion',
    message: ''
  };

  getProfileSupportApiUrl(): string {
    return `http://${window.location.hostname}:8000`;
  }

  refreshProfileSupportIcons(): void {
    setTimeout(() => {
      const lucide = (window as any).lucide;

      if (lucide && typeof lucide.createIcons === 'function') {
        lucide.createIcons();
      }
    }, 50);
  }

  openProfileSupportModal(): void {
    const self = this as any;

    this.profileSupportError = '';
    this.profileSupportSuccess = '';

    this.profileSupportRequest = {
      fullName:
        self.profile?.fullName ||
        self.teacherProfile?.fullName ||
        self.profileForm?.fullName ||
        self.fullName ||
        '',
      email:
        self.profile?.email ||
        self.teacherProfile?.email ||
        self.profileForm?.email ||
        self.email ||
        '',
      subject: 'Problème de connexion',
      message: ''
    };

    this.profileSupportModalOpen = true;
    this.refreshProfileSupportIcons();
  }

  closeProfileSupportModal(): void {
    if (this.profileSupportLoading) {
      return;
    }

    this.profileSupportModalOpen = false;
    this.profileSupportError = '';
    this.profileSupportSuccess = '';
  }

  submitProfileSupportRequest(): void {
    this.profileSupportError = '';
    this.profileSupportSuccess = '';

    const request = {
      fullName: this.profileSupportRequest.fullName.trim(),
      email: this.profileSupportRequest.email.trim(),
      subject: this.profileSupportRequest.subject.trim(),
      message: this.profileSupportRequest.message.trim()
    };

    if (!request.fullName || !request.email || !request.message) {
      this.profileSupportError = 'Veuillez remplir le nom, l’email et le message.';
      this.refreshView();
      return;
    }

    if (this.profileSupportLoading) {
      return;
    }

    this.profileSupportLoading = true;
    this.refreshView();

    this.http.post<{ message: string; request_id: number; email_sent: boolean }>(
      `${this.apiUrl}/teacher-support-requests`,
      request,
      {
        headers: this.getHeaders()
      }
    ).subscribe({
      next: (response) => {
        this.profileSupportLoading = false;
        this.profileSupportSuccess =
          response?.message || 'Demande support envoyée avec succès.';
        this.profileSupportRequest.message = '';

        this.loadSupportRequests();
        this.refreshView();

        setTimeout(() => {
          this.closeProfileSupportModal();
          this.refreshView();
        }, 2000);
      },
      error: (error) => {
        this.profileSupportLoading = false;
        this.profileSupportError =
          error?.error?.detail ||
          'Impossible d’envoyer la demande support.';

        this.refreshView();
      }
    });
  }

}