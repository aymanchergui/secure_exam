// Redirection visuelle propre : la racine devient /accueil
if (window.location.pathname === '/' || window.location.pathname === '') {
  window.history.replaceState({}, '', '/accueil');
}

import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';

bootstrapApplication(App, appConfig)
  .catch((err) => console.error(err));
