#!/bin/bash
#
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

kubectl apply -f sleep.yaml

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


# --- Delete existing jaeger pods ---
echo "---"
echo "Deleting existing jaeger pods..."
# Get all jaeger pod names
JAEGER_PODS=$(kubectl get pods -n istio-system -l app=jaeger --no-headers -o custom-columns=":metadata.name" 2>/dev/null)
if [ -n "$JAEGER_PODS" ]; then
  for JAEGER_POD in $JAEGER_PODS; do
    echo "Deleting Jaeger pod '$JAEGER_POD' in istio-system namespace..."
    kubectl delete pod "$JAEGER_POD" -n istio-system &>/dev/null
  done
  echo "All existing Jaeger pods are being deleted."

  # # Wait for Jaeger pods to be completely gone
  # echo "Waiting for all Jaeger pods to be terminated..."
  # TIMEOUT_DELETE=120 # 2 minutes timeout for deletion
  # COUNT_DELETE=0
  # while kubectl get pods -n istio-system -l app=jaeger --no-headers -o custom-columns=":metadata.name" | grep -q .; do
  #   if [ "$COUNT_DELETE" -ge "$TIMEOUT_DELETE" ]; then
  #     echo "Error: Jaeger pods did not terminate in time. Manual intervention may be required. Exiting."
  #     exit 1
  #   fi
  #   echo "Still waiting for Jaeger pods to terminate..."
  #   sleep 5
  #   COUNT_DELETE=$((COUNT_DELETE+5))
  # done
  echo "All existing Jaeger pods terminated."
else
  echo "No Jaeger pods found. Skipping deletion."
fi

# --- Wait for jaeger pod to be ready ---
echo "---"
echo "Waiting for jaeger pod to be ready..."
# This will now wait for a *new* Jaeger pod to become ready after old ones are gone
if ! kubectl wait --for=condition=Ready pod -n istio-system -l app=jaeger --timeout=5m; then
  echo "Error: Jaeger pod did not become ready in time. Exiting."
  exit 1
fi
echo "Jaeger pod is ready."

# --- Configuration Variables ---
HELM_VALUES_PATH="helm-chart/values.yaml"
HELM_CHART_NAME="md"
# It's better to fetch all traces and then filter/count locally,
# as Jaeger's 'limit' might not guarantee the exact number you want if
# there are more traces available.
JAEGER_URL="http://tracing.istio-system:80/jaeger/api/traces?service=frontend.default&limit=5000" # Increased limit
TARGET_TRACE_COUNT=1000
OUTPUT_FILE="jaeger_traces.json" # This can be a base name now, the full name will be constructed later
NAMESPACE="default" # Defined early for use in my-sleep-pod deletion
DEFAULT_CART_LATENCY1="0ms"
DEFAULT_CART_LATENCY2="0ms"
DEFAULT_CART_LATENCY="0ms"
DEFAULT_CHECKOUT_LATENCY="0ms"
DEFAULT_CURRENCY_LATENCY="0ms"
DEFAULT_PRODUCT_CATALOG_LATENCY="0ms"
LOAD_GENERATION_INTERVAL_SECONDS=10 # How often to check for traces (adjust as needed)

# OUTPUT_FILE_WITH_PARAMS will be constructed AFTER parsing arguments

# Variable to store the PID of the background kube_metrics.py process
KUBE_METRICS_PID=""

# --- Functions ---

# Function to clean up resources in case of script interruption
cleanup() {
  echo "" # Newline for cleaner output after potential interruption
  
  echo "---"
  echo "Cleaning up Helm chart: $HELM_CHART_NAME in namespace $NAMESPACE..."
  helm uninstall "$HELM_CHART_NAME" --namespace "$NAMESPACE" &>/dev/null
  kubectl delete -f loadgenerator.yaml

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
    -c|--cartLatency)
      CART_LATENCY="$2"
      shift 2
      ;;
    -c1|--cartLatency1)
      CART_LATENCY1="$2"
      shift 2
      ;;
    -c2|--cartLatency2)
      CART_LATENCY2="$2"
      shift 2
      ;;
    -o|--checkoutLatency)
      CHECKOUT_LATENCY="$2"
      shift 2
      ;;
    -r|--currencyLatency)
      CURRENCY_LATENCY="$2"
      shift 2
      ;;
    -p|--productCatalogLatency)
      PRODUCT_CATALOG_LATENCY="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [-u|--users <number_of_users>] [-c|--cartLatency <latency>] [-c1|--cartLatency1 <latency>] [-c2|--cartLatency2 <latency>] [-o|--checkoutLatency <latency>] [-r|--currencyLatency <latency>] [-p|--productCatalogLatency <latency>]"
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

