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

import argparse
import os
import re
import subprocess
import time


def normalize_value(value):
  """Normalizes CPU and memory values to a common base.

  CPU values are converted to millicores. Memory values are converted to bytes.
  """
  if value is None:
    return None

  value = value.strip()
  if not value:
    return None

  # Handle CPU units
  if value.endswith("m"):  # millicores
    return float(value[:-1])
  elif value.endswith("n"):  # nanocores
    return float(value[:-1]) / 1_000_000  # Convert to millicores
  elif value.replace(
      ".", "", 1
  ).isdigit():  # If it's just a number, assume cores (for CPU)
    try:
      return float(value) * 1000  # Convert cores to millicores
    except ValueError:
      pass  # Fall through to memory unit checks if not a valid float

  # Handle Memory units
  # Binary units (powers of 1024)
  if value.endswith("Ki"):  # Kibibytes
    return float(value[:-2]) * 1024
  elif value.endswith("Mi"):  # Mebibytes
    return float(value[:-2]) * (1024**2)
  elif value.endswith("Gi"):  # Gibibytes
    return float(value[:-2]) * (1024**3)
  elif value.endswith("Ti"):  # Tebibytes
    return float(value[:-2]) * (1024**4)
  elif value.endswith("Pi"):  # Pebibytes
    return float(value[:-2]) * (1024**5)
  elif value.endswith("Ei"):  # Exbibytes
    return float(value[:-2]) * (1024**6)
  # Decimal units (powers of 1000)
  elif value.endswith("K"):  # Kilobytes
    return float(value[:-1]) * 1000
  elif value.endswith("M"):  # Megabytes
    return float(value[:-1]) * (1000**2)
  elif value.endswith("G"):  # Gigabytes
    return float(value[:-1]) * (1000**3)
  elif value.endswith("T"):  # Terabytes
    return float(value[:-1]) * (1000**4)
  elif value.endswith("P"):  # Petabytes
    return float(value[:-1]) * (1000**5)
  elif value.endswith("E"):  # Exabytes
    return float(value[:-1]) * (1000**6)
  else:
    try:
      # If no unit, assume bytes for memory or cores for CPU (if not handled above)
      # This case primarily for raw byte values from limits or top output without explicit units
      return float(value)
    except ValueError:
      print(f"Warning: Could not normalize value '{value}'. Returning None.")
      return None


def get_kubernetes_metrics(namespace="default"):
  """Retrieves Kubernetes pod metrics (CPU and memory) and returns them as a dictionary."""
  try:
    command = ["kubectl", "top", "pods", "-n", namespace, "--no-headers"]
    process = subprocess.run(
        command, capture_output=True, text=True, check=True
    )
    output = process.stdout.strip()

    metrics = {}
    for line in output.splitlines():
      parts = line.split()
      if len(parts) >= 3:
        pod_name = parts[0]
        cpu = parts[1]
        memory = parts[2]
        metrics[pod_name] = {"cpu": cpu, "memory": memory}
    return metrics

  except subprocess.CalledProcessError as e:
    print(f"Error executing kubectl command: {e}")
    print(f"Stderr: {e.stderr}")
    return None
  except FileNotFoundError:
    print("kubectl not found. Ensure kubectl is installed and in your PATH.")
    return None
  except Exception as e:
    print(f"An unexpected error occurred: {e}")
    return None


