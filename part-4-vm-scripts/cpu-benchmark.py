import os
import subprocess
import argparse
import time
import psutil


MEMCACHED_INITIAL_N_CORES = 2


def get_pid(process_name="memcache"):
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        if process_name in proc.info['name']:
            memcached_pid = proc.info['pid']
            binary_path = proc.info['exe']
            print(
                f"Found {process_name} at {binary_path} with pid {memcached_pid}")
            return memcached_pid


def get_logfile(args, cores):
    logfile = os.path.join(args.log_path, f"cpu-{cores}-cores.csv")
    return logfile


def create_csv_file(args):
    header = "timestamp,cpu_usage\n"
    logfile = get_logfile(args, args.cores)
    print(header)

    if not os.path.exists(logfile):
        with open(logfile, "w") as f:
            f.write(header)


def run_cpu_benchmark(args):
    create_csv_file(args)
    mc_pid = get_pid()
    print(f"Logging CPU usage for {args.time} seconds")
    print(f"Sampling interval: {args.sampling_interval} ms")
    n_samples = int(args.time/args.sampling_interval)
    print(f"Total samples: {n_samples}")
    for _ in range(n_samples):
        log_cpu_usage(args, mc_pid)
        time.sleep(args.sampling_interval)


def log_cpu_usage(args, pid):
    mc_proc = psutil.Process(pid)
    time_since_epoch_ms = int(time.time() * 1000)
    cpu_usage = mc_proc.cpu_percent(interval=None)

    line = f"{time_since_epoch_ms},{cpu_usage}"
    print(line)

    logfile = get_logfile(args, args.cores)
    with open(logfile, "a") as f:
        f.write(line + "\n")


def set_memcached_cpu(args):
    mc_pid = get_pid()
    cpu_affinity = ",".join(map(str, range(0, args.cores)))
    command = f'sudo taskset -a -cp {cpu_affinity} {mc_pid}'
    subprocess.run(command.split(" "), stdout=subprocess.DEVNULL,
                   stderr=subprocess.STDOUT)


def start_memcached():
    restart_memcached_cmd = "sudo systemctl restart memcached"
    result = subprocess.run(
        restart_memcached_cmd.split(" "),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


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
        default=180
    )
    parser.add_argument(
        "-p",
        "--log-path",
        type=str,
        help="specify folder for logging output ",
        required=True,
        default="../part-4-vm-logs/"
    )

    parser.add_argument(
        "-s",
        "--sampling-interval",
        type=float,
        help="specify sample interval in seconds ",
        required=False,
        default=5.0
    )

    args = parser.parse_args()

    start_memcached()
    set_memcached_cpu(args)
    run_cpu_benchmark(args)
