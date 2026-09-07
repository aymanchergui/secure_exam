import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, EventEmitter, Output } from '@angular/core';
import { PublicHeaderComponent } from '../../components/public-header/public-header';

declare const lucide: any;

@Component({
  selector: 'app-accueil',
  standalone: true,
  imports: [CommonModule, PublicHeaderComponent],
  templateUrl: './accueil.html',
  styleUrl: './accueil.css'
})
export class AccueilComponent implements AfterViewInit {
  openSupportPage(): void {
    window.location.href = '/support';
  }


  @Output() professorSelected = new EventEmitter<void>();
  @Output() supervisorSelected = new EventEmitter<void>();
  @Output() supportRequested = new EventEmitter<void>();

  ngAfterViewInit(): void {
    setTimeout(() => {
      if (typeof lucide !== 'undefined') {
        lucide.createIcons();
      }
    });
  }
}
