#!/usr/bin/env python3
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

"""Manage Helm resource requests and limits in values.yaml files.

This script can read, update, or reallocate CPU and memory resources
for services defined in Helm chart values.yaml files.
"""

import argparse
from collections import defaultdict
import os
import re
import sys
from typing import Any, DefaultDict, Dict, List, Optional, Tuple

from ruamel import yaml
from ruamel.yaml import comments
from ruamel.yaml import parser
from ruamel.yaml import scanner

ScannerError = scanner.ScannerError
ParserError = parser.ParserError
CommentedMap = comments.CommentedMap
YAML = yaml.YAML

# Setup YAML instance to preserve comments and formatting
yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)


MEMORY_UNITS_TO_BYTES: Dict[str, int] = {
    'K': 1000,
    'Ki': 1024,
    'M': 1000**2,
    'Mi': 1024**2,
    'G': 1000**3,
    'Gi': 1024**3,
}
MIN_CPU_MILLICORES: int = 100
MIN_MEM_BYTES: int = 100 * 1024**2

# Mapping from service name in pod name to Helm chart key
_POD_SERVICE_TO_HELM_KEY: Dict[str, str] = {
    'productcatalogservice': 'productCatalogService',
    'currencyservice': 'currencyService',
    'shippingservice': 'shippingService',
    'emailservice': 'emailService',
    'checkoutservice': 'checkoutService',
    'recommendationservice': 'recommendationService',
    'cartservice': 'cartService',
    'paymentservice': 'paymentService',
    'adservice': 'adService',
    'loadgenerator': 'loadGenerator',
    'redis-cart': 'cartDatabase',
}


def find_values_files(base_path: str) -> List[str]:
  """Finds all relevant YAML files under the given base path.

  If base_path ends with 'helm-chart/templates', it finds all *.yaml files
  in that directory. Otherwise, it recursively finds all 'values.yaml' files.

  Args:
    base_path: The directory to search in.

  Returns:
    A list of paths to values.yaml files.
  """
  values_files: List[str] = []
  if not os.path.isdir(base_path):
    print(
        f"Error: Path '{base_path}' is not a valid directory.", file=sys.stderr
    )
    sys.exit(1)

  # Normalize the path to remove any trailing slash
  normalized_path = os.path.normpath(base_path)

  if normalized_path.endswith('helm-chart/templates'):
    print(f'Searching for *.yaml files in {base_path}')
    for item in os.listdir(base_path):
      if item.endswith('.yaml'):
        values_files.append(os.path.join(base_path, item))
  else:
    print(f'Recursively searching for values.yaml files in {base_path}')
    for root, _, files in os.walk(base_path):
      if 'values.yaml' in files:
        values_files.append(os.path.join(root, 'values.yaml'))
  return values_files


def _extract_resources_recursive(
    data: Any, file_path: str, service_prefix: str = ''
) -> List[Dict[str, Any]]:
  """Helper function to recursively search for resources blocks."""
  all_resources: List[Dict[str, Any]] = []
  if isinstance(data, dict):
    # Check if the current dict contains resource definitions
    if 'resources' in data and isinstance(data['resources'], dict):
      resources = data['resources']
      limits = resources.get('limits', {})
      requests = resources.get('requests', {})

      limit_cpu = limits.get('cpu', 'Not Set')
      limit_mem = limits.get('memory', 'Not Set')
      req_cpu = requests.get('cpu', 'Not Set')
      req_mem = requests.get('memory', 'Not Set')

      service_name = service_prefix or 'unknown_service'

      print(f'  Service: {service_name}')
      print(f'    Limits:')
      print(f'      CPU:    {limit_cpu}')
      print(f'      Memory: {limit_mem}')
      print(f'    Requests:')
      print(f'      CPU:    {req_cpu}')
      print(f'      Memory: {req_mem}')

      all_resources.append({
          'file': file_path,
          'service': service_name,
          'limits': {'cpu': limit_cpu, 'memory': limit_mem},
          'requests': {'cpu': req_cpu, 'memory': req_mem},
      })
    else:
      # Recursively search in sub-dictionaries
      for key, value in data.items():
        new_prefix = f'{service_prefix}.{key}' if service_prefix else key
        all_resources.extend(
            _extract_resources_recursive(value, file_path, new_prefix)
        )
  return all_resources