def get_app_name_and_limits(pod_name, namespace="default"):
  """Retrieves the app name (from labels) and CPU/memory limits for a given pod,

  prioritizing non-Istio containers.
  """
  try:
    command = ["kubectl", "describe", "pod", pod_name, "-n", namespace]
    process = subprocess.run(
        command, capture_output=True, text=True, check=True
    )
    output = process.stdout

    app_name_match = re.search(r"Labels:\s.*?app=(\S+)", output, re.DOTALL)
    app_name = app_name_match.group(1).strip() if app_name_match else pod_name

    cpu_limit = None
    memory_limit = None

    # Regex to find container blocks within the 'Containers:' section
    # This regex looks for a line starting with "  <container_name>:" followed by
    # any lines until the next container block or end of the section.
    # It captures the container name and its entire block of details.
    # The lookahead `(?=\n\s{2}\S+:|\n[A-Za-z]|\Z)` ensures it stops at the next container,
    # a new top-level section (like "Conditions:"), or the end of the string.
    container_blocks = re.findall(
        r"^\s{2}(\S+):\n(.*?)(?=\n\s{2}\S+:|\n[A-Za-z]|\Z)",
        output,
        re.DOTALL | re.MULTILINE,
    )

    for container_name, block_content in container_blocks:
      # Exclude Istio sidecar containers by name
      if container_name in ["istio-proxy", "istio-init"]:
        continue

      # Regex to find the Limits block within the current container block
      # Assumes "Limits:" is indented 4 spaces, and cpu/memory are indented 6 spaces.
      limits_block_match = re.search(
          r"^\s{4}Limits:\n((?:^\s{6}.+\n?)*)", block_content, re.MULTILINE
      )
      if limits_block_match:
        limits_content = limits_block_match.group(1)

        cpu_limit_match = re.search(
            r"^\s{6}cpu:\s*(\S+)", limits_content, re.MULTILINE
        )
        memory_limit_match = re.search(
            r"^\s{6}memory:\s*(\S+)", limits_content, re.MULTILINE
        )

        if cpu_limit_match:
          cpu_limit = cpu_limit_match.group(1).strip()
        if memory_limit_match:
          memory_limit = memory_limit_match.group(1).strip()

        # If we found limits for a non-Istio container, we can stop and use these.
        # This assumes there's one primary non-Istio container whose limits we care about.
        if cpu_limit is not None or memory_limit is not None:
          break  # Found the limits for the main app container, exit loop

    return {"app_name": app_name, "cpu": cpu_limit, "memory": memory_limit}

  except subprocess.CalledProcessError as e:
    print(f"Error describing pod {pod_name}: {e}")
    return {"app_name": pod_name, "cpu": None, "memory": None}
  except Exception as e:
    print(f"An error occurred while getting app name and pod limits: {e}")
    return {"app_name": pod_name, "cpu": None, "memory": None}


def calculate_utilization(usage_str, limit_str):
  """Calculates the percentage utilization of resources, handling different units."""
  usage_value = normalize_value(usage_str)
  limit_value = normalize_value(limit_str)

  if usage_value is None or limit_value is None or limit_value == 0:
    return None

  return (usage_value / limit_value) * 100


