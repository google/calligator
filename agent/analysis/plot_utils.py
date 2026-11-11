# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Matplotlib utility module for generating trace analysis plots (bar charts and CDFs)."""

import os
from typing import Any, Dict, Optional

import matplotlib
import matplotlib.pyplot as plt
import numpy as np


matplotlib.use('Agg')


def _save_figure(fig: Any, output_path: str) -> None:
  """Saves a matplotlib figure safely.

  Args:
    fig: The matplotlib Figure to save.
    output_path: Path where the figure will be saved.
  """
  parent_dir = os.path.dirname(output_path)
  if parent_dir:
    os.makedirs(parent_dir, exist_ok=True)
  fig.savefig(output_path, bbox_inches='tight', dpi=150)


def plot_rank_drag(
    data: Dict[str, Any],
    output_path: Optional[str] = None,
    show_plot: bool = False,
) -> None:
  """Generates a horizontal bar chart of top exclusive drag methods.

  Args:
    data: A dictionary containing rank drag analysis results.
    output_path: Optional path to save the generated figure.
    show_plot: Whether to display the plot interactively.
  """
  rankings = data.get('rankings', [])
  if not rankings:
    return

  methods = [r['method'] for r in reversed(rankings)]
  stat = data.get('stat', 'exclusive_drag_sec')
  drag_vals = [
      r.get(stat, r.get('exclusive_drag_sec', 0.0)) for r in reversed(rankings)
  ]

  vals = [v * 1000.0 for v in drag_vals]
  unit = 'ms'

  p_start = data.get('percentile_start', None)
  p_end = data.get('percentile_end', None)
  stat_label = stat[:-4] if stat.endswith('_sec') else stat
  stat_str = stat_label.upper()

  if p_start is not None and p_end is not None:
    bracket_str = f' (p{p_start:.0f}-p{p_end:.0f})'
    label_bracket = f', p{p_start:.0f}-p{p_end:.0f}'
  else:
    bracket_str = ''
    label_bracket = ''

  fig, ax = plt.subplots(figsize=(10, max(4, len(methods) * 0.4)))
  ax.barh(methods, vals, color='#1f77b4')
  ax.set_xlabel(f'Exclusive Drag ({unit}) [{stat_str}{label_bracket}]')
  ax.set_ylabel('RPC Method')
  ax.set_title(
      f'Top-{len(rankings)} Exclusive Drag Ranking along Critical Path'
      f'{bracket_str} (Stat: {stat_str})'
  )
  ax.grid(True, linestyle='--', alpha=0.5, axis='x')

  plt.tight_layout()
  if output_path:
    _save_figure(fig, output_path)
  if show_plot:
    plt.show()
  plt.close(fig)


