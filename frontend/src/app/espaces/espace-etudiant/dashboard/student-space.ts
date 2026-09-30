import {
  AfterViewInit,
  ChangeDetectorRef,
  Component,
  EventEmitter,
  OnDestroy,
  OnInit,
  Output
} from '@angular/core';

import {
  CommonModule
} from '@angular/common';

import {
  HttpClient,
  HttpHeaders
} from '@angular/common/http';

import { timeout } from 'rxjs/operators';

declare const lucide: any;


interface StudentExamConfig {
  packages: string[];
  sudo: boolean;
  internet: boolean;
  educ_access: boolean;
  allowed_domains: string[];
  nix_filename: string;
}


interface StudentExam {
  assignment_id: number;
  exam_id: string;
  exam_name: string;
  exam_date: string;
  exam_time: string;
  machine_id: string;
  status: string;
  assigned_at: string;
  started_at: string | null;
  config_ready: boolean;
  config: StudentExamConfig | null;
}


interface StudentInfo {
  id: number;
  username: string;
  student_number: string;
  full_name: string;
  email: string;
}


interface StudentDashboard {
  student: StudentInfo;
  exams: StudentExam[];
  exams_count: number;
}


interface StartExamResponse {
  success: boolean;
  assignment_id: number;
  exam_id: string;
  status: string;
  started_at: string | null;
  configuration_applied: boolean;
}


type StudentSessionState =
  | 'idle'
  | 'running'
  | 'paused'
  | 'finished';


