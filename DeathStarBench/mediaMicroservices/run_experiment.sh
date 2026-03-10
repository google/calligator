#!/bin/bash

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

# --- Ensure my-sleep-pod is running and ready ---
echo "---"
echo "Ensuring my-sleep-pod is running and ready..."
# Assuming my-sleep-pod is in the default namespace
MY_SLEEP_POD_NAME="my-sleep-pod"
MY_SLEEP_POD_NAMESPACE="default"

# Check if the pod exists
if ! kubectl get pod "$MY_SLEEP_POD_NAME" -n "$MY_SLEEP_POD_NAMESPACE" &>/dev/null; then
  echo "Error: my-sleep-pod '$MY_SLEEP_POD_NAME' not found in namespace '$MY_SLEEP_POD_NAMESPACE'. Exiting."
  exit 1
else
  echo "my-sleep-pod '$MY_SLEEP_POD_NAME' exists."
fi

# Wait for my-sleep-pod to be ready
echo "Waiting for my-sleep-pod to be ready..."
if ! kubectl wait --for=condition=Ready pod "$MY_SLEEP_POD_NAME" -n "$MY_SLEEP_POD_NAMESPACE" --timeout=5m; then
  echo "Error: my-sleep-pod '$MY_SLEEP_POD_NAME' did not become ready in time. Exiting."
  exit 1
fi
echo "my-sleep-pod '$MY_SLEEP_POD_NAME' is ready."

# --- Configuration Variables ---
HELM_VALUES_PATH="helm-chart/values.yaml"
LOAD_GENERATOR_YAML_PATH="loadgenerator/loadgenerator.yaml"
HELM_CHART_NAME="media"
# It's better to fetch all traces and then filter/count locally,
# as Jaeger's 'limit' might not guarantee the exact number you want if
# there are more traces available.
JAEGER_URL="http://jaeger:16686/api/traces?service=nginx-web-server&limit=5000" # Increased limit
TARGET_TRACE_COUNT=2000
OUTPUT_FILE="jaeger_traces.json" # This can be a base name now, the full name will be constructed later
NAMESPACE="default" # Defined early for use in my-sleep-pod deletion
LOAD_GENERATION_INTERVAL_SECONDS=10 # How often to check for traces (adjust as needed)

# Variable to store the PID of the background kube_metrics.py process
KUBE_METRICS_PID=""

# --- Functions ---

# Function to clean up resources in case of script interruption
cleanup() {
  echo "" # Newline for cleaner output after potential interruption
  
  echo "---"
  echo "Cleaning up Helm chart: $HELM_CHART_NAME in namespace $NAMESPACE..."
  helm uninstall "$HELM_CHART_NAME" --namespace "$NAMESPACE" &>/dev/null
  kubectl delete -f "$LOAD_GENERATOR_YAML_PATH" -n "$NAMESPACE" 

  # Terminate the background kube_metrics.py process if it's running
  if [ -n "$KUBE_METRICS_PID" ]; then
    echo "Terminating kube_metrics.py process (PID: $KUBE_METRICS_PID)..."
    kill "$KUBE_METRICS_PID" &>/dev/null
  fi
  echo "Cleanup complete."
  exit 1 # Exit with an error code
}

# Trap Ctrl+C (SIGINT) and call the cleanup function
trap cleanup SIGINT

# --- Script Start ---
echo "---"
echo "Starting trace collection experiment..."

# Parse CLI arguments
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    -u|--users)
      USERS="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [-u|--users <number_of_users>]"
      exit 1
      ;;
  esac
done

if [ -z "$USERS" ]; then
  USERS=100
  echo "No users specified, using default value: $USERS"
else
  echo "Using users: $USERS"
fi

# --- Construct OUTPUT_FILE_WITH_PARAMS AFTER variables are set ---
OUTPUT_FILE_WITH_PARAMS="jaeger_traces_users_${USERS}"
OUTPUT_FILE_WITH_PARAMS="${OUTPUT_FILE_WITH_PARAMS}.json"
LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS="loadgenerator_users_${USERS}"
LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS="${LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS}.txt"
# -----------------------------------------------------------------

# Update values.yaml with the new number of users and latencies
echo "Updating $HELM_VALUES_PATH..."

## YAML Update Functions using yq ##
#
# Prerequisite: Ensure yq is installed.
# For macOS: brew install yq
# For Linux: sudo snap install yq
# Or download binary from https://github.com/mikefarah/yq/releases
#

# Function to update a simple key-value pair using yq
update_yaml_value() {
  local file="$1"
  local key_path="$2" # e.g., ".loadGenerator.users" or ".checkoutService.extraLatency"
  local value="$3"
  
  # Corrected yq command: The filter and file path are separate arguments.
  # No need for 'eval' when passing arguments directly.
  if ! yq eval --inplace "${key_path} = \"${value}\"" "$file"; then
      echo "Error: Failed to update key '${key_path}' in '$file' using yq."
      exit 1
  fi
}

# --- Apply the updates using the yq functions ---

# Update users (top-level key)
# update_yaml_value "$HELM_VALUES_PATH" ".loadGenerator.users" "$USERS"

if [ $? -ne 0 ]; then
  echo "Error: Failed to update $HELM_VALUES_PATH. Exiting."
  exit 1
fi
echo "$HELM_VALUES_PATH updated successfully."

# Uninstall Helm chart
helm uninstall "$HELM_CHART_NAME" --namespace "$NAMESPACE" &>/dev/null
kubectl delete -f "$LOAD_GENERATOR_YAML_PATH" -n "$NAMESPACE"
echo "Helm chart uninstalled."