def plot_distribution(
    data: Dict[str, Any],
    output_path: Optional[str] = None,
    show_plot: bool = False,
) -> None:
  """Generates cumulative distribution function (CDF) plots for distribution mode.

  Args:
    data: A dictionary containing distribution analysis results.
    output_path: Optional path to save the generated figure.
    show_plot: Whether to display the plot interactively.
  """
  metrics_data = data.get('metrics', {})
  if not metrics_data:
    return

  # Ensure there is actually data to plot to avoid empty figures and
  # legend warnings.
  has_data = False
  for values in metrics_data.values():
    orig = values.get('original', [])
    ret = values.get('retimed', [])
    if (orig and len(orig) > 0) or (ret and len(ret) > 0):
      has_data = True
      break
  if not has_data:
    return

  metric_filter = data.get('metric_filter', '')
  plot_drag_type = data.get('plot_drag_type', 'exclusive')
  drag_key = f'{plot_drag_type}_drag'
  drag_label = (
      'Exclusive Drag' if plot_drag_type == 'exclusive' else 'Inclusive Drag'
  )

  is_all_mode = metric_filter == 'all' or (
      'slack' in metrics_data
      and drag_key in metrics_data
      and len(metrics_data) > 1
  )

  target_method = data.get('target_method', None)
  target_service = data.get('target_service', None)
  if target_method:
    target_context = f'Method: {target_method}'
  elif target_service:
    target_context = f'Service: {target_service}'
  else:
    target_context = 'Root Node'

  if is_all_mode:
    fig, ax = plt.subplots(figsize=(10, 6))

    orig_slack = [
        s * 1000.0 for s in metrics_data.get('slack', {}).get('original', [])
    ]
    orig_drag = [
        d * 1000.0 for d in metrics_data.get(drag_key, {}).get('original', [])
    ]
    ret_slack = [
        s * 1000.0 for s in metrics_data.get('slack', {}).get('retimed', [])
    ]
    ret_drag = [
        d * 1000.0 for d in metrics_data.get(drag_key, {}).get('retimed', [])
    ]

    orig_x = None
    if orig_slack and orig_drag:
      orig_x = np.array(
          [d if d > 0 else -abs(s) for s, d in zip(orig_slack, orig_drag)]
      )
    elif orig_drag:
      orig_x = np.array(orig_drag)
    elif orig_slack:
      orig_x = np.array([-abs(s) for s in orig_slack])

    sample_size = len(orig_x) if orig_x is not None else 0

    # Baseline (Original)
    if orig_x is not None and len(orig_x) > 0:
      sort_idx = np.argsort(orig_x)
      orig_x_sorted = orig_x[sort_idx]
      orig_y = np.arange(1, len(orig_x_sorted) + 1) / len(orig_x_sorted)

      # Interpolate to find exact Y value where line crosses X=0
      orig_y_cross = float(
          np.interp(0.0, orig_x_sorted, orig_y, left=0.0, right=1.0)
      )

      # Plot Baseline Slack (X <= 0, Good color: blue)
      if np.any(orig_x_sorted <= 0):
        orig_slack_x = list(orig_x_sorted[orig_x_sorted <= 0])
        orig_slack_y = list(orig_y[orig_x_sorted <= 0])
        if orig_slack_x[-1] != 0.0:
          orig_slack_x.append(0.0)
          orig_slack_y.append(orig_y_cross)
        ax.plot(
            orig_slack_x,
            orig_slack_y,
            color='#1f77b4',
            linestyle='-',
            linewidth=2.0,
            label='Baseline Slack',
        )

      # Plot Baseline Drag (X > 0, Bad color: red/orange)
      if np.any(orig_x_sorted > 0):
        orig_drag_x = [0.0] + list(orig_x_sorted[orig_x_sorted > 0])
        orig_drag_y = [orig_y_cross] + list(orig_y[orig_x_sorted > 0])
        ax.plot(
            orig_drag_x,
            orig_drag_y,
            color='#d62728',
            linestyle='-',
            linewidth=2.0,
            label=f'Baseline {drag_label}',
        )

    # Retimed
    ret_x = None
    if ret_slack and ret_drag:
      ret_x = np.array(
          [d if d > 0 else -abs(s) for s, d in zip(ret_slack, ret_drag)]
      )
    elif ret_drag:
      ret_x = np.array(ret_drag)
    elif ret_slack:
      ret_x = np.array([-abs(s) for s in ret_slack])

    if ret_x is not None and len(ret_x) > 0:
      sort_idx_ret = np.argsort(ret_x)
      ret_x_sorted = ret_x[sort_idx_ret]
      ret_y = np.arange(1, len(ret_x_sorted) + 1) / len(ret_x_sorted)

      # Interpolate to find exact Y value where line crosses X=0
      ret_y_cross = float(
          np.interp(0.0, ret_x_sorted, ret_y, left=0.0, right=1.0)
      )

      # Plot Retimed Slack (X <= 0, Good color: dashed green)
      if np.any(ret_x_sorted <= 0):
        ret_slack_x = list(ret_x_sorted[ret_x_sorted <= 0])
        ret_slack_y = list(ret_y[ret_x_sorted <= 0])
        if ret_slack_x[-1] != 0.0:
          ret_slack_x.append(0.0)
          ret_slack_y.append(ret_y_cross)
        ax.plot(
            ret_slack_x,
            ret_slack_y,
            color='#2ca02c',
            linestyle='--',
            linewidth=2.0,
            label='Retimed Slack',
        )

      # Plot Retimed Drag (X > 0, Bad color: dashed orange)
      if np.any(ret_x_sorted > 0):
        ret_drag_x = [0.0] + list(ret_x_sorted[ret_x_sorted > 0])
        ret_drag_y = [ret_y_cross] + list(ret_y[ret_x_sorted > 0])
        ax.plot(
            ret_drag_x,
            ret_drag_y,
            color='#ff7f0e',
            linestyle='--',
            linewidth=2.0,
            label=f'Retimed {drag_label}',
        )

    ax.axvline(0, color='gray', linestyle=':', alpha=0.7)
    ax.set_xlabel(f'Slack (X <= 0, ms) / {drag_label} (X > 0, ms)')
    ax.set_ylabel('CDF')
    ax.set_title(f'Continuous Latency CDF ({target_context}, N={sample_size})')
    ax.legend(loc='lower right')
    ax.grid(True, linestyle='--', alpha=0.5)

  else:
    num_metrics = len(metrics_data)
    fig, axes = plt.subplots(
        num_metrics, 1, figsize=(8, 3.5 * num_metrics), squeeze=False
    )

    for idx, (metric_name, values) in enumerate(metrics_data.items()):
      ax = axes[idx, 0]
      orig = values.get('original', [])
      retimed = values.get('retimed', [])

      if orig:
        sorted_orig = np.sort(orig) * 1000.0
        cdf_orig = np.arange(1, len(sorted_orig) + 1) / len(sorted_orig)
        ax.plot(
            sorted_orig,
            cdf_orig,
            label='Original',
            color='#1f77b4',
            linewidth=2,
        )

      if retimed:
        sorted_ret = np.sort(retimed) * 1000.0
        cdf_ret = np.arange(1, len(sorted_ret) + 1) / len(sorted_ret)
        ax.plot(
            sorted_ret,
            cdf_ret,
            label='Retimed',
            color='#ff7f0e',
            linestyle='--',
            linewidth=2,
        )

      ax.set_xlabel(f'{metric_name.replace("_", " ").title()} (ms)')
      ax.set_ylabel('CDF')
      ax.set_title(f'Distribution: {metric_name}')
      ax.legend(loc='lower right')
      ax.grid(True, linestyle='--', alpha=0.5)

  plt.tight_layout()
  if output_path:
    _save_figure(fig, output_path)
  if show_plot:
    plt.show()
  plt.close(fig)