@Component({
  selector: 'app-student-space',
  standalone: true,

  imports: [
    CommonModule
  ],

  templateUrl: './student-space.html',
  styleUrl: './student-space.css'
})
export class StudentSpaceComponent
implements OnInit, AfterViewInit, OnDestroy {

  @Output()
  backToDashboard =
    new EventEmitter<void>();


  @Output()
  logoutRequested =
    new EventEmitter<void>();


  activeStudentSection:
    'exam'
    | 'config'
    | 'instructions' = 'exam';


  get studentFullName(): string {

    return (
      this.dashboard?.student?.full_name
      || localStorage.getItem(
        'secureexam_student_full_name'
      )
      || 'Étudiant'
    );
  }


  dashboard:
    StudentDashboard | null = null;


  loading = false;
  launchLoading = false;

  error = '';
  launchError = '';

  elapsedSeconds = 0;

  sessionState:
    StudentSessionState = 'idle';

  private timerBaseSeconds = 0;

  private timerRunningSinceMs:
    number | null = null;

  private timerHandle:
    ReturnType<typeof setInterval>
    | null = null;


  private launchStatusHandle:
    ReturnType<typeof setInterval>
    | null = null;


  private readonly apiUrl =
    `/api`;


  constructor(
    private readonly http:
      HttpClient,

    private readonly cdr:
      ChangeDetectorRef
  ) {}


  ngOnInit(): void {

    /*
     * L'espace étudiant doit toujours avoir
     * son URL complète, même après un refresh.
     */
    if (
      window.location.pathname
      !== '/espace_etudiant/dashboard'
    ) {

      window.history.replaceState(
        {},
        '',
        '/espace_etudiant/dashboard'
      );
    }

    this.loadDashboard();
  }


  ngAfterViewInit(): void {

    this.refreshStudentIcons();
  }


  private refreshStudentIcons(): void {

    setTimeout(() => {

      if (
        typeof lucide
        !== 'undefined'
      ) {
        lucide.createIcons();
      }

    });
  }


  goToStudentSection(
    section:
      'exam'
      | 'config'
      | 'instructions',
    event?: Event
  ): void {

    if (event) {
      event.preventDefault();
    }

    this.activeStudentSection =
      section;

    const target =
      document.getElementById(
        `student-${section}`
      );

    if (target) {

      target.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    }
  }


  refresh(): void {

    this.loadDashboard();

    this.refreshStudentIcons();
  }


  goToDashboardFromLogo(): void {

    this.backToDashboard.emit();
  }


  ngOnDestroy(): void {

    this.stopTimer();
    this.stopExamStatusPolling();
  }


  get assignedExam():
    StudentExam | null {

    if (
      !this.dashboard
      || this.dashboard.exams.length
      === 0
    ) {
      return null;
    }

    const running =
      this.dashboard.exams.find(
        exam =>
          String(
            exam.status
            || ''
          ).toUpperCase()
          === 'EN_COURS'
      );

    if (running) {
      return running;
    }

    const upcoming =
      this.dashboard.exams.find(
        exam => {

          const status =
            String(
              exam.status
              || ''
            ).toUpperCase();

          return (
            status !== 'TERMINE'
            && status !== 'TERMINEE'
            && status !== 'CLOTURE'
            && status !== 'CLOTUREE'
          );
        }
      );

    return (
      upcoming
      || this.dashboard.exams[0]
    );
  }


  get examRunning():
    boolean {

    return (
      this.sessionState
      === 'running'
    );
  }


  get examPaused():
    boolean {

    return (
      this.sessionState
      === 'paused'
    );
  }


  get examFinished():
    boolean {

    return (
      this.sessionState
      === 'finished'
    );
  }


  get examStarted():
    boolean {

    return (
      this.examRunning
      || this.examPaused
      || this.examFinished
    );
  }



  get examPreparing():
    boolean {

    return (
      String(
        this.assignedExam?.status
        || ''
      ).toUpperCase()
      === 'PREPARING'
    );
  }


  private getHeaders():
    HttpHeaders {

    const token =
      localStorage.getItem(
        'secureexam_student_token'
      )
      || '';

    return new HttpHeaders({
      Authorization:
        `Bearer ${token}`
    });
  }


  loadDashboard(): void {

    this.loading = true;
    this.error = '';

    this.http
      .get<StudentDashboard>(
        `${this.apiUrl}/student/dashboard`,
        {
          headers:
            this.getHeaders()
        }
      )
      .pipe(
        timeout(8000)
      )
      .subscribe({

        next: data => {

          this.dashboard = data;

          this.loading = false;

          localStorage.setItem(
            'secureexam_student_full_name',
            data.student.full_name
          );

          this.syncTimer();

          if (this.examPreparing) {

            this.startExamStatusPolling();

          } else {

            this.stopExamStatusPolling();
          }

          this.refreshStudentIcons();

          this.cdr.detectChanges();
        },

        error: error => {

          this.loading = false;

          if (
            error?.name === 'TimeoutError'
          ) {

            this.error =
              'Le serveur SecureExam ne répond pas. '
              + 'Vérifiez que le backend est lancé '
              + 'sur le port 8000.';

          } else if (
            error?.status === 401
            || error?.status === 403
          ) {

            this.error =
              'Votre session étudiant a expiré. '
              + 'Veuillez vous reconnecter.';

          } else {

            this.error =
              error?.error?.detail
              || (
                'Impossible de charger '
                + 'votre espace étudiant.'
              );
          }
        }
      });
  }


  launchExam(): void {

    const exam =
      this.assignedExam;

    if (!exam) {
      return;
    }


    if (!exam.config_ready) {

      this.launchError =
        'La configuration de cet examen '
        + 'n?est pas encore disponible.';

      return;
    }


    /*
     * Une session locale deja demarree
     * conserve pause / reprise / fin.
     */
    if (this.examStarted) {

      if (this.examRunning) {
        this.syncTimer();
      }

      return;
    }


    /*
     * La machine est deja en preparation :
     * pas de seconde commande START_EXAM.
     */
    if (this.examPreparing) {

      this.startExamStatusPolling();

      return;
    }


    this.launchLoading = true;
    this.launchError = '';


    this.http
      .post<StartExamResponse>(
        (
          `${this.apiUrl}`
          + `/student/exams/`
          + `${exam.assignment_id}`
          + `/start`
        ),
        {},
        {
          headers:
            this.getHeaders()
        }
      )
      .pipe(
        timeout(8000)
      )
      .subscribe({

        next: response => {

          exam.status =
            response.status;

          exam.started_at =
            response.started_at;

          const status =
            String(
              response.status
              || ''
            ).toUpperCase();


          /*
           * Cas normalement utilise seulement
           * si l'examen etait deja EN_COURS.
           */
          if (
            status === 'EN_COURS'
            && response.started_at
          ) {

            this.launchLoading =
              false;

            this.beginSessionTimer(
              response.started_at
            );

            this.refreshStudentIcons();
            this.cdr.detectChanges();

            return;
          }


          /*
           * Nouveau comportement normal :
           *
           * backend = PREPARING
           * started_at = null
           *
           * PAS DE CHRONO.
           */
          if (
            status === 'PREPARING'
          ) {

            this.launchLoading =
              true;

            this.stopTimer();

            this.sessionState =
              'idle';

            this.elapsedSeconds =
              0;

            this.timerBaseSeconds =
              0;

            this.timerRunningSinceMs =
              null;

            this.startExamStatusPolling();

            this.refreshStudentIcons();
            this.cdr.detectChanges();

            return;
          }


          this.launchLoading =
            false;

          this.cdr.detectChanges();
        },

        error: error => {

          this.launchLoading =
            false;

          this.launchError =
            error?.error?.detail
            || (
              'Impossible de lancer '
              + 'l?examen.'
            );

          this.cdr.detectChanges();
        }
      });
  }


  private startExamStatusPolling():
    void {

    if (
      this.launchStatusHandle
      !== null
    ) {
      return;
    }


    this.launchLoading = true;


    const poll = () => {

      this.http
        .get<StudentDashboard>(
          `${this.apiUrl}/student/dashboard`,
          {
            headers:
              this.getHeaders()
          }
        )
        .pipe(
          timeout(8000)
        )
        .subscribe({

          next: data => {

            this.dashboard = data;

            const exam =
              this.assignedExam;

            const status =
              String(
                exam?.status
                || ''
              ).toUpperCase();


            /*
             * READY cote agent a deja fait :
             *
             * PREPARING
             *   ->
             * EN_COURS + started_at
             */
            if (
              status === 'EN_COURS'
              && exam?.started_at
            ) {

              this.stopExamStatusPolling();

              this.launchLoading =
                false;

              this.launchError =
                '';

              /*
               * Utilise ton systeme existant
               * de timer/sessionState.
               */
              this.syncTimer();

              this.refreshStudentIcons();
              this.cdr.detectChanges();

              return;
            }


            if (
              status === 'START_ERROR'
            ) {

              this.stopExamStatusPolling();

              this.launchLoading =
                false;

              this.launchError =
                'La preparation du poste '
                + 'SecureExam a echoue. '
                + 'Le chronometre '
                + 'n a pas demarre.';

              this.stopTimer();

              this.sessionState =
                'idle';

              this.elapsedSeconds =
                0;

              this.timerBaseSeconds =
                0;

              this.timerRunningSinceMs =
                null;

              this.refreshStudentIcons();
              this.cdr.detectChanges();

              return;
            }


            /*
             * PREPARING :
             * on attend simplement le prochain poll.
             */
            this.cdr.detectChanges();
          },

          error: () => {

            /*
             * Erreur reseau temporaire.
             * On retentera au prochain poll.
             */
          }
        });
    };


    poll();


    this.launchStatusHandle =
      setInterval(
        poll,
        1000
      );
  }


  private stopExamStatusPolling():
    void {

    if (
      this.launchStatusHandle
      !== null
    ) {

      clearInterval(
        this.launchStatusHandle
      );

      this.launchStatusHandle =
        null;
    }
  }


  private syncTimer(): void {

    this.stopTimer();


    const exam =
      this.assignedExam;


    if (
      !exam
      || !exam.started_at
    ) {

      this.sessionState =
        'idle';

      this.elapsedSeconds =
        0;

      this.timerBaseSeconds =
        0;

      this.timerRunningSinceMs =
        null;

      return;
    }


    const stored =
      this.readSessionTimer();


    if (stored) {

      if (
        stored.state
        === 'finished'
      ) {

        this.sessionState =
          'finished';

        this.elapsedSeconds =
          Math.max(
            0,
            Number(
              stored.elapsedSeconds
              || 0
            )
          );

        this.timerBaseSeconds =
          this.elapsedSeconds;

        this.timerRunningSinceMs =
          null;

        return;
      }


      if (
        stored.state
        === 'paused'
      ) {

        this.sessionState =
          'paused';

        this.elapsedSeconds =
          Math.max(
            0,
            Number(
              stored.elapsedSeconds
              || 0
            )
          );

        this.timerBaseSeconds =
          this.elapsedSeconds;

        this.timerRunningSinceMs =
          null;

        return;
      }


      if (
        stored.state
        === 'running'
      ) {

        this.startRunningTimer(
          Math.max(
            0,
            Number(
              stored.elapsedSeconds
              || 0
            )
          ),

          Number(
            stored.runningSinceMs
            || Date.now()
          )
        );

        return;
      }
    }


    if (
      String(
        exam.status
        || ''
      ).toUpperCase()
      === 'EN_COURS'
    ) {

      this.beginSessionTimer(
        exam.started_at
      );

      return;
    }


    this.sessionState =
      'idle';

    this.elapsedSeconds =
      0;

    this.timerBaseSeconds =
      0;

    this.timerRunningSinceMs =
      null;
  }



  private getSessionTimerStorageKey():
    string {

    const exam =
      this.assignedExam;

    if (!exam) {
      return '';
    }

    return (
      'secureexam_student_timer_'
      + String(
          exam.assignment_id
        )
    );
  }


  private readSessionTimer():
    any | null {

    const key =
      this.getSessionTimerStorageKey();

    if (!key) {
      return null;
    }


    const raw =
      localStorage.getItem(
        key
      );

    if (!raw) {
      return null;
    }


    try {

      return JSON.parse(
        raw
      );

    } catch {

      localStorage.removeItem(
        key
      );

      return null;
    }
  }


  private persistSessionTimer(): void {

    const key =
      this.getSessionTimerStorageKey();

    if (!key) {
      return;
    }


    localStorage.setItem(
      key,
      JSON.stringify({
        state:
          this.sessionState,

        elapsedSeconds:
          this.timerBaseSeconds,

        runningSinceMs:
          this.timerRunningSinceMs
      })
    );
  }


  private parseStartedAt(
    startedAt: string
  ): number {

    const date =
      new Date(
        String(
          startedAt
        ).replace(
          ' ',
          'T'
        )
      );


    const timestamp =
      date.getTime();


    if (
      Number.isNaN(
        timestamp
      )
    ) {

      return Date.now();
    }


    return timestamp;
  }


  private beginSessionTimer(
    startedAt: string
  ): void {

    const startedMs =
      this.parseStartedAt(
        startedAt
      );


    this.startRunningTimer(
      0,
      startedMs
    );


    this.persistSessionTimer();
  }


  private startRunningTimer(
    baseSeconds: number,
    runningSinceMs: number
  ): void {

    this.stopTimer();


    this.sessionState =
      'running';

    this.timerBaseSeconds =
      Math.max(
        0,
        Math.floor(
          baseSeconds
        )
      );

    this.timerRunningSinceMs =
      runningSinceMs;


    const refresh = () => {

      if (
        this.sessionState
        !== 'running'
        || this.timerRunningSinceMs
        === null
      ) {
        return;
      }


      const additional =
        Math.max(
          0,
          Math.floor(
            (
              Date.now()
              - this.timerRunningSinceMs
            )
            / 1000
          )
        );


      this.elapsedSeconds =
        this.timerBaseSeconds
        + additional;


      this.cdr.detectChanges();
    };


    refresh();


    this.timerHandle =
      setInterval(
        refresh,
        1000
      );
  }


  pauseExam(): void {

    if (
      !this.examRunning
    ) {
      return;
    }


    if (
      this.timerRunningSinceMs
      !== null
    ) {

      const additional =
        Math.max(
          0,
          Math.floor(
            (
              Date.now()
              - this.timerRunningSinceMs
            )
            / 1000
          )
        );


      this.elapsedSeconds =
        this.timerBaseSeconds
        + additional;
    }


    this.stopTimer();


    this.sessionState =
      'paused';

    this.timerBaseSeconds =
      this.elapsedSeconds;

    this.timerRunningSinceMs =
      null;


    this.persistSessionTimer();

    this.refreshStudentIcons();

    this.cdr.detectChanges();
  }


  resumeExam(): void {

    if (
      !this.examPaused
    ) {
      return;
    }


    this.timerBaseSeconds =
      this.elapsedSeconds;

    this.timerRunningSinceMs =
      Date.now();

    this.sessionState =
      'running';


    this.persistSessionTimer();


    this.startRunningTimer(
      this.timerBaseSeconds,
      this.timerRunningSinceMs
    );


    this.refreshStudentIcons();

    this.cdr.detectChanges();
  }


  finishExam(): void {

    if (
      !this.examStarted
      || this.examFinished
    ) {
      return;
    }


    const confirmed =
      window.confirm(
        (
          'Voulez-vous vraiment terminer '
          + 'l’examen ?\n\n'
          + 'Le chronomètre sera '
          + 'définitivement arrêté.'
        )
      );


    if (!confirmed) {
      return;
    }


    if (
      this.examRunning
      && this.timerRunningSinceMs
      !== null
    ) {

      const additional =
        Math.max(
          0,
          Math.floor(
            (
              Date.now()
              - this.timerRunningSinceMs
            )
            / 1000
          )
        );


      this.elapsedSeconds =
        this.timerBaseSeconds
        + additional;
    }


    this.stopTimer();


    this.sessionState =
      'finished';

    this.timerBaseSeconds =
      this.elapsedSeconds;

    this.timerRunningSinceMs =
      null;


    this.persistSessionTimer();

    this.refreshStudentIcons();

    this.cdr.detectChanges();
  }



  private stopTimer(): void {

    if (
      this.timerHandle
      !== null
    ) {

      clearInterval(
        this.timerHandle
      );

      this.timerHandle = null;
    }
  }


  formatTimer():
    string {

    const hours =
      Math.floor(
        this.elapsedSeconds
        / 3600
      );

    const minutes =
      Math.floor(
        (
          this.elapsedSeconds
          % 3600
        )
        / 60
      );

    const seconds =
      this.elapsedSeconds
      % 60;


    return [
      hours,
      minutes,
      seconds
    ]
      .map(
        value =>
          String(value)
            .padStart(
              2,
              '0'
            )
      )
      .join(':');
  }


  packagesText(
    exam: StudentExam
  ): string {

    const packages =
      exam.config?.packages
      || [];

    if (
      packages.length === 0
    ) {
      return 'Aucun paquet';
    }

    return packages.join(', ');
  }


  formatDate(
    value: string
  ): string {

    if (!value) {
      return 'Non renseignée';
    }

    const date =
      new Date(
        value
      );

    if (
      Number.isNaN(
        date.getTime()
      )
    ) {
      return value;
    }

    return date.toLocaleDateString(
      'fr-FR'
    );
  }


  logout(): void {

    this.stopTimer();

    localStorage.removeItem(
      'secureexam_student_token'
    );

    localStorage.removeItem(
      'secureexam_student_username'
    );

    localStorage.removeItem(
      'secureexam_student_number'
    );

    localStorage.removeItem(
      'secureexam_student_full_name'
    );

    this.logoutRequested.emit();
  }
}
