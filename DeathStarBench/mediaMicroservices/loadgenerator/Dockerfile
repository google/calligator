FROM ubuntu:22.04

RUN apt-get update \
  && apt-get install -y \
      git libssl-dev luarocks libz-dev make curl \
      && apt-get clean

RUN git clone https://github.com/delimitrou/DeathStarBench.git \
  && cd DeathStarBench \
  && git submodule init && git submodule update \
  && cd wrk2 \
  && make

COPY compose-review.lua .
COPY register_movies.sh .
COPY register_users.sh .

RUN chmod +x register_movies.sh register_users.sh

ENTRYPOINT /bin/bash register_movies.sh nginx-web-server ; \
  /bin/bash register_users.sh nginx-web-server ; \
  /DeathStarBench/wrk2/wrk -D exp -t 4 -c 4 -d 15s -L -s ./compose-review.lua http://nginx-web-server:8080/wrk2-api/review/compose -R 10 > /dev/null 2>&1 ; \
  /DeathStarBench/wrk2/wrk -D exp -t "${NUM_THREADS}" -c "${NUM_CONNECTIONS}" -d "${DURATION}" -L -s ./compose-review.lua http://nginx-web-server:8080/wrk2-api/review/compose -R "${RPS}" ; \
  sleep infinity

