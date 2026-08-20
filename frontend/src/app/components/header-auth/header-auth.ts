import { CommonModule } from '@angular/common';
import { Component, AfterViewInit } from '@angular/core';

declare global {
  interface Window {
    lucide?: {
      createIcons: () => void;
    };
  }
}

@Component({
  selector: 'app-header-auth',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './header-auth.html',
  styleUrl: './header-auth.css'
})
export class HeaderAuthComponent implements AfterViewInit {
  showProjectInfoModal = false;
  currentYear = new Date().getFullYear();
  appVersion = 'Chargement...';

  ngAfterViewInit(): void {
    this.loadProjectVersion();
    this.refreshIcons();
  }

  openProjectInfoModal(): void {
    this.showProjectInfoModal = true;
    this.refreshIcons();
  }

  closeProjectInfoModal(): void {
    this.showProjectInfoModal = false;
    this.refreshIcons();
  }

  loadProjectVersion(): void {
    fetch(`/assets/VERSION?ts=${Date.now()}`)
      .then((response) => {
        if (!response.ok) {
          throw new Error('Fichier VERSION introuvable.');
        }

        return response.text();
      })
      .then((version) => {
        const cleanVersion = version.trim();
        this.appVersion = cleanVersion || 'Non renseignée';
        this.refreshIcons();
      })
      .catch(() => {
        this.appVersion = 'Non renseignée';
        this.refreshIcons();
      });
  }

  refreshIcons(): void {
    setTimeout(() => {
      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
      }
    }, 50);
  }
}