def read_resources(file_path: str) -> List[Dict[str, Any]]:
  """Reads and extracts resource limits and requests from a values.yaml file.

  Args:
      file_path (str): The path to the YAML file.

  Returns:
      list: A list of dictionaries, where each dictionary contains resource
            information for a service found in the file.
  """
  print(f'\n--- Reading: {file_path} ---')
  all_resources: List[Dict[str, Any]] = []
  try:
    with open(file_path, 'r') as f:
      data = yaml.load(f)

    all_resources = _extract_resources_recursive(data, file_path)
    return all_resources

  except (ScannerError, ParserError) as e:
    print(f'  Error: Could not parse YAML file: {e}', file=sys.stderr)
  except FileNotFoundError:
    print(f'  Error: File not found.', file=sys.stderr)
  except Exception as e:
    print(f'  An unexpected error occurred while reading: {e}', file=sys.stderr)
  return []


def parse_resource_value(value: Any) -> Tuple[float, str]:
  """Parses a resource string like '500m' or '1Gi' into (number, unit)."""
  if isinstance(value, (int, float)):
    return float(value), ''
  if value is None or value == 'Not Set':
    return 0, ''
  value = str(value)
  match = re.match(r'^(-?[0-9.]+)([a-zA-Z]*)', value)
  if match:
    num = float(match.group(1))
    unit = match.group(2) if match.group(2) else ''
    return num, unit
  try:
    return float(value), ''
  except ValueError:
    if value.endswith('%'):
      return float(value[:-1]), '%'
    print(f'Warning: Could not parse resource value: {value}', file=sys.stderr)
    return 0, ''


def format_resource_value(num: float, unit: str) -> str:
  """Formats a number and unit back into a resource string."""
  if unit == '' or unit is None:
    return str(int(num)) if num == int(num) else str(num)
  if unit == '%':
    return f'{int(num) if num == int(num) else num}%'
  return f'{int(num) if num == int(num) else num}{unit}'


def _to_millicores(cpu_str: Optional[str]) -> Optional[float]:
  """Converts CPU resource string to millicores, or None if not possible."""
  if cpu_str is None:
    return None
  try:
    num, unit = parse_resource_value(cpu_str)
    if unit == '%':
      return None  # Percentages are not comparable for minimums
    return num if unit == 'm' else num * 1000
  except:
    return None


def _to_bytes(mem_str: Optional[str]) -> Optional[float]:
  """Converts memory resource string to bytes, or None if not possible."""
  if mem_str is None:
    return None
  try:
    num, unit = parse_resource_value(mem_str)
    if unit == '%':
      return None  # Percentages are not comparable for minimums
    return num * MEMORY_UNITS_TO_BYTES.get(unit, 1)
  except:
    return None


def _enforce_min_cpu(cpu_str: str) -> str:
  """Ensures CPU value is not below minimum, returns '100m' if it is."""
  millicores = _to_millicores(cpu_str)
  if millicores is not None and millicores < MIN_CPU_MILLICORES:
    return '100m'
  return cpu_str


def _enforce_min_mem(mem_str: str) -> str:
  """Ensures Memory value is not below minimum, returns '100Mi' if it is."""
  mem_bytes = _to_bytes(mem_str)
  if mem_bytes is not None and mem_bytes < MIN_MEM_BYTES:
    return '100Mi'
  return mem_str


