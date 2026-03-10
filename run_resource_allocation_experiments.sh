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


REVERSE=false
APP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reverse)
      REVERSE=true
      shift
      ;;
    --app)
      APP="$2"
      shift 2
      ;;
    -*)
      echo "Unknown option: $1"
      exit 1
      ;;
    *)
      if [[ -z "$TRIAL_NUMBER" ]]; then
        TRIAL_NUMBER=$1
        shift
      else
        echo "Only one trial number can be provided."
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$TRIAL_NUMBER" || -z "$APP" ]]; then
  echo "Usage: $0 [--reverse] --app <onlineboutique|mediamicroservices> <trial_number>"
  exit 1
fi

if [[ "$APP" != "onlineboutique" && "$APP" != "mediamicroservices" ]]; then
  echo "Invalid app: $APP. Must be 'onlineboutique' or 'mediamicroservices'."
  echo "Usage: $0 [--reverse] --app <onlineboutique|mediamicroservices> <trial_number>"
  exit 1
fi

NUM_ITERATIONS=10
NUM_RECOMMENDATIONS=3
NUM_USERS=200
MEDIA_MICROSERVICES_PATH="DeathStarBench/mediaMicroservices"
ONLINEBOUTIQUES_PATH="microservices-demo-sleeps"

# --- SETUP ---

kubectl apply -f sleep.yaml

if [ "$REVERSE" = true ]; then
  LCPU="1500m"
  LMEM="1500Mi"
else
  LCPU="200m"
  LMEM="200Mi"
fi

if [[ "$APP" == "onlineboutique" ]]; then
  python3 manage_helm_resources.py $ONLINEBOUTIQUES_PATH/helm-chart update --limit-cpu $LCPU --limit-mem $LMEM
elif [[ "$APP" == "mediamicroservices" ]]; then
  python3 manage_helm_resources.py $MEDIA_MICROSERVICES_PATH/helm-chart/mediamicroservices update --limit-cpu $LCPU --limit-mem $LMEM
  python3 manage_helm_resources.py $MEDIA_MICROSERVICES_PATH/helm-chart/mediamicroservices/ update --service jaeger --limit-mem 5000Mi --limit-cpu 1000m
fi

# create helper function to run the mediamicroservices data collection
function run_mediamicroservices_data_collection {
  yes | gcloud container clusters resize eval2 --zone us-central1-c --project sysres-intern-test --node-pool=pool-1 --num-nodes=4 &
  yes | gcloud container clusters resize eval2 --zone us-central1-c --project sysres-intern-test --node-pool=pool-2 --num-nodes=4 &
  yes | gcloud container clusters resize eval2 --zone us-central1-c --project sysres-intern-test --node-pool=pool-3 --num-nodes=4 &
  yes | gcloud container clusters resize eval2 --zone us-central1-c --project sysres-intern-test --node-pool=pool-4 --num-nodes=4 &
  sleep 30
  kubectl apply -f sleep.yaml
  local round_number=$1
  cd $MEDIA_MICROSERVICES_PATH
  ./run_experiment.sh -u $NUM_USERS
  mv jaeger_traces_users_${NUM_USERS}.json jaeger_traces_users_${NUM_USERS}_round_${round_number}_trial_${TRIAL_NUMBER}.json
  mv resource_utilization.txt resource_utilization_round_${round_number}_trial_${TRIAL_NUMBER}.txt
  mv loadgenerator_users_${NUM_USERS}.txt loadgenerator_users_${NUM_USERS}_round_${round_number}_trial_${TRIAL_NUMBER}.txt
  cd -
}

function run_onlineboutique_data_collection {
  yes | gcloud container clusters resize eval2 --zone us-central1-c --project sysres-intern-test --node-pool=pool-1 --num-nodes=4 &
  yes | gcloud container clusters resize eval2 --zone us-central1-c --project sysres-intern-test --node-pool=pool-2 --num-nodes=4 &
  yes | gcloud container clusters resize eval2 --zone us-central1-c --project sysres-intern-test --node-pool=pool-3 --num-nodes=4 &
  yes | gcloud container clusters resize eval2 --zone us-central1-c --project sysres-intern-test --node-pool=pool-4 --num-nodes=4 &
  sleep 30
  kubectl apply -f sleep.yaml
  local round_number=$1
  cd $ONLINEBOUTIQUES_PATH
  ./run_experiment.sh -u $NUM_USERS
  mv jaeger_traces_users_${NUM_USERS}.json jaeger_traces_users_${NUM_USERS}_round_${round_number}_trial_${TRIAL_NUMBER}.json
  mv resource_utilization_users_${NUM_USERS}.txt resource_utilization_users_${NUM_USERS}_round_${round_number}_trial_${TRIAL_NUMBER}.txt
  mv loadgenerator_users_${NUM_USERS}.txt loadgenerator_users_${NUM_USERS}_round_${round_number}_trial_${TRIAL_NUMBER}.txt
  cd -
}

