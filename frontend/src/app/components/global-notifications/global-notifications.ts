import {
  ChangeDetectionStrategy,
  Component,
  inject
} from '@angular/core';

import {
  CommonModule
} from '@angular/common';

import {
  AppNotification,
  NotificationService,
  NotificationType
} from '../../services/notification.service';


@Component({
  selector: 'app-global-notifications',

  standalone: true,

  imports: [
    CommonModule
  ],

  changeDetection:
    ChangeDetectionStrategy.OnPush,

  template: `
    <div
      class="notification-stack"
      aria-live="polite"
    >

      <article
        *ngFor="
          let notification of notifications$ | async;
          trackBy: trackById
        "
        class="notification-toast"
        [ngClass]="notification.type"
      >

        <div class="notification-icon">
          {{ iconFor(notification.type) }}
        </div>

        <div class="notification-content">

          <strong>
            {{ notification.title }}
          </strong>

          <p>
            {{ notification.message }}
          </p>

        </div>

        <button
          type="button"
          class="notification-close"
          (click)="dismiss(notification.id)"
          aria-label="Fermer"
        >
          ×
        </button>

        <span
          class="notification-progress"
          [style.animation-duration.ms]="notification.duration"
        ></span>

      </article>

    </div>
  `,

  styles: [`
    :host {
      pointer-events: none;
    }

    .notification-stack {
      position: fixed;
      top: 92px;
      right: 22px;
      z-index: 99999;

      width:
        min(
          370px,
          calc(100vw - 32px)
        );

      display: flex;
      flex-direction: column;
      gap: 12px;

      pointer-events: none;
    }

    .notification-toast {
      --accent: #334155;

      position: relative;
      overflow: hidden;

      min-height: 76px;

      display: grid;

      grid-template-columns:
        42px
        minmax(0, 1fr)
        28px;

      align-items: center;
      gap: 12px;

      padding:
        13px
        12px
        14px
        13px;

      border:
        1px solid
        rgba(15,23,42,.09);

      border-left:
        4px solid
        var(--accent);

      border-radius: 17px;

      background:
        rgba(255,255,255,.98);

      box-shadow:
        0 20px 45px
        rgba(15,23,42,.16),
        0 5px 14px
        rgba(15,23,42,.06);

      backdrop-filter:
        blur(18px);

      pointer-events:
        auto;

      animation:
        notification-enter
        .28s
        cubic-bezier(.2,.8,.2,1);
    }

    .notification-toast.success {
      --accent: #059669;
    }

    .notification-toast.error {
      --accent: #c40024;
    }

    .notification-toast.warning {
      --accent: #d97706;
    }

    .notification-toast.info {
      --accent: #334155;
    }

    .notification-icon {
      width: 42px;
      height: 42px;

      display: flex;
      align-items: center;
      justify-content: center;

      border-radius: 13px;

      background: #f8fafc;

      color: var(--accent);

      font-size: 20px;
      font-weight: 950;
    }

    .notification-content {
      min-width: 0;
    }

    .notification-content strong {
      display: block;

      margin:
        0
        0
        4px;

      color: #111827;

      font-size: 13.5px;
      font-weight: 950;
    }

    .notification-content p {
      margin: 0;

      color: #64748b;

      font-size: 12px;
      font-weight: 650;
      line-height: 1.4;

      overflow-wrap: anywhere;
    }

    .notification-close {
      width: 28px;
      height: 28px;

      display: flex;
      align-items: center;
      justify-content: center;

      border: 0;
      border-radius: 9px;

      background: transparent;

      color: #94a3b8;

      font-size: 21px;

      cursor: pointer;
    }

    .notification-close:hover {
      background: #f1f5f9;
      color: #111827;
    }

    .notification-progress {
      position: absolute;

      left: 0;
      bottom: 0;

      width: 100%;
      height: 3px;

      background:
        var(--accent);

      transform-origin:
        left center;

      animation-name:
        notification-progress;

      animation-timing-function:
        linear;

      animation-fill-mode:
        forwards;
    }

    @keyframes notification-enter {

      from {
        opacity: 0;

        transform:
          translateX(28px)
          scale(.97);
      }

      to {
        opacity: 1;

        transform:
          translateX(0)
          scale(1);
      }
    }

    @keyframes notification-progress {

      from {
        transform:
          scaleX(1);
      }

      to {
        transform:
          scaleX(0);
      }
    }

    @media
      (max-width: 1600px)
      and (max-height: 900px) {

      .notification-stack {
        top: 78px;
        right: 18px;
        width: 340px;
      }
    }

    @media (max-width: 700px) {

      .notification-stack {
        top: 14px;
        left: 14px;
        right: 14px;
        width: auto;
      }
    }
  `]
})
export class GlobalNotificationsComponent {

  private readonly service =
    inject(
      NotificationService
    );

  readonly notifications$ =
    this.service.notifications$;


  dismiss(
    id: number
  ): void {

    this.service.dismiss(
      id
    );
  }


  trackById(
    _index: number,
    notification:
      AppNotification
  ): number {

    return notification.id;
  }


  iconFor(
    type: NotificationType
  ): string {

    switch (type) {

      case 'success':
        return '✓';

      case 'error':
      case 'warning':
        return '!';

      default:
        return 'i';
    }
  }
}
