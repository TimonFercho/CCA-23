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


def set_memcached_cpu(pid, no_of_cpus):
    cpu_affinity = ",".join(map(str, range(0, no_of_cpus)))
    print(f'Setting Memcached CPU affinity to {cpu_affinity}')
    command = f'sudo taskset -a -cp {cpu_affinity} {pid}'
    #logger.log_memchached_state(no_of_cpus)
    subprocess.run(command.split(" "), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return pid, no_of_cpus


def start_memcached():
    restart_memcached_cmd = "sudo systemctl restart memcached"
    result = subprocess.run(
        restart_memcached_cmd.split(" "),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_part_4(args):

    schedule = None

    try:

        print("in run part 4")

        #setting number of cores
        set_memcached_cpu(memcached_pid, args.cores)
        mc_process = psutil.Process(memcached_pid)

        schedule = parsecs.Schedule(mc_cores= args.cores)

        sampling_interval = 0.2

        while(not schedule.is_complete()):

            print("in iteration")

            all_cpus_util = psutil.cpu_percent(interval=None, percpu=True)
            #mc_util = mc_process.cpu_percent() 

            #memcached_expanded = False

            # memcached needs to expand
            if schedule.mc_cores == 1 and all_cpus_util[0] > 75:  #mc_util > 70:
                schedule.update_for_memcached(mc_cores=2)
                set_memcached_cpu(memcached_pid, no_of_cpus=2)
                #memcached_expanded = True

            # memcached is allowed to retract
            elif schedule.mc_cores == 2 and  all_cpus_util[0] + all_cpus_util[1] < 60: #mc_util < 120:
                set_memcached_cpu(memcached_pid, no_of_cpus=1)
                schedule.update_for_memcached(mc_cores=1)

            #optmize parsec job scheduling
            schedule.update_internal_parsec(all_cpus_util)

            # check currently running jobs, remove containers if jobs are finished
            schedule.update_state()

            time.sleep(sampling_interval)
    
    except Exception as e:
        if schedule is not None:
            schedule.remove_all_containers()
        raise(e)
    
    schedule.remove_all_containers()




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
        type=str,
        help="specify folder for logging output ",
        default=20
    )

    args = parser.parse_args()

    print("in the main of controller.py")

    set_pid()
    run_part_4(args)