def plot_percent_improvement(
    data: Dict[str, Any],
    output_path: Optional[str] = None,
    show_plot: bool = False,
) -> None:
  """Generates a 3-panel CDF plot for percent improvement simulation mode.

  Args:
    data: A dictionary containing percent improvement simulation results.
    output_path: Optional path to save the generated figure.
    show_plot: Whether to display the plot interactively.
  """
  orig = data.get('original_durations_sec', [])
  retimed = data.get('retimed_durations_sec', [])
  saved = data.get('saved_sec', [])
  pct_imp = data.get('percent_improvements', [])

  if not orig or len(orig) == 0:
    return

  fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 4.5))

  # Panel 1: Original vs Retimed Latency CDF
  s_orig = np.sort(orig) * 1000.0
  s_ret = np.sort(retimed) * 1000.0
  ax1.plot(
      s_orig,
      np.arange(1, len(s_orig) + 1) / len(s_orig),
      label='Original',
      color='#1f77b4',
      linewidth=2,
  )
  ax1.plot(
      s_ret,
      np.arange(1, len(s_ret) + 1) / len(s_ret),
      label='Retimed',
      color='#2ca02c',
      linestyle='--',
      linewidth=2,
  )
  ax1.set_xlabel('E2E Latency (ms)')
  ax1.set_ylabel('CDF')
  ax1.set_title('E2E Latency CDF')
  ax1.legend(loc='lower right')
  ax1.grid(True, linestyle='--', alpha=0.5)

  # Panel 2: Saved Time CDF
  s_saved = np.sort(saved) * 1000.0
  ax2.plot(
      s_saved,
      np.arange(1, len(s_saved) + 1) / len(s_saved),
      color='#ff7f0e',
      linewidth=2,
  )
  ax2.set_xlabel('Time Saved (ms)')
  ax2.set_ylabel('CDF')
  ax2.set_title('Absolute Time Saved (ms)')
  ax2.grid(True, linestyle='--', alpha=0.5)

  # Panel 3: Percent Improvement CDF
  s_pct = np.sort(pct_imp)
  ax3.plot(
      s_pct,
      np.arange(1, len(s_pct) + 1) / len(s_pct),
      color='#d62728',
      linewidth=2,
  )
  ax3.set_xlabel('Percent Improvement (%)')
  ax3.set_ylabel('CDF')
  ax3.set_title('Percent Improvement (%)')
  ax3.grid(True, linestyle='--', alpha=0.5)

  plt.tight_layout()
  if output_path:
    _save_figure(fig, output_path)
  if show_plot:
    plt.show()
  plt.close(fig)