if [ -z "$CART_LATENCY" ]; then
  CART_LATENCY=$DEFAULT_CART_LATENCY
  echo "No cart latency specified, using default value: $CART_LATENCY"
else
  echo "Using cart latency: $CART_LATENCY"
fi

if [ -z "$CART_LATENCY1" ]; then
  CART_LATENCY1=$DEFAULT_CART_LATENCY1
  echo "No cart replica 1 latency specified, using default value: $CART_LATENCY1"
else
  echo "Using cart replica 1 latency: $CART_LATENCY1"
fi

if [ -z "$CART_LATENCY2" ]; then
  CART_LATENCY2=$DEFAULT_CART_LATENCY2
  echo "No cart replica 2 latency specified, using default value: $CART_LATENCY2"
else
  echo "Using cart replica 2 latency: $CART_LATENCY2"
fi

if [ -z "$CHECKOUT_LATENCY" ]; then
  CHECKOUT_LATENCY=$DEFAULT_CHECKOUT_LATENCY
  echo "No checkout latency specified, using default value: $CHECKOUT_LATENCY"
else
  echo "Using checkout latency: $CHECKOUT_LATENCY"
fi

if [ -z "$CURRENCY_LATENCY" ]; then
  CURRENCY_LATENCY=$DEFAULT_CURRENCY_LATENCY
  echo "No currency latency specified, using default value: $CURRENCY_LATENCY"
else
  echo "Using currency latency: $CURRENCY_LATENCY"
fi

if [ -z "$PRODUCT_CATALOG_LATENCY" ]; then
  PRODUCT_CATALOG_LATENCY=$DEFAULT_PRODUCT_CATALOG_LATENCY
  echo "No product catalog latency specified, using default value: $PRODUCT_CATALOG_LATENCY"
else
  echo "Using product catalog latency: $PRODUCT_CATALOG_LATENCY"
fi

# --- Construct OUTPUT_FILE_WITH_PARAMS AFTER variables are set ---
OUTPUT_FILE_WITH_PARAMS="jaeger_traces_users_${USERS}"
LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS="loadgenerator_users_${USERS}"
RESOURCE_UTILIZATION_FILE_WITH_PARAMS="resource_utilization_users_${USERS}"
if [ -n "$CART_LATENCY" ] && [ "$CART_LATENCY" != "$DEFAULT_CART_LATENCY" ]; then
  OUTPUT_FILE_WITH_PARAMS="${OUTPUT_FILE_WITH_PARAMS}_cart_${CART_LATENCY}"
  LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS="${LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS}_cart_${CART_LATENCY}"
  RESOURCE_UTILIZATION_FILE_WITH_PARAMS="${RESOURCE_UTILIZATION_FILE_WITH_PARAMS}_cart_${CART_LATENCY}"
fi
if [ -n "$CART_LATENCY1" ] && [ "$CART_LATENCY1" != "$DEFAULT_CART_LATENCY1" ]; then
  OUTPUT_FILE_WITH_PARAMS="${OUTPUT_FILE_WITH_PARAMS}_cart1_${CART_LATENCY1}"
  LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS="${LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS}_cart1_${CART_LATENCY1}"
  RESOURCE_UTILIZATION_FILE_WITH_PARAMS="${RESOURCE_UTILIZATION_FILE_WITH_PARAMS}_cart1_${CART_LATENCY1}"
fi
if [ -n "$CART_LATENCY2" ] && [ "$CART_LATENCY2" != "$DEFAULT_CART_LATENCY2" ]; then
  OUTPUT_FILE_WITH_PARAMS="${OUTPUT_FILE_WITH_PARAMS}_cart2_${CART_LATENCY2}"
  LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS="${LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS}_cart2_${CART_LATENCY2}"
  RESOURCE_UTILIZATION_FILE_WITH_PARAMS="${RESOURCE_UTILIZATION_FILE_WITH_PARAMS}_cart2_${CART_LATENCY2}"
