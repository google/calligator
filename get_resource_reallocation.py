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

"""Identifies resource reallocation candidates from Jaeger traces and metrics."""

import argparse
import json
import re
from typing import Dict, List, Tuple

from . import df_utils
from .graph import GraphCollection


def parse_metrics_file(filepath: str) -> Dict[str, Dict[str, str]]:
  """Reads a metrics file and saves the information into a dictionary.

  Args:
      filepath: The path to the metrics file.

  Returns:
      A dictionary where keys are app names and values are dictionaries
      containing 'cpu', 'cpu_percent', 'memory', and 'memory_percent'.
  """
  metrics_data = {}
  try:
    resource_path = f'experimental/sysres/critical_path/{filepath}'
    with open(resource_path, 'r') as f:
      for line in f:
        if ':' in line:
          try:
            app_name, metrics_str = line.split(':', 1)
            app_name = app_name.strip()
            metrics = {}

            # Use regex to extract CPU and Memory information
            cpu_match = re.search(r'CPU=([\d.]+m) \(([\d.]+%)\)', metrics_str)
            memory_match = re.search(
                r'Memory=([\d.]+Mi) \(([\d.]+%)\)', metrics_str
            )

            if cpu_match:
              metrics['cpu'] = cpu_match.group(1)
              metrics['cpu_percent'] = cpu_match.group(2)
            if memory_match:
              metrics['memory'] = memory_match.group(1)
              metrics['memory_percent'] = memory_match.group(2)

            if metrics:
              metrics_data[app_name] = metrics
          except ValueError:
            print(f'Warning: Could not parse line: {line.strip()}')
  except FileNotFoundError:
    print(f'Error: File not found at {filepath}')
    raise
  return metrics_data


def _get_service_metrics(
    metrics_data: Dict[str, Dict[str, str]], service_name: str
) -> Tuple[str, float, float]:
  """Extracts service metrics from metrics_data."""
  if '.default' in service_name:
    service_name = service_name.replace('.default', '')
  metrics = metrics_data[service_name]
  cpu_percent = float(metrics['cpu_percent'].strip('%')) / 100
  memory_percent = float(metrics['memory_percent'].strip('%')) / 100
  return service_name, cpu_percent, memory_percent


def _calculate_scores(
    value: float,
    cpu_percent: float,
    memory_percent: float,
    drag_only: bool,
    utilization_only: bool,
) -> Tuple[float, float]:
  """Calculates CPU and memory scores based on value and flags."""
  if drag_only:
    return value, value
  elif utilization_only:
    return cpu_percent, memory_percent
  else:
    return cpu_percent * value, memory_percent * value