for ((i=0; i<NUM_ITERATIONS; i++)); do

  echo "Iteration $i"
  if [[ "$APP" == "onlineboutique" ]]; then
    run_onlineboutique_data_collection $i
    APP_PATH=$ONLINEBOUTIQUES_PATH
    HELM_PATH="$ONLINEBOUTIQUES_PATH/helm-chart"
    JAEGER_TRACES_PATH="$ONLINEBOUTIQUES_PATH/jaeger_traces_users_${NUM_USERS}_round_${i}_trial_${TRIAL_NUMBER}.json"
    RESOURCE_UTILIZATION_PATH="$ONLINEBOUTIQUES_PATH/resource_utilization_users_${NUM_USERS}_round_${i}_trial_${TRIAL_NUMBER}.txt"
  elif [[ "$APP" == "mediamicroservices" ]]; then
    run_mediamicroservices_data_collection $i
    APP_PATH=$MEDIA_MICROSERVICES_PATH
    HELM_PATH="$MEDIA_MICROSERVICES_PATH/helm-chart/mediamicroservices"
    JAEGER_TRACES_PATH="$MEDIA_MICROSERVICES_PATH/jaeger_traces_users_${NUM_USERS}_round_${i}_trial_${TRIAL_NUMBER}.json"
    RESOURCE_UTILIZATION_PATH="$MEDIA_MICROSERVICES_PATH/resource_utilization_round_${i}_trial_${TRIAL_NUMBER}.txt"
  fi

  python3 manage_helm_resources.py $HELM_PATH read -y
  mv resource_summary.yaml resource_summary_round_${i}_trial_${TRIAL_NUMBER}.yaml
  # get the resource reallocation recommendations
  echo "Running get_resource_reallocation for round ${i}"

  declare -a BLAZE_ARGS
  BLAZE_ARGS=(--jaeger_traces_path="$JAEGER_TRACES_PATH" --resource_utilization_path="$RESOURCE_UTILIZATION_PATH" --utilization_only --num_recommendations="$NUM_RECOMMENDATIONS")

  if [ "$REVERSE" = true ]; then
    BLAZE_ARGS+=(--least)
  fi

  REALLOC_OUTPUT=$(blaze run //experimental/sysres/critical_path:get_resource_reallocation -- "${BLAZE_ARGS[@]}" 2>&1)
  echo "Reallocation output:\n$REALLOC_OUTPUT"

  if [ "$REVERSE" = true ]; then
    # Extract services with least CPU drag
    CPU_DRAG_SERVICES=$(echo "$REALLOC_OUTPUT" | grep "Least 3 CPU Drag:" | sed 's/Least 3 CPU Drag: \[//' | sed 's/\]//' | tr -d " " | sed 's/),(/\n/g' | sed "s/[()']//g" | cut -d',' -f1)
    # Extract services with least Memory drag
    MEM_DRAG_SERVICES=$(echo "$REALLOC_OUTPUT" | grep "Least 3 Memory Drag:" | sed 's/Least 3 Memory Drag: \[//' | sed 's/\]//' | tr -d " " | sed 's/),(/\n/g' | sed "s/[()']//g" | cut -d',' -f1)
    echo "Least CPU Drag Services:\n$CPU_DRAG_SERVICES"
    echo "Least Memory Drag Services:\n$MEM_DRAG_SERVICES"
    CPU_INC="-200m"
    MEM_INC="-200Mi"
    CPU_DELTA_STR="200m"
    MEM_DELTA_STR="200Mi"
    CPU_ACTION="Decreasing"
    MEM_ACTION="Decreasing"
  else
    # Extract services with high CPU drag
    CPU_DRAG_SERVICES=$(echo "$REALLOC_OUTPUT" | grep "Top 3 CPU Drag:" | sed 's/Top 3 CPU Drag: \[//' | sed 's/\]//' | tr -d " " | sed 's/),(/\n/g' | sed "s/[()']//g" | cut -d',' -f1)
    # Extract services with high Memory drag
    MEM_DRAG_SERVICES=$(echo "$REALLOC_OUTPUT" | grep "Top 3 Memory Drag:" | sed 's/Top 3 Memory Drag: \[//' | sed 's/\]//' | tr -d " " | sed 's/),(/\n/g' | sed "s/[()']//g" | cut -d',' -f1)
    echo "CPU Drag Services:\n$CPU_DRAG_SERVICES"
    echo "Memory Drag Services:\n$MEM_DRAG_SERVICES"
    CPU_INC="100m"
    MEM_INC="100Mi"
    CPU_DELTA_STR="100m"
    MEM_DELTA_STR="100Mi"
    CPU_ACTION="Increasing"
    MEM_ACTION="Increasing"
  fi

  # Update CPU limits
  for service in $CPU_DRAG_SERVICES; do
    if [[ -n "$service" ]]; then
      echo "$CPU_ACTION CPU for $service by $CPU_DELTA_STR"
      python3 ./manage_helm_resources.py "$HELM_PATH" update --service "$service" --increase-limit-cpu $CPU_INC
    fi
  done

  # Update Memory limits
  for service in $MEM_DRAG_SERVICES; do
    if [[ -n "$service" ]]; then
      echo "$MEM_ACTION Memory for $service by $MEM_DELTA_STR"
      python3 ./manage_helm_resources.py "$HELM_PATH" update --service "$service" --increase-limit-mem $MEM_INC
    fi
  done

done
