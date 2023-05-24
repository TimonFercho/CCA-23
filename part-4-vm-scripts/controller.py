import os
import subprocess
import sys
import argparse
from datetime import datetime
import time 
import psutil

import parsecs


MEMCACHED_INITIAL_N_CORES = 1

memcached_pid = None

filepath = ""

def set_pid(process_name = "memcache"):
    for proc in psutil.process_iter():
        if process_name in proc.name():
            memcached_pid = proc.pid
            return memcached_pid
        
def create_csv_file(args):

    header = "timestamp,cpu_usage\n"

    filename = "memcached_cpu_usage_cores{args.cores}_threads2.csv"
    filepath = os.path.join(args.log_path, filename)

    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            f.write(header)


def init_memcached_config():
    process_name = "memcache"

    # Find the pid of memcache
    for proc in psutil.process_iter():
        if process_name in proc.name():
            memcached_pid = proc.pid
            break
    
    #command = f"sudo renice -n -19 -p {pid}"
    #subprocess.run(command.split(" "), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    # Set the cpu affinity of memcached to CPU 0
    return set_memcached_cpu( memcached_pid, MEMCACHED_INITIAL_N_CORES)


def set_memcached_cpu(pid, no_of_cpus, logger):
    cpu_affinity = ",".join(map(str, range(0, no_of_cpus)))
    print(f'Setting Memcached CPU affinity to {cpu_affinity}')
    command = f'sudo taskset -a -cp {cpu_affinity} {pid}'
    #logger.log_memchached_state(no_of_cpus)
    subprocess.run(command.split(" "), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return pid, no_of_cpus


def start_memcached(logger):
    restart_memcached_cmd = "sudo systemctl restart memcached"
    result = subprocess.run(
        restart_memcached_cmd.split(" "),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_part_4(args):

    #setting number of cores
    set_memcached_cpu(memcached_pid, args.cores)
    mc_process = psutil.Process(memcached_pid)

    schedule = parsecs.Schedule(mc_cores= args.cores)

    sampling_interval = 0.1

    while(not schedule.is_complete()):

        all_cpus_util = psutil.cpu_percent(interval=None, percpu=True)
        #mc_util = mc_process.cpu_percent() 

        #memcached_expanded = False

        # check currently running jobs, remove cotnainers if jobs are finished
        schedule.update_state()

        # memcached needs to expand
        if schedule.mc_cores == 1 and all_cpus_util[0] + all_cpus_util[1] > 75:  #mc_util > 70:
            schedule.update_for_memcached(mc_cores=2)
            set_memcached_cpu(memcached_pid, no_of_cpus=2)
            #memcached_expanded = True

        # memcached is allowed to retract
        elif schedule.mc_cores == 2 and  all_cpus_util[0] + all_cpus_util[1] < 60: #mc_util < 120:
            set_memcached_cpu(memcached_pid, no_of_cpus=1)
            schedule.update_for_memcached(mc_cores=1)

        #optmize parsec job scheduling
        schedule.update_internal_parsec(all_cpus_util)

        time.sleep(sampling_interval)




if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Measure CPU usage for Part 4.1",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--cores",
        type=int,
        help="number of cores ",
        required=True,
        default=1
    )
    parser.add_argument(
        "-p",
        "--log-path",
        type=int,
        help="specify folder for logging output ",
        required=True,
        default=20
    )

    args = parser.parse_args()

    set_pid()
    run_part_4(args)



