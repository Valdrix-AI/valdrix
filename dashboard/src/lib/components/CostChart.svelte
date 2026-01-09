<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import {
    Chart,
    Title,
    Tooltip,
    Legend,
    BarElement,
    CategoryScale,
    LinearScale,
    BarController
  } from 'chart.js';

  Chart.register(
    Title,
    Tooltip,
    Legend,
    BarElement,
    CategoryScale,
    LinearScale,
    BarController
  );

  export let data: any[] = [];
  
  let canvas: HTMLCanvasElement;
  let chart: Chart;

  // Color palette for services
  const colors = [
    '#5C5CFF', // Primary (Indigo)
    '#00C897', // Success (Emerald)
    '#FF3D71', // Danger (Rose)
    '#FFB800', // Warning (Amber)
    '#8F5CFF', // Purple
    '#00D4FF', // Cyan
    '#FF8F5C', // Orange
    '#A0AEC0', // Gray
  ];

  function updateChart() {
    if (!chart || !data || data.length === 0) return;

    // Extract unique services
    const services = new Set<string>();
    data.forEach(day => {
      if (day.services) {
        Object.keys(day.services).forEach(s => services.add(s));
      }
    });
    
    const serviceList = Array.from(services).sort();
    
    // Prepare datasets
    const datasets = serviceList.map((service, index) => ({
      label: service,
      data: data.map(day => day.services?.[service] || 0),
      backgroundColor: colors[index % colors.length],
      borderColor: colors[index % colors.length],
      borderWidth: 1,
      borderRadius: 4,
      stack: 'Stack 0',
    }));
    
    // Format dates for labels
    const labels = data.map(day => {
      const d = new Date(day.date);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });

    chart.data = {
      labels,
      datasets
    };
    chart.update();
  }

  $: if (data) {
    updateChart();
  }

  onMount(() => {
    const ctx = canvas.getContext('2d');
    if (ctx) {
      chart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: [],
          datasets: []
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom',
              labels: {
                color: '#94a3b8',
                usePointStyle: true,
                boxWidth: 8,
              }
            },
            tooltip: {
              mode: 'index',
              intersect: false,
              backgroundColor: '#1e293b',
              titleColor: '#f8fafc',
              bodyColor: '#cbd5e1',
              borderColor: '#334155',
              borderWidth: 1,
            }
          },
          scales: {
            x: {
              grid: {
                display: false,
                color: '#334155'
              },
              ticks: {
                color: '#64748b'
              },
              stacked: true,
            },
            y: {
              grid: {
                color: '#1e293b'
              },
              ticks: {
                color: '#64748b',
                callback: (value) => '$' + value
              },
              stacked: true,
              beginAtZero: true
            }
          }
        }
      });
      updateChart();
    }
  });

  onDestroy(() => {
    if (chart) {
      chart.destroy();
    }
  });
</script>

<div class="h-full w-full min-h-[300px]">
  <canvas bind:this={canvas}></canvas>
  {#if data.length === 0}
    <div class="absolute inset-0 flex items-center justify-center text-ink-500 text-sm">
      No cost data available for this period
    </div>
  {/if}
</div>
