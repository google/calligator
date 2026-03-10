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


NUM_ITERATIONS=10
NUM_RECOMMENDATIONS=3
NUM_USERS=200
MEDIA_MICROSERVICES_PATH="DeathStarBench/mediaMicroservices"
ONLINEBOUTIQUES_PATH="microservices-demo-sleeps"

# get trial number from argument
if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <trial_number> <initial_resource_allocation> <application_name>"
  echo "application_name must be one of 'mediamicroservices' or 'onlineboutique'"
  exit 1
fi
TRIAL_NUMBER=$1
INITIAL_RESOURCE_ALLOCATION=$2
APPLICATION_NAME=$3

if [[ "$APPLICATION_NAME" != "mediamicroservices" && "$APPLICATION_NAME" != "onlineboutique" ]]; then
  echo "Invalid application name: $APPLICATION_NAME"
  echo "application_name must be one of 'mediamicroservices' or 'onlineboutique'"
  exit 1
fi

# --- SETUP ---

kubectl apply -f sleep.yaml

if [[ "$APPLICATION_NAME" == "mediamicroservices" ]]; then
  APP_PATH=$MEDIA_MICROSERVICES_PATH
  HELM_PATH="$MEDIA_MICROSERVICES_PATH/helm-chart/mediamicroservices"
elif [[ "$APPLICATION_NAME" == "onlineboutique" ]]; then
  APP_PATH=$ONLINEBOUTIQUES_PATH
  HELM_PATH="$ONLINEBOUTIQUES_PATH/helm-chart/"
fi

# Initial resource allocation
echo "Performing initial resource allocation for $APPLICATION_NAME"
python3 manage_helm_resources.py $HELM_PATH update --limit-cpu ${INITIAL_RESOURCE_ALLOCATION}m --limit-mem ${INITIAL_RESOURCE_ALLOCATION}Mi --req-cpu 100m --req-mem 100Mi
if [[ "$APPLICATION_NAME" == "mediamicroservices" ]]; then
  python3 manage_helm_resources.py $HELM_PATH/ update --service jaeger --limit-mem 5000Mi --limit-cpu 2000m
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
  # run the data collection
  if [[ "$APPLICATION_NAME" == "mediamicroservices" ]]; then
    run_mediamicroservices_data_collection $i
    JAEGER_TRACES_PATH="$APP_PATH/jaeger_traces_users_${NUM_USERS}_round_${i}_trial_${TRIAL_NUMBER}.json"
    RESOURCE_UTILIZATION_PATH="$APP_PATH/resource_utilization_round_${i}_trial_${TRIAL_NUMBER}.txt"
  elif [[ "$APPLICATION_NAME" == "onlineboutique" ]]; then
    run_onlineboutique_data_collection $i
    JAEGER_TRACES_PATH="$APP_PATH/jaeger_traces_users_${NUM_USERS}_round_${i}_trial_${TRIAL_NUMBER}.json"
    RESOURCE_UTILIZATION_PATH="$APP_PATH/resource_utilization_users_${NUM_USERS}_round_${i}_trial_${TRIAL_NUMBER}.txt"
  fi

  python3 manage_helm_resources.py $HELM_PATH read -y
  mv resource_summary.yaml resource_summary_${APPLICATION_NAME}_round_${i}_trial_${TRIAL_NUMBER}.yaml
  # get the resource reallocation recommendations
  echo "Running get_resource_reallocation for round ${i}"
  REALLOC_OUTPUT=$(blaze run //experimental/sysres/critical_path:get_resource_reallocation -- \
    --jaeger_traces_path="$JAEGER_TRACES_PATH" \
    --resource_utilization_path="$RESOURCE_UTILIZATION_PATH" \
    --num_recommendations="$NUM_RECOMMENDATIONS" 2>&1)

        # --utilization_only \

  echo "Reallocation output:\n$REALLOC_OUTPUT"

  # Extract services with high CPU drag
  TOP_CPU_DRAG_SERVICES=$(echo "$REALLOC_OUTPUT" | grep "Top 3 CPU Drag:" | sed 's/Top 3 CPU Drag: \[//' | sed 's/\]//' | tr -d " " | sed 's/),(/\n/g' | sed "s/[()']//g" | cut -d',' -f1)
  # Extract services with low CPU drag
  LEAST_CPU_DRAG_SERVICES=$(echo "$REALLOC_OUTPUT" | grep "Least 3 CPU Drag:" | sed 's/Least 3 CPU Drag: \[//' | sed 's/\]//' | tr -d " " | sed 's/),(/\n/g' | sed "s/[()']//g" | cut -d',' -f1)

  # Extract services with high Memory drag
  TOP_MEM_DRAG_SERVICES=$(echo "$REALLOC_OUTPUT" | grep "Top 3 Memory Drag:" | sed 's/Top 3 Memory Drag: \[//' | sed 's/\]//' | tr -d " " | sed 's/),(/\n/g' | sed "s/[()']//g" | cut -d',' -f1)
  # Extract services with low Memory drag
  LEAST_MEM_DRAG_SERVICES=$(echo "$REALLOC_OUTPUT" | grep "Least 3 Memory Drag:" | sed 's/Least 3 Memory Drag: \[//' | sed 's/\]//' | tr -d " " | sed 's/),(/\n/g' | sed "s/[()']//g" | cut -d',' -f1)

  echo "Top CPU Drag Services:\n$TOP_CPU_DRAG_SERVICES"
  echo "Least CPU Drag Services:\n$LEAST_CPU_DRAG_SERVICES"
  echo "Top Memory Drag Services:\n$TOP_MEM_DRAG_SERVICES"
  echo "Least Memory Drag Services:\n$LEAST_MEM_DRAG_SERVICES"

  CPU_TRANSFER_AMOUNT="50m"
  MEM_TRANSFER_AMOUNT="50Mi"

  readarray -t LEAST_CPU_ARRAY <<<"$LEAST_CPU_DRAG_SERVICES"
  readarray -t TOP_CPU_ARRAY <<<"$TOP_CPU_DRAG_SERVICES"
  readarray -t LEAST_MEM_ARRAY <<<"$LEAST_MEM_DRAG_SERVICES"
  readarray -t TOP_MEM_ARRAY <<<"$TOP_MEM_DRAG_SERVICES"

  # Reallocate CPU
  for ((k=0; k<NUM_RECOMMENDATIONS; k++)); do
    from_service=${LEAST_CPU_ARRAY[$k]}
    to_service=${TOP_CPU_ARRAY[$k]}
    if [[ -n "$from_service" && -n "$to_service" ]]; then
      echo "Attempting to reallocate CPU $CPU_TRANSFER_AMOUNT from $from_service to $to_service"
      python3 ./manage_helm_resources.py "$HELM_PATH" reallocate \
        --from-service "$from_service" \
        --to-service "$to_service" \
        --amount-cpu "$CPU_TRANSFER_AMOUNT"
    fi
  done

  # Reallocate Memory
  for ((k=0; k<NUM_RECOMMENDATIONS; k++)); do
    from_service=${LEAST_MEM_ARRAY[$k]}
    to_service=${TOP_MEM_ARRAY[$k]}
    if [[ -n "$from_service" && -n "$to_service" ]]; then
      echo "Attempting to reallocate Memory $MEM_TRANSFER_AMOUNT from $from_service to $to_service"
      python3 ./manage_helm_resources.py "$HELM_PATH" reallocate \
        --from-service "$from_service" \
        --to-service "$to_service" \
        --amount-mem "$MEM_TRANSFER_AMOUNT"
    fi
  done

done