def add_memory_values(val1_str: str, val2_str: str) -> str:
  """Adds two memory resource strings (e.g., '1Gi', '200Mi')."""
  num1, unit1 = parse_resource_value(val1_str)
  num2, unit2 = parse_resource_value(val2_str)

  if unit1 == '%' or unit2 == '%':
    print(
        'Warning: Percentage memory values not supported for addition:'
        f' {val1_str}, {val2_str}',
        file=sys.stderr,
    )
    return val1_str

  if unit1 and unit1 not in MEMORY_UNITS_TO_BYTES:
    print(
        f"Error: Invalid memory unit '{unit1}' in '{val1_str}'", file=sys.stderr
    )
    sys.exit(1)
  if unit2 and unit2 not in MEMORY_UNITS_TO_BYTES:
    print(
        f"Error: Invalid memory unit '{unit2}' in '{val2_str}'", file=sys.stderr
    )
    sys.exit(1)

  base1 = num1 * MEMORY_UNITS_TO_BYTES.get(unit1, 1)
  base2 = num2 * MEMORY_UNITS_TO_BYTES.get(unit2, 1)
  result = base1 + base2

  return format_resource_value(result / MEMORY_UNITS_TO_BYTES['Mi'], 'Mi')


def add_cpu_values(val1_str: str, val2_str: str) -> str:
  """Adds two CPU resource strings (e.g., '500m', '1')."""
  num1, unit1 = parse_resource_value(val1_str)
  num2, unit2 = parse_resource_value(val2_str)

  if unit1 == '%' or unit2 == '%':
    print(
        'Warning: Percentage CPU values not supported for addition:'
        f' {val1_str}, {val2_str}',
        file=sys.stderr,
    )
    return val1_str

  if unit1 and unit1 != 'm':
    print(f"Error: Invalid CPU unit '{unit1}' in '{val1_str}'", file=sys.stderr)
    sys.exit(1)
  if unit2 and unit2 != 'm':
    print(f"Error: Invalid CPU unit '{unit2}' in '{val2_str}'", file=sys.stderr)
    sys.exit(1)

  # Convert to millicores
  base1 = num1 if unit1 == 'm' else num1 * 1000
  base2 = num2 if unit2 == 'm' else num2 * 1000
  result_milli = base1 + base2

  return format_resource_value(result_milli, 'm')


