import os
import subprocess
import sys
import argparse
from datetime import datetime
import time 
import psutil


MEMCACHED_INITIAL_N_CORES = 2

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
        

def run_cpu_benchmark(args):

    #setting number of cores
    set_memcached_cpu(memcached_pid, args.cores)

    total_time = args.time
    sampling_interval = 0.2

    for i in range(int(total_time/sampling_interval)):
        get_cpu_usage()
        time.sleep(sampling_interval)


def get_cpu_usage(mc_pid, print_log=True):
    #psutil.cpu_percent(interval=None, percpu=True)
    mc_proc = psutil.Process(mc_pid)
    time_since_epoch_ms = int(time.time() * 1000)
    cpu_usage = mc_proc.cpu_percent(interval=None)

    line = f"{time_since_epoch_ms},{cpu_usage}"
    if print_log:
        print(line)
    
    with open(filepath, "a") as f:
        f.write(line)



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


"""
if __name__ == "__main__":
    mc_pid, no_of_cpus = init_memcached_config(logger)
    start_memcached(logger)
    while True:
        print_cpu_usage(mc_pid)
        time.sleep(1)
"""


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
        default=2
    )
    parser.add_argument(
        "-t",
        "--time",
        type=int,
        help="measurement period in seconds ",
        required=True,
        default=20
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
    run_cpu_benchmark(args)



