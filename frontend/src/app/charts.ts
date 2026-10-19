import {
  Chart,
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend
} from 'chart.js';

// Registra só os componentes usados pelos dashboards (Chart.js 4 é modular).
Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend);

export { Chart };