def get_reallocation_candidates(
    collection: GraphCollection,
    resource_utilization_path: str,
    num_recommendations: int,
    drag_only: bool = False,
    utilization_only: bool = False,
) -> Tuple[
    List[Tuple[str, float]],
    List[Tuple[str, float]],
    List[Tuple[str, float]],
    List[Tuple[str, float]],
]:
  """Gets reallocation candidates based on drag, slack, and resource utilization.

  Args:
    collection: A GraphCollection object containing trace data.
    resource_utilization_path: Path to the resource utilization file.
    num_recommendations: The number of top/bottom candidates to return.
    drag_only: If True, use only drag for scoring.
    utilization_only: If True, use only utilization for scoring.

  Returns:
    A tuple containing four lists:
    - top_cpu_drag: Top N services with highest CPU score.
    - least_cpu_drag: Bottom N services with lowest CPU score.
    - top_memory_drag: Top N services with highest Memory score.
    - least_memory_drag: Bottom N services with lowest Memory score.
  """
  metrics_data = parse_metrics_file(resource_utilization_path)
  most_drag_data = collection.get_most_average_drag_by_method()
  most_slack_data = collection.get_most_average_slack_by_method()

  if drag_only:
    print('Using drag only to calculate the reallocation candidates.')
  elif utilization_only:
    print('Using utilization only to calculate the reallocation candidates.')

  most_cpu_drag_scores = []
  most_memory_drag_scores = []
  for service, drag_value in most_drag_data:
    try:
      service_name, cpu_percent, memory_percent = _get_service_metrics(
          metrics_data, service
      )
      cpu_score, memory_score = _calculate_scores(
          drag_value, cpu_percent, memory_percent, drag_only, utilization_only
      )
      most_cpu_drag_scores.append((service_name, cpu_score))
      most_memory_drag_scores.append((service_name, memory_score))
    except KeyError:
      print(f'Warning: Service {service} not found in metrics data.')

  most_cpu_slack_scores = []
  most_memory_slack_scores = []
  for service, slack_value in most_slack_data:
    try:
      service_name, cpu_percent, memory_percent = _get_service_metrics(
          metrics_data, service
      )
      cpu_score, memory_score = _calculate_scores(
          slack_value, cpu_percent, memory_percent, drag_only, utilization_only
      )
      most_cpu_slack_scores.append((service_name, cpu_score))
      most_memory_slack_scores.append((service_name, memory_score))
    except KeyError:
      print(f'Warning: Service {service} not found in metrics data.')

  # Sort to find most and least drag services
  most_cpu_drag_scores.sort(key=lambda x: x[1], reverse=True)
  most_memory_drag_scores.sort(key=lambda x: x[1], reverse=True)
  least_cpu_drag_scores = sorted(most_cpu_drag_scores, key=lambda x: x[1])
  least_memory_drag_scores = sorted(most_memory_drag_scores, key=lambda x: x[1])

  # Get top and bottom k recommendations
  top_cpu_drag = most_cpu_drag_scores[:num_recommendations]
  top_memory_drag = most_memory_drag_scores[:num_recommendations]
  least_cpu_drag = least_cpu_drag_scores[:num_recommendations]
  least_memory_drag = least_memory_drag_scores[:num_recommendations]

  print(f'Top {num_recommendations} CPU Drag: {top_cpu_drag}')
  print(f'Least {num_recommendations} CPU Drag: {least_cpu_drag}')
  print(f'Top {num_recommendations} Memory Drag: {top_memory_drag}')
  print(f'Least {num_recommendations} Memory Drag: {least_memory_drag}')

  return top_cpu_drag, least_cpu_drag, top_memory_drag, least_memory_drag


def read_jaeger_traces_to_collection(filepath: str) -> GraphCollection:
  """Reads a Jaeger traces file and loads it into a GraphCollection.

  Args:
    filepath: The path to the Jaeger traces file.

  Returns:
    A GraphCollection object containing trace data.
  """
  resource_path = f'experimental/sysres/critical_path/{filepath}'
  with open(resource_path, 'r') as f:
    data = json.load(f)

  data_df = df_utils.get_df_from_jaeger_json(data)
  collection = GraphCollection(df=data_df, max_traces=5000)
  return collection


def main() -> None:
  # get the command line arguments
  parser = argparse.ArgumentParser(
      description='Get resource reallocation candidates.'
  )
  # get the file path of the jaeger traces
  parser.add_argument(
      '--jaeger_traces_path',
      required=True,
      help='The path to the jaeger traces file.',
  )
  parser.add_argument(
      '--resource_utilization_path',
      required=True,
      help='The path to the resources file.',
  )
  # get number of recommendations to return
  parser.add_argument(
      '--num_recommendations',
      type=int,
      default=3,
      help='The number of recommendations to return.',
  )
  # if this flag is provided, then we will use drag only to calculate the
  # reallocation candidates
  parser.add_argument(
      '--drag_only',
      action='store_true',
      help=(
          'If this flag is provided, only use drag to calculate the'
          ' reallocation candidates.'
      ),
  )
  # if this flag is provided, then we will use utilization only to calculate
  # the reallocation candidates
  parser.add_argument(
      '--utilization_only',
      action='store_true',
      help=(
          'If true, only use utilization to calculate the reallocation'
          ' candidates.'
      ),
  )

  args = parser.parse_args()
  jaeger_traces_path = args.jaeger_traces_path
  resource_utilization_path = args.resource_utilization_path
  num_recommendations = args.num_recommendations
  collection = read_jaeger_traces_to_collection(jaeger_traces_path)
  get_reallocation_candidates(
      collection,
      resource_utilization_path,
      num_recommendations,
      args.drag_only,
      args.utilization_only,
  )


if __name__ == '__main__':
  main()