fi
if [ -n "$CHECKOUT_LATENCY" ] && [ "$CHECKOUT_LATENCY" != "$DEFAULT_CHECKOUT_LATENCY" ]; then
  OUTPUT_FILE_WITH_PARAMS="${OUTPUT_FILE_WITH_PARAMS}_checkout_${CHECKOUT_LATENCY}"
  LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS="${LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS}_checkout_${CHECKOUT_LATENCY}"
  RESOURCE_UTILIZATION_FILE_WITH_PARAMS="${RESOURCE_UTILIZATION_FILE_WITH_PARAMS}_checkout_${CHECKOUT_LATENCY}"
fi
if [ -n "$CURRENCY_LATENCY" ] && [ "$CURRENCY_LATENCY" != "$DEFAULT_CURRENCY_LATENCY" ]; then
  OUTPUT_FILE_WITH_PARAMS="${OUTPUT_FILE_WITH_PARAMS}_currency_${CURRENCY_LATENCY}"
  LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS="${LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS}_currency_${CURRENCY_LATENCY}"  
  RESOURCE_UTILIZATION_FILE_WITH_PARAMS="${RESOURCE_UTILIZATION_FILE_WITH_PARAMS}_currency_${CURRENCY_LATENCY}"
fi
if [ -n "$PRODUCT_CATALOG_LATENCY" ] && [ "$PRODUCT_CATALOG_LATENCY" != "$DEFAULT_PRODUCT_CATALOG_LATENCY" ]; then
  OUTPUT_FILE_WITH_PARAMS="${OUTPUT_FILE_WITH_PARAMS}_product_${PRODUCT_CATALOG_LATENCY}"
  LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS="${LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS}_product_${PRODUCT_CATALOG_LATENCY}"
  RESOURCE_UTILIZATION_FILE_WITH_PARAMS="${RESOURCE_UTILIZATION_FILE_WITH_PARAMS}_product_${PRODUCT_CATALOG_LATENCY}"
fi  

OUTPUT_FILE_WITH_PARAMS="${OUTPUT_FILE_WITH_PARAMS}.json"
LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS="${LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS}.txt"
RESOURCE_UTILIZATION_FILE_WITH_PARAMS="${RESOURCE_UTILIZATION_FILE_WITH_PARAMS}.txt"
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
  local key_path="$2" # e.g., ".loadGenerator.users"
  local value="$3"
  
  # Corrected yq command: The filter and file path are separate arguments.
  # No need for 'eval' when passing arguments directly.
  if ! yq eval --inplace "${key_path} = \"${value}\"" "$file"; then
      echo "Error: Failed to update key '${key_path}' in '$file' using yq."
      exit 1
  fi
}

# Function to update cartService replica latency using yq
update_cart_replica_latency() {
  local file="$1"
  local replica_name="$2" # e.g., "cartservice-replica-1"
  local latency_value="$3"

  # Corrected yq command: Filter and file path are separate arguments.
  if ! yq eval --inplace "( .cartService.replicaConfigs[] | select(.name == \"${replica_name}\") ).extraLatency = \"${latency_value}\"" "$file"; then
      echo "Error: Failed to update extraLatency for '${replica_name}' in cartService in '$file' using yq."
      exit 1
  fi
}

# Function to update service replica latency using yq
update_service_replica_latency() {
  local file="$1"
  local service_key="$2" # e.g., "checkoutService"
  local replica_name="$3" # e.g., "checkoutservice"
  local latency_value="$4"

  # yq command to update extraLatency for the specific replica within the service
  if ! yq eval --inplace "( .${service_key}.replicaConfigs[] | select(.name == \"${replica_name}\") ).extraLatency = \"${latency_value}\"" "$file"; then
      echo "Error: Failed to update extraLatency for '${replica_name}' in '${service_key}' in '$file' using yq."
      exit 1
  fi
}

# --- Apply the updates using the yq functions ---