# Install Helm chart
echo "Installing helm chart '$HELM_CHART_NAME' in namespace '$NAMESPACE'..."
if ! helm install "$HELM_CHART_NAME" helm-chart/mediamicroservices; then
  echo "Error: Helm chart installation failed. Exiting."
  exit 1
fi
echo "Helm chart installed successfully."

# Apply sleep.yaml
kubectl apply -f sleep.yaml -n "$NAMESPACE"

echo "Target trace count: $TARGET_TRACE_COUNT"
echo "---"
# Wait for pods to be ready
# echo "Waiting for pods in namespace '$NAMESPACE' to be ready (timeout: 5m)..."
# if ! kubectl wait --for=condition=Ready pods --all -n "$NAMESPACE" --timeout=5m; then
#   echo "Error: Pods did not become ready in time. Exiting."
#   helm uninstall "$HELM_CHART_NAME" --namespace "$NAMESPACE" &>/dev/null
#   exit 1
# fi
# echo "All pods are ready."
sleep 120

# --- Run load generator ---
echo "Starting load generator..."
kubectl apply -f "$LOAD_GENERATOR_YAML_PATH" -n "$NAMESPACE"
echo "Load generator started successfully."

sleep 100

# --- Find the pod name of jaeger and restart it ---
echo "Finding Jaeger pod name..."
POD_NAME=$(kubectl get pod -n "$NAMESPACE" -l app=jaeger -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD_NAME" ]; then
  echo "Error: Could not find Jaeger pod. Exiting."
  exit 1
fi

echo "Deleting Jaeger pod: $POD_NAME..."
kubectl delete pod "$POD_NAME" -n "$NAMESPACE"
echo "Jaeger pod deleted."

# Wait for the new Jaeger pod to be ready
echo "Waiting for new Jaeger pod to be ready..."
if ! kubectl wait --for=condition=Ready pod -l app=jaeger -n "$NAMESPACE" --timeout=2m; then
  echo "Error: New Jaeger pod did not become ready in time. Exiting."
  exit 1
fi
echo "New Jaeger pod is ready."

# --- Run kube_metrics.py in the background after all pods are ready ---
echo "Starting kube_metrics.py in the background for resource utilization tracing..."
python3 ../../kube_metrics.py -d 200 -i 30 -a resource_utilization.txt &
# Capture the PID of the background process so we can wait for it later or kill it on cleanup
KUBE_METRICS_PID=$!
# --------------------------------------------------------------------

TRACE_COUNT=0
ITERATION=0
while [ "$TRACE_COUNT" -lt "$TARGET_TRACE_COUNT" ]; do
  ITERATION=$((ITERATION + 1))
  echo "---"
  echo "Iteration $ITERATION: Collecting traces..."

  # Generate load (assuming an external load generator is running)
  echo "Simulating load generation... (Ensure your load generator is active)"
  # If you need to trigger load generation from this script, add the command here.
  # For example: your_load_generator_command

  # Fetch traces from Jaeger using kubectl exec through my-sleep-pod
  echo "Fetching traces from Jaeger at $JAEGER_URL via my-sleep-pod..."
  if ! kubectl exec "$MY_SLEEP_POD_NAME" -n "$MY_SLEEP_POD_NAMESPACE" -- curl -s "$JAEGER_URL" > "$OUTPUT_FILE_WITH_PARAMS"; then
    echo "Error: Failed to fetch traces from Jaeger via my-sleep-pod. Retrying..."
    sleep "$LOAD_GENERATION_INTERVAL_SECONDS"
    continue # Skip to the next iteration
  fi

  # Parse trace count using jq
  # We use '.data | length' to get the number of traces in the 'data' array.
  # The '.total' field in Jaeger's API might not always reflect the actual
  # number of traces returned in the 'data' array, especially with limits.
  TEMP_TRACE_COUNT=$(jq '.data | length' "$OUTPUT_FILE_WITH_PARAMS")

  if [ -z "$TEMP_TRACE_COUNT" ] || [ "$TEMP_TRACE_COUNT" -lt 0 ]; then
    echo "Warning: Could not parse trace count from '$OUTPUT_FILE'. Skipping this iteration."
    TRACE_COUNT=0 # Reset or keep previous, depending on desired behavior
  else
    TRACE_COUNT="$TEMP_TRACE_COUNT"
  fi

  echo "Collected $TRACE_COUNT traces in this batch."

  # Check if we have enough traces
  if [ "$TRACE_COUNT" -lt "$TARGET_TRACE_COUNT" ]; then
    echo "Current total traces: $TRACE_COUNT. Target: $TARGET_TRACE_COUNT. Waiting for more traces..."
    sleep "$LOAD_GENERATION_INTERVAL_SECONDS"
  fi
done

echo "---"
echo "Reached $TARGET_TRACE_COUNT traces. Experiment finished."

# --- Wait for kube_metrics.py to finish before uninstalling Helm chart ---
echo "Waiting for kube_metrics.py to finish..."
wait "$KUBE_METRICS_PID"
echo "kube_metrics.py has finished."
# -----------------------------------------------------------------------

sleep 60 

kubectl logs --tail=300 -n "$NAMESPACE" -l app=loadgenerator > "$LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS"

# Uninstall Helm chart
helm uninstall "$HELM_CHART_NAME" --namespace "$NAMESPACE"
echo "Helm chart uninstalled."
echo "---"
echo "Script completed successfully."