def collect_and_save_metrics(
    namespace="default",
    num_samples=None,
    interval=10,
    duration=None,
    filename="kubernetes_metrics.txt",
    average=False,
):
  """Collects Kubernetes metrics, resource limits, and calculates utilization, then saves to a file."""
  if duration is not None and interval is not None and num_samples is None:
    num_samples = int(duration / interval)
    if num_samples <= 0:
      print("Error: Duration must be greater than the interval.")
      return
  elif num_samples is None and duration is None:
    print("Error: Either --num_samples or --duration must be provided.")
    return
  elif num_samples is not None and duration is not None:
    print(
        "Warning: Both --num_samples and --duration provided. Using"
        " --num_samples."
    )

  all_metrics_data = []

  if num_samples is not None:
    try:
      for i in range(num_samples):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        metrics = get_kubernetes_metrics(namespace)
        if metrics:
          pod_metrics = {}
          for pod_name, data in metrics.items():
            app_info = get_app_name_and_limits(pod_name, namespace)
            app_name = app_info["app_name"]
            limits = {"cpu": app_info["cpu"], "memory": app_info["memory"]}

            if limits:
              cpu_utilization = calculate_utilization(
                  data["cpu"], limits["cpu"]
              )
              memory_utilization = calculate_utilization(
                  data["memory"], limits["memory"]
              )
              pod_metrics[app_name] = {
                  "cpu_usage": data["cpu"],
                  "cpu_limit": limits["cpu"],
                  "cpu_utilization": cpu_utilization,
                  "memory_usage": data["memory"],
                  "memory_limit": limits["memory"],
                  "memory_utilization": memory_utilization,
              }
            else:
              pod_metrics[app_name] = {
                  "cpu_usage": data["cpu"],
                  "cpu_limit": None,
                  "cpu_utilization": None,
                  "memory_usage": data["memory"],
                  "memory_limit": None,
                  "memory_utilization": None,
              }
          all_metrics_data.append({"timestamp": timestamp, "apps": pod_metrics})
        else:
          print(f"Failed to retrieve metrics at {timestamp}.")
        if i < num_samples - 1:
          time.sleep(interval)

      with open(filename, "w") as f:
        if average:
          if not all_metrics_data:
            f.write("No metrics collected to average.\n")
            return

          averaged_metrics = {}
          num_reports = len(all_metrics_data)

          for report in all_metrics_data:
            for app_name, data in report["apps"].items():
              if app_name not in averaged_metrics:
                averaged_metrics[app_name] = {
                    "cpu_usage_sum": 0,
                    "cpu_utilization_sum": 0,
                    "cpu_utilization_count": 0,
                    "memory_usage_sum": 0,
                    "memory_utilization_sum": 0,
                    "memory_utilization_count": 0,
                }

              averaged_metrics[app_name]["cpu_usage_sum"] += (
                  normalize_value(data["cpu_usage"]) or 0
              )
              if data["cpu_utilization"] is not None:
                averaged_metrics[app_name]["cpu_utilization_sum"] += data[
                    "cpu_utilization"
                ]
                averaged_metrics[app_name]["cpu_utilization_count"] += 1

              averaged_metrics[app_name]["memory_usage_sum"] += (
                  normalize_value(data["memory_usage"]) or 0
              )
              if data["memory_utilization"] is not None:
                averaged_metrics[app_name]["memory_utilization_sum"] += data[
                    "memory_utilization"
                ]
                averaged_metrics[app_name]["memory_utilization_count"] += 1

          f.write("--- Average Metrics Report ---\n")
          for app_name, avg_data in averaged_metrics.items():
            avg_cpu_usage_m = (
                avg_data["cpu_usage_sum"] / num_reports
            )  # Already in millicores

            # Explicitly initialize before conditional assignment
            avg_cpu_utilization = None
            if avg_data["cpu_utilization_count"] > 0:
              avg_cpu_utilization = (
                  avg_data["cpu_utilization_sum"]
                  / avg_data["cpu_utilization_count"]
              )

            avg_memory_usage_bytes = (
                avg_data["memory_usage_sum"] / num_reports
            )  # In bytes
            avg_memory_usage_mi = avg_memory_usage_bytes / (
                1024**2
            )  # Convert to MiB for display

            # Explicitly initialize before conditional assignment
            avg_memory_utilization = None
            if avg_data["memory_utilization_count"] > 0:
              avg_memory_utilization = (
                  avg_data["memory_utilization_sum"]
                  / avg_data["memory_utilization_count"]
              )

            cpu_str = (
                f"({avg_cpu_utilization:.2f}%)"
                if avg_cpu_utilization is not None
                else "(Utilization unavailable)"
            )
            memory_str = (
                f"({avg_memory_utilization:.2f}%)"
                if avg_memory_utilization is not None
                else "(Utilization unavailable)"
            )

            f.write(
                f"{app_name}:"
                f" CPU={avg_cpu_usage_m:.2f}m {cpu_str},"
                f" Memory={avg_memory_usage_mi:.2f}Mi {memory_str}\n"
            )

        else:
          for report in all_metrics_data:
            f.write(f"Timestamp: {report['timestamp']}\n")
            for app_name, data in report["apps"].items():
              cpu_str = (
                  f"({data['cpu_utilization']:.2f}%)"
                  if data["cpu_utilization"] is not None
                  else "(Utilization unavailable)"
              )
              # Normalize memory usage for consistent display
              memory_usage_normalized_bytes = normalize_value(
                  data["memory_usage"]
              )
              memory_usage_display = (
                  f"{memory_usage_normalized_bytes / (1024**2):.2f}Mi"
                  if memory_usage_normalized_bytes is not None
                  else data["memory_usage"]
              )

              memory_str = (
                  f"({data['memory_utilization']:.2f}%)"
                  if data["memory_utilization"] is not None
                  else "(Utilization unavailable)"
              )
              f.write(
                  f"{app_name}: CPU={data['cpu_usage']} {cpu_str},"
                  f" Memory={memory_usage_display} {memory_str}"
              )
              if data["cpu_limit"] is None or data["memory_limit"] is None:
                f.write(" (Limits unavailable)")
              f.write("\n")
            f.write("\n")

      print(f"Metrics and utilization saved to {filename}")
    except Exception as e:
      print(f"An error occurred during collection/saving: {e}")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description="Collect and save Kubernetes metrics."
  )

  # Add command line arguments
  parser.add_argument(
      "filename", help="The name of the file to save the metrics to."
  )
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument(
      "--num_samples",
      type=int,
      help="The number of metric samples to collect.",
  )
  group.add_argument(
      "--duration",
      "-d",
      type=int,
      help="The total time (in seconds) to collect metrics for.",
  )
  parser.add_argument(
      "--interval",
      "-i",
      type=int,
      default=10,
      help="The interval (in seconds) between metric samples (default: 10).",
  )
  parser.add_argument(
      "--average",
      "-a",
      action="store_true",
      help="Print a single report with the average metrics.",
  )

  args = parser.parse_args()

  collect_and_save_metrics(
      num_samples=args.num_samples,
      interval=args.interval,
      duration=args.duration,
      filename=args.filename,
      average=args.average,
  )