# Update users (top-level key)
update_yaml_value "$HELM_VALUES_PATH" ".loadGenerator.users" "$USERS"

# Update cartService replica latencies
update_cart_replica_latency "$HELM_VALUES_PATH" "cartservice-replica-1" "$CART_LATENCY1"
update_cart_replica_latency "$HELM_VALUES_PATH" "cartservice-replica-2" "$CART_LATENCY2"

update_service_replica_latency "$HELM_VALUES_PATH" "cartService" "cartservice" "$CART_LATENCY"

# Update checkoutService extraLatency
update_service_replica_latency "$HELM_VALUES_PATH" "checkoutService" "checkoutservice" "$CHECKOUT_LATENCY"

# Update currencyService extraLatency
update_service_replica_latency "$HELM_VALUES_PATH" "currencyService" "currencyservice" "$CURRENCY_LATENCY"

# Update productCatalogService extraLatency
update_service_replica_latency "$HELM_VALUES_PATH" "productCatalogService" "productcatalogservice" "$PRODUCT_CATALOG_LATENCY"

if [ $? -ne 0 ]; then
  echo "Error: Failed to update $HELM_VALUES_PATH. Exiting."
  exit 1
fi
echo "$HELM_VALUES_PATH updated successfully."

# Install Helm chart
helm uninstall "$HELM_CHART_NAME" --namespace "$NAMESPACE" &>/dev/null
echo "Helm chart uninstalled."
kubectl delete -f loadgenerator.yaml
echo "Loadgenerator deleted."
echo "Installing helm chart '$HELM_CHART_NAME' in namespace '$NAMESPACE'..."
if ! helm install "$HELM_CHART_NAME" helm-chart --values "$HELM_VALUES_PATH" --namespace "$NAMESPACE" --create-namespace; then
  echo "Error: Helm chart installation failed. Exiting."
  exit 1
fi
echo "Helm chart installed successfully."

echo "Target trace count: $TARGET_TRACE_COUNT"
echo "---"
# Wait for pods to be ready
echo "Waiting for pods in namespace '$NAMESPACE' to be ready (timeout: 5m)..."
if ! kubectl wait --for=condition=Ready pods --all -n "$NAMESPACE" --timeout=5m; then
  echo "Error: Pods did not become ready in time. Exiting."
  helm uninstall "$HELM_CHART_NAME" --namespace "$NAMESPACE" &>/dev/null
  exit 1
fi
echo "All pods are ready."

kubectl apply -f loadgenerator.yaml
sleep 20

# --- Run kube_metrics.py in the background after all pods are ready ---
echo "Starting kube_metrics.py in the background for resource utilization tracing..."
python3 ../kube_metrics.py -d 200 -i 30 -a resource_utilization.txt &
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

mv resource_utilization.txt "$RESOURCE_UTILIZATION_FILE_WITH_PARAMS"

sleep 120

echo "---"
echo "Fetching locust.out from loadgenerator pod..."
pod_name=$(kubectl get pods -n "$NAMESPACE" --no-headers -o custom-columns=":metadata.name" | grep loadgenerator | head -n 1)

if [ -z "$pod_name" ]; then
    echo "Error: No pod with 'loadgenerator' in its name found in namespace '$NAMESPACE'."
else
    echo "Found loadgenerator pod: $pod_name"
    # Check if locust.out exists
    if kubectl exec -n "$NAMESPACE" "$pod_name" -- test -f locust.out; then
        echo "Copying locust.out from $pod_name..."
        if kubectl exec -n "$NAMESPACE" "$pod_name" -- cat locust.out > "$LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS"; then
            echo "Successfully copied locust.out to $LOADGENERATOR_OUTPUT_FILE_WITH_PARAMS"
        else
            echo "Error: Failed to copy locust.out from $pod_name."
        fi
    else
        echo "Error: locust.out not found in pod $pod_name."
    fi
fi

# kubectl exec 
# -----------------------------------------------------------------------

# Uninstall Helm chart
helm uninstall "$HELM_CHART_NAME" --namespace "$NAMESPACE"
echo "Helm chart uninstalled."
kubectl delete -f loadgenerator.yaml
echo "---"
echo "Script completed successfully."
