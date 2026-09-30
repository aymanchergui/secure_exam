import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export type NotificationType =
  | 'success'
  | 'error'
  | 'warning'
  | 'info';

export interface AppNotification {
  id: number;
  type: NotificationType;
  title: string;
  message: string;
  duration: number;
}

@Injectable({
  providedIn: 'root'
})
export class NotificationService {

  private sequence = 0;

  private readonly subject =
    new BehaviorSubject<AppNotification[]>([]);

  readonly notifications$ =
    this.subject.asObservable();

  private readonly timers =
    new Map<number, number>();

  success(
    message: string,
    title = 'Opération réussie',
    duration = 4200
  ): void {

    this.show(
      'success',
      title,
      message,
      duration
    );
  }

  error(
    message: string,
    title = 'Une erreur est survenue',
    duration = 6500
  ): void {

    this.show(
      'error',
      title,
      message,
      duration
    );
  }

  warning(
    message: string,
    title = 'Attention',
    duration = 5200
  ): void {

    this.show(
      'warning',
      title,
      message,
      duration
    );
  }

  info(
    message: string,
    title = 'Information',
    duration = 4500
  ): void {

    this.show(
      'info',
      title,
      message,
      duration
    );
  }

  private show(
    type: NotificationType,
    title: string,
    message: string,
    duration: number
  ): void {

    const cleanMessage =
      String(message || '').trim();

    if (!cleanMessage) {
      return;
    }

    const id =
      ++this.sequence;

    const item:
      AppNotification = {

      id,
      type,
      title,
      message: cleanMessage,
      duration
    };

    this.subject.next(
      [
        item,
        ...this.subject.value
      ].slice(0, 4)
    );

    const timer =
      window.setTimeout(
        () => this.dismiss(id),
        duration
      );

    this.timers.set(
      id,
      timer
    );
  }

  dismiss(
    id: number
  ): void {

    const timer =
      this.timers.get(id);

    if (
      timer !== undefined
    ) {

      window.clearTimeout(
        timer
      );

      this.timers.delete(
        id
      );
    }

    this.subject.next(
      this.subject.value.filter(
        item =>
          item.id !== id
      )
    );
  }

  clear(): void {

    for (
      const timer
      of this.timers.values()
    ) {

      window.clearTimeout(
        timer
      );
    }

    this.timers.clear();

    this.subject.next([]);
  }
}
