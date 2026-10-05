import { Injectable } from '@angular/core';
import { Resolve } from '@angular/router';
import { Observable, catchError, map, of } from 'rxjs';
import { ApiService } from '../services/api.service';

export interface PainelMatriculas {
  ok: boolean;
  enrollments: any[];
}

// Carrega as matrículas antes da rota /student ser ativada: a tela já nasce com os dados.
@Injectable({ providedIn: 'root' })
export class EnrollmentsResolver implements Resolve<PainelMatriculas> {
  constructor(private api: ApiService) { }

  resolve(): Observable<PainelMatriculas> {
    return this.api.getMyEnrollments().pipe(
      map((res: any) => ({ ok: true, enrollments: res.enrollments || [] })),
      catchError(err => {
        console.error('Error loading enrollments', err);
        return of({ ok: false, enrollments: [] });
      })
    );
  }
}
