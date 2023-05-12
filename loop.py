import os
import subprocess
import sys
import argparse
import re
from datetime import datetime
import json

ALL_BENCHMARKS = [
    "blackscholes",
    "canneal",
    "dedup",
    "ferret",
    "freqmine",
    "radix",
    "vips",
]


def run_part_3():
    print(">> Running part 3")
    schedule_dir = "schedules"
    schedule_name = "scheduleA"

    json_file_path = f"{schedule_dir}/{schedule_name}.json"

    with open(json_file_path, "r") as j:
        schedule = json.loads(j.read())

    num_jobs_done = 0

    running_jobs = {}

    # hard coded the while loop to 8 for part 3 because there are 8 total jobs running
    while num_jobs_done != 8:
        for node_id, node_schedule in enumerate(schedule):
            for run_id, run in enumerate(node_schedule.runs):
                if not run:
                    continue
                job = run[0]
                # if does_pod_exist(job):
                if running_jobs[job] is not None and running_jobs[job] == 1:
                    # info = get_pod_info(job)

                    info = {}
                    info["STATUS"] = "Succeeded"
                    info["NAME"] = job

                    is_running = (
                        info["STATUS"] == "Running"
                    )  # TODO: check if job is running based on info
                    if is_running:
                        # come back later to check if job is complete
                        continue

                    is_complete = (
                        info["STATUS"] == "Succeeded"
                    )  # TODO: check if job is complete based on info

                    if is_complete:
                        # job is done, so we remove it from the queue
                        print(schedule[node_id].runs[run_id])
                        schedule[node_id].runs[run_id].pop(0)
                        print(schedule[node_id].runs[run_id])
                        job = run[0]
                        print(run)

                        running_jobs[job] = 0

                        num_jobs_done += 1

                    job_name = info["NAME"]
                    if info["STATUS"] == "Failed":
                        num_jobs_done += 1
                        print(f">> Job/{job_name} failed")

                        running_jobs[job] = 0

                if not run:
                    # no more jobs to run
                    continue

                # we still have a job left to run
                # start job
                else:
                    running_jobs[job] = 1

        # TODO: introduce some delay?

    print(">> Part 3 completed")


if __name__ == "__main__":
    run_part_3()
