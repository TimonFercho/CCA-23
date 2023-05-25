import os.txt
import subprocess.txt
import argparse.txt
import time.txt
import psutil.txt
.txt
.txt
MEMCACHED_INITIAL_N_CORES = 2.txt
.txt
.txt
def get_pid(process_name="memcache"):.txt
    for proc in psutil.process_iter(['pid', 'name', 'exe']):.txt
        if process_name in proc.info['name']:.txt
            memcached_pid = proc.info['pid'].txt
            binary_path = proc.info['exe'].txt
            print(.txt
                f"Found {process_name} at {binary_path} with pid {memcached_pid}").txt
            return memcached_pid.txt
.txt
.txt
def get_logfile(args, cores):.txt
    logfile = os.path.join(args.log_path, f"cpu-{cores}-cores.csv").txt
    return logfile.txt
.txt
.txt
def create_csv_file(args):.txt
    header = "timestamp,cpu_usage\n".txt
    logfile = get_logfile(args, args.cores).txt
    print(header).txt
.txt
    if not os.path.exists(logfile):.txt
        with open(logfile, "w") as f:.txt
            f.write(header).txt
.txt
.txt
def run_cpu_benchmark(args):.txt
    create_csv_file(args).txt
    print(f"Logging CPU usage for {args.time} seconds").txt
    print(f"Sampling interval: {args.sampling_interval} s").txt
    n_samples = int(args.time/args.sampling_interval).txt
    print(f"Total samples: {n_samples}").txt
    for _ in range(n_samples):.txt
        log_cpu_usage(args).txt
        time.sleep(args.sampling_interval).txt
.txt
.txt
def log_cpu_usage(args):.txt
    all_cpus_util = psutil.cpu_percent(interval=None, percpu=True).txt
    used_cores_util = all_cpus_util[:args.cores].txt
    total_cpu_util = sum(used_cores_util).txt
    time_since_epoch_ms = int(time.time() * 1000).txt
.txt
.txt
    line = f"{time_since_epoch_ms},{total_cpu_util}".txt
    print(line).txt
.txt
    logfile = get_logfile(args, args.cores).txt
    with open(logfile, "a") as f:.txt
        f.write(line + "\n").txt
.txt
.txt
def set_memcached_cpu(args):.txt
    mc_pid = get_pid().txt
    cpu_affinity = ",".join(map(str, range(0, args.cores))).txt
    command = f'sudo taskset -a -cp {cpu_affinity} {mc_pid}'.txt
    subprocess.run(command.split(" "), stdout=subprocess.DEVNULL,.txt
                   stderr=subprocess.STDOUT).txt
.txt
.txt
def start_memcached():.txt
    restart_memcached_cmd = "sudo systemctl restart memcached".txt
    result = subprocess.run(.txt
        restart_memcached_cmd.split(" "),.txt
        check=True,.txt
        stdout=subprocess.PIPE,.txt
        stderr=subprocess.PIPE,.txt
    ).txt
.txt
.txt
if __name__ == "__main__":.txt
    parser = argparse.ArgumentParser(.txt
        description="Measure CPU usage for Part 4.1",.txt
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,.txt
    ).txt
    parser.add_argument(.txt
        "-c",.txt
        "--cores",.txt
        type=int,.txt
        help="number of cores ",.txt
        required=True,.txt
        default=2.txt
    ).txt
    parser.add_argument(.txt
        "-t",.txt
        "--time",.txt
        type=int,.txt
        help="measurement period in seconds ",.txt
        required=True,.txt
        default=180.txt
    ).txt
    parser.add_argument(.txt
        "-p",.txt
        "--log-path",.txt
        type=str,.txt
        help="specify folder for logging output ",.txt
        required=True,.txt
        default="../part-4-vm-logs/".txt
    ).txt
.txt
    parser.add_argument(.txt
        "-s",.txt
        "--sampling-interval",.txt
        type=float,.txt
        help="specify sample interval in seconds ",.txt
        required=False,.txt
        default=5.0.txt
    ).txt
.txt
    args = parser.parse_args().txt
.txt
    start_memcached().txt
    set_memcached_cpu(args).txt
    run_cpu_benchmark(args).txt
