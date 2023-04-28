#!/bin/sh

MEMCACHED_IP=100.96.2.2
INTERNAL_AGENT_IP=10.0.32.5

echo "Please provide a name to save files as:"
read EXPERIMENT_NAME
echo "Will save output as ${EXPERIMENT_NAME}"

for i in 1 2 3
do
  echo "Starting run $i"
  touch "${EXPERIMENT_NAME}_${i}.txt"
  ./mcperf -s ${MEMCACHED_IP} -a  ${INTERNAL_AGENT_IP} --noload -T 16 -C 4 -D 4 -Q 1000 -c 4 -w 2 -t 5 --scan 30000:110000:5000 2>&1 | tee "${EXPERIMENT_NAME}_${i}.txt"
  echo "Done with run $i"
done