def _get_service_data(
    data: Dict[str, Any], service_name: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
  """Finds service data and key in YAML data."""
  for key, value in data.items():
    if isinstance(value, dict) and value.get('name') == service_name:
      return value, key
    elif key == service_name:
      return value, key
  return None, None


def update_resources(
    file_path: str,
    service_name: str,
    new_limit_cpu: Optional[str],
    new_limit_mem: Optional[str],
    new_req_cpu: Optional[str],
    new_req_mem: Optional[str],
    increase_limit_cpu: Optional[str] = None,
    increase_limit_mem: Optional[str] = None,
) -> bool:
  """Updates resource limits and requests for a specific service in a values.yaml file.

  Args:
      file_path (str): The path to the YAML file to update.
      service_name (str): The name of the service to update.
      new_limit_cpu (str): New CPU limit value. Can be None if not updating.
      new_limit_mem (str): New Memory limit value. Can be None if not updating.
      new_req_cpu (str): New CPU request value. Can be None if not updating.
      new_req_mem (str): New Memory request value. Can be None if not updating.
      increase_limit_cpu (str): Amount to increase CPU limit by.
      increase_limit_mem (str): Amount to increase Memory limit by.

  Returns:
      bool: True if the file was updated, False otherwise.
  """
  print(f'\n--- Processing Update: {file_path} for service: {service_name} ---')
  updated = False
  try:
    with open(file_path, 'r') as f:
      data = yaml.load(f)

    service_data, found_key = _get_service_data(data, service_name)

    if not service_data:
      print(
          f"  Error: Service with name or key '{service_name}' not found in"
          f' {file_path}'
      )
      return False

    if not isinstance(service_data, dict):
      print(
          f"  Error: Expected a dictionary for service '{service_name}', but"
          f' found {type(service_data)}'
      )
      return False

    # Ensure the 'resources', 'limits', and 'requests' keys exist
    if 'resources' not in service_data:
      service_data['resources'] = (
          CommentedMap()
      )  # Use CommentedMap to preserve order/comments
    if 'limits' not in service_data['resources']:
      service_data['resources']['limits'] = CommentedMap()
    if 'requests' not in service_data['resources']:
      service_data['resources']['requests'] = CommentedMap()

    current_limits = service_data['resources'].get('limits', {})
    current_limit_cpu = current_limits.get('cpu')
    current_limit_mem = current_limits.get('memory')

    if increase_limit_cpu is not None:
      new_limit_cpu_val = add_cpu_values(current_limit_cpu, increase_limit_cpu)
      new_limit_cpu_val = _enforce_min_cpu(new_limit_cpu_val)
      print(
          f'  Increased {service_name} limits.cpu from {current_limit_cpu} by'
          f' {increase_limit_cpu} to: {new_limit_cpu_val}'
      )
      service_data['resources']['limits']['cpu'] = new_limit_cpu_val
      updated = True
    elif new_limit_cpu is not None:
      new_limit_cpu_val = _enforce_min_cpu(new_limit_cpu)
      service_data['resources']['limits']['cpu'] = new_limit_cpu_val
      print(f'  Updated {service_name} limits.cpu to: {new_limit_cpu_val}')
      updated = True

    if increase_limit_mem is not None:
      new_limit_mem_val = add_memory_values(
          current_limit_mem, increase_limit_mem
      )
      new_limit_mem_val = _enforce_min_mem(new_limit_mem_val)
      print(
          f'  Increased {service_name} limits.memory from'
          f' {current_limit_mem} by {increase_limit_mem} to:'
          f' {new_limit_mem_val}'
      )
      service_data['resources']['limits']['memory'] = new_limit_mem_val
      updated = True
    elif new_limit_mem is not None:
      new_limit_mem_val = _enforce_min_mem(new_limit_mem)
      service_data['resources']['limits']['memory'] = new_limit_mem_val
      print(f'  Updated {service_name} limits.memory to: {new_limit_mem_val}')
      updated = True

    if new_req_cpu is not None:
      new_req_cpu_val = _enforce_min_cpu(new_req_cpu)
      service_data['resources']['requests']['cpu'] = new_req_cpu_val
      print(f'  Updated {service_name} requests.cpu to: {new_req_cpu_val}')
      updated = True
    if new_req_mem is not None:
      new_req_mem_val = _enforce_min_mem(new_req_mem)
      service_data['resources']['requests']['memory'] = new_req_mem_val
      print(f'  Updated {service_name} requests.memory to: {new_req_mem_val}')
      updated = True

    if updated:
      data[found_key] = service_data
      try:
        with open(file_path, 'w') as f:
          yaml.dump(data, f)
        print(f'  Successfully saved changes to {file_path}')
      except IOError as e:
        print(f'  Error: Could not write changes to file: {e}', file=sys.stderr)
        return False
    else:
      print(f'  No update values provided for {service_name}.')

    return True

  except (ScannerError, ParserError) as e:
    print(f'  Error: Could not parse YAML file: {e}', file=sys.stderr)
  except FileNotFoundError:
    print(f'  Error: File not found.', file=sys.stderr)
  except KeyError as e:
    print(
        f'  Error: Structure missing in YAML file: Key {e} not found.',
        file=sys.stderr,
    )
  except Exception as e:
    print(f'  An unexpected error occurred during update: {e}', file=sys.stderr)
  return False


def _process_update_data_list(data: List[Dict[str, Any]]) -> Dict[str, Any]:
  """Processes a list of timestamped entries to find the latest limits for each service.

  This is a helper function to be used by main().

  Args:
      data (list): A list of dictionaries, where each dictionary contains
        timestamped pod resource data.

  Returns:
      dict: A dictionary where keys are camelCase service names and values
            contain the extracted resource limits.
  """
  latest_entries: Dict[str, Any] = {}
  for entry in data:
    timestamp = entry.get('timestamp')
    pod_name = entry.get('pod_name')
    if not timestamp or not pod_name:
      continue

    # Extract service name from pod_name
    match = re.match(r'([a-zA-Z-]+)-[a-f0-9-]+-[a-zA-Z0-9]+', pod_name)
    if not match:
      match = re.match(r'([a-zA-Z-]+)-[a-f0-9]+', pod_name)
    if not match:
      continue
    service_name: str = match.group(1)

    # Convert service name to Helm chart key
    service_name_camel: str = ''
    if service_name in _POD_SERVICE_TO_HELM_KEY:
      service_name_camel = _POD_SERVICE_TO_HELM_KEY[service_name]
    else:
      parts = service_name.split('-')
      service_name_camel = parts[0] + ''.join(p.capitalize() for p in parts[1:])

    if not service_name_camel:
      continue

    if (
        service_name_camel not in latest_entries
        or timestamp > latest_entries[service_name_camel]['timestamp']
    ):
      latest_entries[service_name_camel] = entry

  update_data: Dict[str, Any] = {}
  for service_name_camel, entry in latest_entries.items():
    containers = entry.get('containers', [])
    if containers:
      container = containers[0]
      cpu_limit = container.get('cpu_limit')
      memory_limit = container.get('memory_limit')

      if cpu_limit is not None and memory_limit is not None:
        update_data[service_name_camel] = {
            'resources': {
                'limits': {'cpu': str(cpu_limit), 'memory': str(memory_limit)}
            }
        }
        print(
            f'  {service_name_camel}: CPU Limit: {cpu_limit}, Memory Limit:'
            f' {memory_limit}'
        )

  return update_data


def main() -> None:
  """Main function to parse arguments and perform actions."""
  parser = argparse.ArgumentParser(
      description=(
          'Read or update resource limits/requests in Helm values.yaml files.'
      ),
      formatter_class=argparse.RawDescriptionHelpFormatter,
  )

  parser.add_argument(
      'path',
      help=(
          'Base path for reading or updating resources. For "read", it can be a'
          ' directory to search recursively. For "update", it can be a single'
          ' YAML file or a directory to search recursively for values.yaml'
          ' files.'
      ),
  )
  parser.add_argument(
      'action',
      choices=['read', 'update', 'reallocate'],
      help="Action to perform: 'read', 'update', or 'reallocate'.",
  )

  parser.add_argument(
      '--service',
      help=(
          'Name of the service to update (e.g., adService). If omitted, flags'
          ' apply to ALL services.'
      ),
  )
  parser.add_argument(
      '--from-service',
      help='For reallocate action: service to take resources from.',
  )
  parser.add_argument(
      '--to-service',
      help='For reallocate action: service to give resources to.',
  )
  parser.add_argument(
      '--amount-cpu', help='For reallocate action: amount of CPU to reallocate.'
  )
  parser.add_argument(
      '--amount-mem',
      help='For reallocate action: amount of Memory to reallocate.',
  )

  parser.add_argument(
      '--limit-cpu',
      help=(
          "New CPU limit (e.g., '500m', '1'). Only applies if action is"
          " 'update'."
      ),
  )
  parser.add_argument(
      '--limit-mem',
      help=(
          "New Memory limit (e.g., '512Mi', '1Gi'). Only applies if action is"
          " 'update'."
      ),
  )
  parser.add_argument(
      '--req-cpu',
      help=(
          "New CPU request (e.g., '100m', '0.5'). Only applies if action is"
          " 'update'."
      ),
  )
  parser.add_argument(
      '--req-mem',
      help=(
          "New Memory request (e.g., '128Mi', '256Mi'). Only applies if action"
          " is 'update'."
      ),
  )
  parser.add_argument(
      '--increase-limit-cpu',
      help=(
          "Amount to increase CPU limit by (e.g., '200m')."
          " Only applies if action is 'update'."
      ),
  )
  parser.add_argument(
      '--increase-limit-mem',
      help=(
          "Amount to increase Memory limit by (e.g., '200Mi')."
          " Only applies if action is 'update'."
      ),
  )
  parser.add_argument(
      '-y',
      '--yaml',
      action='store_true',
      help=(
          'Write all resource data to a single YAML file (only for read'
          ' action). The output format is suitable for --input-yaml.'
      ),
  )
  parser.add_argument(
      '-i',
      '--input-yaml',
      help=(
          'YAML file containing service resource updates (only for update'
          ' action). This should be a dictionary where keys are service names'
          ' and values contain resource blocks (e.g., as generated by "read'
          ' -y").'
      ),
  )
  parser.add_argument(
      '--update-file',
      help=(
          'A YAML file with multiple timestamped entries. The script will parse'
          ' this file, find the latest timestamp for each pod, and use that to'
          ' update the corresponding helm charts.'
      ),
  )

  args = parser.parse_args()

  if args.action == 'update':
    has_flags = any([
        args.limit_cpu,
        args.limit_mem,
        args.req_cpu,
        args.req_mem,
        args.increase_limit_cpu,
        args.increase_limit_mem,
    ])
    if (
        (args.input_yaml and has_flags)
        or (args.update_file and has_flags)
        or (args.input_yaml and args.update_file)
    ):
      print(
          'Error: Cannot use --input-yaml, --update-file, and individual'
          ' resource flags at the same time.',
          file=sys.stderr,
      )
      parser.print_help()
      sys.exit(1)
    if not args.input_yaml and not has_flags and not args.update_file:
      print(
          'Error: Update action specified, but no resource values provided.'
          ' Use --limit-cpu/--limit-mem, --input-yaml, or --update-file.',
          file=sys.stderr,
      )
      parser.print_help()
      sys.exit(1)

  if args.action == 'read':
    values_files = find_values_files(args.path)
    if not values_files:
      print(f"No YAML files found matching the criteria in '{args.path}'.")
      sys.exit(0)

    all_resources: List[Dict[str, Any]] = []
    for file_path in values_files:
      resource_data = read_resources(file_path)
      if resource_data:
        all_resources.extend(resource_data)

    if args.yaml:
      output_for_yaml: DefaultDict[str, Dict[str, Any]] = defaultdict(dict)
      for res in all_resources:
        file_path = res['file']
        service_name = res['service']
        output_for_yaml[file_path][service_name] = {
            'resources': {
                'limits': res['limits'],
                'requests': res['requests'],
            }
        }
      with open('resource_summary.yaml', 'w') as outfile:
        yaml.dump(dict(output_for_yaml), outfile)
      print('\n--- Resource Summary written to resource_summary.yaml ---')
    print(
        '\n--- Read Summary: Found resources in'
        f' {len(all_resources)} services ---'
    )

  elif args.action == 'update':
    update_files: List[str] = []
    if os.path.isfile(args.path):
      update_files.append(args.path)
    elif os.path.isdir(args.path):
      update_files = find_values_files(args.path)
    else:
      print(
          f'Error: Update path not found or invalid: {args.path}',
          file=sys.stderr,
      )
      sys.exit(1)

    if not update_files:
      print(f"No YAML files found to update in '{args.path}'.")
      sys.exit(0)

    print(f'--- Found {len(update_files)} files to update ---')

    update_data: Dict[str, Any] = {}
    input_file = args.update_file or args.input_yaml
    if input_file:
      try:
        with open(input_file, 'r') as f:
          data = yaml.load(f)

        if isinstance(data, list):
          print(f'Processing timestamped list from {input_file}...')
          update_data = _process_update_data_list(data)
        elif isinstance(data, dict):
          print(f'Processing dictionary from {input_file}...')
          update_data = data
        else:
          print(
              f'Error: Input YAML file {input_file} has an unexpected format.',
              file=sys.stderr,
          )
          sys.exit(1)
      except (ScannerError, ParserError, FileNotFoundError) as e:
        print(
            f'Error: Could not read input YAML file {input_file}: {e}',
            file=sys.stderr,
        )
        sys.exit(1)

    if not update_data and input_file:
      print(f'No update data loaded from {input_file}')
      sys.exit(1)

    for file_path in update_files:
      print(f'\n--- Processing file: {file_path} ---')

      if args.input_yaml:
        # Update data is structured by file path
        if file_path in update_data:
          file_specific_updates = update_data[file_path]
          updated_any_service = False
          for service_name, service_values in file_specific_updates.items():
            if (
                isinstance(service_values, dict)
                and 'resources' in service_values
            ):
              limits = service_values['resources'].get('limits', {})
              requests = service_values['resources'].get('requests', {})
              if update_resources(
                  file_path,
                  service_name,
                  limits.get('cpu'),
                  limits.get('memory'),
                  requests.get('cpu'),
                  requests.get('memory'),
                  increase_limit_cpu=args.increase_limit_cpu,
                  increase_limit_mem=args.increase_limit_mem,
              ):
                updated_any_service = True
          if updated_any_service:
            print(f'Successfully applied updates to {file_path}')
          else:
            print(f'No resource updates applied to {file_path} from input YAML')
        else:
          print(f'No updates found for {file_path} in {args.input_yaml}')
      elif args.update_file:
        # This case implies update_data is from _process_update_data_list
        # Which is a flat dict of service_name -> resources
        updated_any_service = False
        for service_name, service_values in update_data.items():
          if isinstance(service_values, dict) and 'resources' in service_values:
            limits = service_values['resources'].get('limits', {})
            requests = service_values['resources'].get('requests', {})
            # This will try to update the service if it exists in the current file_path
            if update_resources(
                file_path,
                service_name,
                limits.get('cpu'),
                limits.get('memory'),
                requests.get('cpu'),
                requests.get('memory'),
            ):
              updated_any_service = True
        if updated_any_service:
          print(f'Successfully applied updates to {file_path}')
        else:
          print(f'No resource updates applied to {file_path}')

      else:  # Update from command line arguments
        try:
          with open(file_path, 'r') as f:
            data = yaml.load(f)
        except (ScannerError, ParserError, FileNotFoundError) as e:
          print(
              f'Error: Could not read target YAML file {file_path}: {e}',
              file=sys.stderr,
          )
          continue

        if args.service:
          service_found = False
          for key, value in data.items():
            if isinstance(value, dict) and value.get('name') == args.service:
              service_found = True
              if update_resources(
                  file_path,
                  args.service,
                  args.limit_cpu,
                  args.limit_mem,
                  args.req_cpu,
                  args.req_mem,
                  increase_limit_cpu=args.increase_limit_cpu,
                  increase_limit_mem=args.increase_limit_mem,
              ):
                print(f'Successfully updated {args.service} in {file_path}')
              else:
                print(f'Failed to update {args.service} in {file_path}')
              break
            elif key == args.service:  # Fallback to key match
              service_found = True
              if update_resources(
                  file_path,
                  args.service,
                  args.limit_cpu,
                  args.limit_mem,
                  args.req_cpu,
                  args.req_mem,
                  increase_limit_cpu=args.increase_limit_cpu,
                  increase_limit_mem=args.increase_limit_mem,
              ):
                print(f'Successfully updated {args.service} in {file_path}')
              else:
                print(f'Failed to update {args.service} in {file_path}')
              break
          if not service_found:
            print(f'Service {args.service} not found in {file_path}')
        else:
          print(
              '--service not specified, attempting to update all services in'
              f' {file_path}'
          )
          updated_any_service = False
          for service_name in data.keys():
            if isinstance(data[service_name], dict):
              print(f'Updating resources for service: {service_name}')
              if update_resources(
                  file_path,
                  service_name,
                  args.limit_cpu,
                  args.limit_mem,
                  args.req_cpu,
                  args.req_mem,
                  increase_limit_cpu=args.increase_limit_cpu,
                  increase_limit_mem=args.increase_limit_mem,
              ):
                updated_any_service = True

          if not updated_any_service:
            print(f'No services were updated in {file_path}')
          else:
            print(
                f'Successfully updated all applicable services in {file_path}'
            )
  elif args.action == 'reallocate':
    if not args.from_service or not args.to_service:
      print(
          'Error: --from-service and --to-service are required for reallocate'
          ' action.',
          file=sys.stderr,
      )
      sys.exit(1)
    if not args.amount_cpu and not args.amount_mem:
      print(
          'Error: --amount-cpu or --amount-mem is required for reallocate'
          ' action.',
          file=sys.stderr,
      )
      sys.exit(1)

    all_files: List[str] = []
    if os.path.isfile(args.path):
      all_files.append(args.path)
    elif os.path.isdir(args.path):
      all_files = find_values_files(args.path)
    else:
      print(
          f'Error: Reallocate path not found or invalid: {args.path}',
          file=sys.stderr,
      )
      sys.exit(1)

    from_service_file, to_service_file = None, None
    from_service_found_data, to_service_found_data = None, None

    for file_path in all_files:
      try:
        with open(file_path, 'r') as f:
          data = yaml.load(f)

        if not from_service_file:
          from_service_data, _ = _get_service_data(data, args.from_service)
          if from_service_data:
            from_service_file = file_path
            from_service_found_data = from_service_data

        if not to_service_file:
          to_service_data, _ = _get_service_data(data, args.to_service)
          if to_service_data:
            to_service_file = file_path
            to_service_found_data = to_service_data
      except (ScannerError, ParserError, FileNotFoundError) as e:
        print(f'  Error: Could not read YAML file: {e}', file=sys.stderr)
        continue

    if not from_service_file:
      print(
          'Error: service'
          f" '{args.from_service}' not found in any file in {args.path}"
      )
      sys.exit(1)
    if not to_service_file:
      print(
          'Error: service'
          f" '{args.to_service}' not found in any file in {args.path}"
      )
      sys.exit(1)

    # Check if reallocation is possible
    can_reallocate_cpu = False
    if args.amount_cpu:
      amount_m, _ = parse_resource_value(args.amount_cpu)
      from_limits = from_service_found_data.get('resources', {}).get(
          'limits', {}
      )
      from_cpu = from_limits.get('cpu')
      from_cpu_m = _to_millicores(from_cpu)
      if from_cpu_m is not None and from_cpu_m - amount_m >= MIN_CPU_MILLICORES:
        can_reallocate_cpu = True
      else:
        print(
            f'Cannot reallocate CPU from {args.from_service}: current limit'
            f' {from_cpu}, reducing by {args.amount_cpu} would go below minimum'
            f' {MIN_CPU_MILLICORES}m.'
        )

    can_reallocate_mem = False
    if args.amount_mem:
      amount_bytes = _to_bytes(args.amount_mem)
      from_limits = from_service_found_data.get('resources', {}).get(
          'limits', {}
      )
      from_mem = from_limits.get('memory')
      from_mem_bytes = _to_bytes(from_mem)
      if (
          from_mem_bytes is not None
          and from_mem_bytes - amount_bytes >= MIN_MEM_BYTES
      ):
        can_reallocate_mem = True
      else:
        print(
            f'Cannot reallocate Memory from {args.from_service}: current limit'
            f' {from_mem}, reducing by {args.amount_mem} would go below minimum'
            f' {MIN_MEM_BYTES} bytes.'
        )

    # Perform reallocation
    reallocated_anything = False
    if args.amount_cpu and can_reallocate_cpu:
      print(
          f'Reallocating CPU {args.amount_cpu} from {args.from_service} in'
          f' {from_service_file} to {args.to_service} in {to_service_file}'
      )
      update_resources(
          from_service_file,
          args.from_service,
          None,
          None,
          None,
          None,
          increase_limit_cpu=f'-{args.amount_cpu}',
      )
      update_resources(
          to_service_file,
          args.to_service,
          None,
          None,
          None,
          None,
          increase_limit_cpu=args.amount_cpu,
      )
      reallocated_anything = True

    if args.amount_mem and can_reallocate_mem:
      print(
          f'Reallocating Memory {args.amount_mem} from {args.from_service} in'
          f' {from_service_file} to {args.to_service} in {to_service_file}'
      )
      update_resources(
          from_service_file,
          args.from_service,
          None,
          None,
          None,
          None,
          increase_limit_mem=f'-{args.amount_mem}',
      )
      update_resources(
          to_service_file,
          args.to_service,
          None,
          None,
          None,
          None,
          increase_limit_mem=args.amount_mem,
      )
      reallocated_anything = True

    if not reallocated_anything:
      print('No resources were reallocated.')

  print('\n--- Script Finished ---')


if __name__ == '__main__':
  main()
