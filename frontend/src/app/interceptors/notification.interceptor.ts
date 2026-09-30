import {
  HttpErrorResponse,
  HttpInterceptorFn,
  HttpResponse
} from '@angular/common/http';

import {
  inject
} from '@angular/core';

import {
  catchError,
  tap,
  throwError
} from 'rxjs';

import {
  NotificationService
} from '../services/notification.service';


function isMutation(
  method: string
): boolean {

  return [
    'POST',
    'PUT',
    'PATCH',
    'DELETE'
  ].includes(
    method.toUpperCase()
  );
}


function ignoredRequest(
  url: string
): boolean {

  const value =
    url.toLowerCase();

  const ignored = [
    '/auth/login',
    '/student/login',
    '/admin/login',
    '/login',
    '/heartbeat',
    '/search',
    '/preview',
    '/verify',
    '/validate'
  ];

  return ignored.some(
    item =>
      value.includes(item)
  );
}


function successTitle(
  method: string,
  url: string
): string {

  const value =
    url.toLowerCase();

  if (
    value.includes(
      'support-requests'
    )
  ) {

    return 'Demande envoyée';
  }

  if (
    value.includes('/start')
  ) {

    return 'Session démarrée';
  }

  if (
    value.includes('/finish')
    || value.includes('/complete')
  ) {

    return 'Session terminée';
  }

  switch (
    method.toUpperCase()
  ) {

    case 'DELETE':

      return 'Suppression effectuée';

    case 'PUT':
    case 'PATCH':

      return 'Modification enregistrée';

    default:

      return 'Opération réussie';
  }
}


function successMessage(
  method: string,
  url: string,
  body: unknown
): string {

  if (
    body !== null
    && typeof body === 'object'
    && 'message' in body
  ) {

    const value =
      (
        body as {
          message?: unknown;
        }
      ).message;

    if (
      typeof value === 'string'
      && value.trim()
    ) {

      return value.trim();
    }
  }

  if (
    url.toLowerCase()
      .includes(
        'support-requests'
      )
  ) {

    return (
      'Votre demande de support '
      + 'a bien été transmise.'
    );
  }

  switch (
    method.toUpperCase()
  ) {

    case 'DELETE':

      return (
        'L’élément a été supprimé '
        + 'avec succès.'
      );

    case 'PUT':
    case 'PATCH':

      return (
        'Les modifications ont été '
        + 'enregistrées avec succès.'
      );

    default:

      return (
        'L’opération a été effectuée '
        + 'avec succès.'
      );
  }
}


function errorMessage(
  error: HttpErrorResponse
): string {

  const detail =
    error?.error?.detail;

  if (
    typeof detail === 'string'
    && detail.trim()
  ) {

    return detail.trim();
  }

  const message =
    error?.error?.message;

  if (
    typeof message === 'string'
    && message.trim()
  ) {

    return message.trim();
  }

  if (
    error.status === 0
  ) {

    return (
      'Impossible de joindre '
      + 'le serveur SecureExam.'
    );
  }

  if (
    error.status === 401
    || error.status === 403
  ) {

    return (
      'Vous n’êtes pas autorisé '
      + 'à effectuer cette opération.'
    );
  }

  if (
    error.status === 404
  ) {

    return (
      'La ressource demandée '
      + 'est introuvable.'
    );
  }

  return (
    'L’opération n’a pas pu '
    + 'être effectuée.'
  );
}


export const notificationInterceptor:
  HttpInterceptorFn =
  (request, next) => {

    const notifications =
      inject(
        NotificationService
      );

    const notify =
      isMutation(
        request.method
      )
      && !ignoredRequest(
        request.url
      );

    if (!notify) {

      return next(request);
    }

    return next(request).pipe(

      tap(event => {

        if (
          event
          instanceof HttpResponse
        ) {

          notifications.success(
            successMessage(
              request.method,
              request.url,
              event.body
            ),
            successTitle(
              request.method,
              request.url
            )
          );
        }
      }),

      catchError(
        (
          error:
            HttpErrorResponse
        ) => {

          notifications.error(
            errorMessage(error),
            'Échec de l’opération'
          );

          return throwError(
            () => error
          );
        }
      )
    );
  };
