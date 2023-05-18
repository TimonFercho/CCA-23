import shutil
import os
import subprocess
import sys
import argparse
import re
from datetime import datetime
import json
import get_time
import paramiko
import fileinput
from time import sleep

ALL_BENCHMARKS = [
    "blackscholes",
    "canneal",
    "dedup",
    "ferret",
    "freqmine",
    "radix",
    "vips",
]


client_a = paramiko.SSHClient()
client_b = paramiko.SSHClient()
client_measure = paramiko.SSHClient()

client_command = "sudo sh -c 'echo deb-src http://europe-west3.gce.archive.ubuntu.com/ubuntu/ bionic main restricted >> /etc/apt/sources.list' "
client_command += "sudo apt-get update \n"
client_command += "sudo apt-get install libevent-dev libzmq3-dev git make g++ --yes \n"
client_command += "sudo apt-get build-dep memcached --yes \n"
client_command += "git clone https://github.com/eth-easl/memcache-perf-dynamic.git \n"
client_command += "cd memcache-perf-dynamic \n"
client_command += "make"


def get_client_ips(internal=False):
    client_agent_a_info = get_node_info("client-agent-a")
    client_agent_b_info = get_node_info("client-agent-b")
    client_measure_info = get_node_info("client-measure")

    if not (all([client_agent_a_info, client_agent_b_info, client_measure_info])):
        raise RuntimeError("Could not get node info for mcperf compilation")

    type = "INTERNAL-IP" if internal else "EXTERNAL-IP"
    client_agent_a_IP = client_agent_a_info[type]
    client_agent_b_IP = client_agent_b_info[type]
    client_measure_IP = client_measure_info[type]

    return client_agent_a_IP, client_agent_b_IP, client_measure_IP


def connect_mcperfs():

    print(">> Setting up SSH connection to compile mcperf")

    client_agent_a_IP, client_agent_b_IP, client_measure_IP = get_client_ips(
        internal=False)

    client_a.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client_a.connect(client_agent_a_IP, 22, username="ubuntu")

    client_b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client_b.connect(client_agent_b_IP, 22, username="ubuntu")

    client_measure.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client_measure.connect(client_measure_IP, 22, username="ubuntu")


def spin_up_cluster(args):
    if args.deploy_cluster:
        print(f">> Setting up part {args.task}")
        os.environ["KOPS_STATE_STORE"] = f"gs://{args.project}-{args.user}"
        os.environ["PROJECT"] = args.project

        print(">> Creating cluster")
        if does_cluster_exist(args.cluster_name):
            print(">> Cluster already exists")
        else:
            subprocess.run(
                ["kops", "create", "-f", args.userYaml],
                check=True,
            )

        print(">> Deploying cluster")
        if is_cluster_deployed(args.cluster_name):
            print(">> Cluster already deployed")
        else:
            subprocess.run(
                ["kops", "update", "cluster", args.cluster_name, "--yes", "--admin"],
                check=True,
            )
            print(">> Waiting for cluster to be ready")
            subprocess.run(["kops", "validate", "cluster",
                           "--wait", "10m"], check=True)
            print(">> Cluster deployed successfully")

    connect_mcperfs()

    if args.compile_mcperf:
        print(">> Compiling mcperf")
        client_a.exec_command(client_command)
        client_b.exec_command(client_command)
        client_measure.exec_command(client_command)
    else:
        print(">> Skipping mcperf compilation")

    print(f">> Finished setting up part {args.task}")


def log_job_time(schedule, schedule_dir):
    print(">> Logging job times")
    results_file = f"{schedule_dir}/results.json"
    parsec_times_file = f"{schedule_dir}/parsec_times.csv"

    JSON_COMMAND = f"kubectl get pods -o json > {results_file}"
    subprocess.run(JSON_COMMAND, shell=True, check=True)

    parsec_df = get_time.get_time(results_file)

    for _, node_schedule in enumerate(schedule):
        for _, run in enumerate(node_schedule['runs']):
            for job in run:
                if 'memcached' in job:
                    continue
                parsec_df.loc[parsec_df['name'] == job,
                              'machine'] = node_schedule['node']

    parsec_df.to_csv(parsec_times_file, index=False)


def create_modified_config_file(args, benchmark, n_threads):
    with open(
        f"{args.cca_directory}/parsec-benchmarks/part2b/{benchmark}.yaml", "r"
    ) as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if "-n 1" in line:
                lines[i] = line.replace("-n 1", f"-n {n_threads}")
        with open(
            f"{args.cca_directory}/parsec-benchmarks/part2b/{benchmark}_{n_threads}.yaml",
            "w",
        ) as f:
            f.writelines(lines)


def tear_down_cluster(args):
    if not is_cluster_deployed(args.cluster_name):
        print(">> Cluster already deleted")
        return

    if args.keep_alive:
        print(">> Cluster will be kept alive")
        return

    print(">> Deleting cluster")
    subprocess.run(
        ["kops", "delete", "cluster", args.cluster_name, "--yes"], check=True
    )
    print(">> Cluster deleted successfully")


def execute_ssh_command(client, command):
    _, stdout, _ = client.exec_command(command)
    return stdout


def start_mcperf():
    memcached_info = get_pod_info("memcached")
    memcached_ip = memcached_info["IP"]
    client_agent_a_IP, client_agent_b_IP, _ = get_client_ips(internal=True)

    terminate_mcperf()

    print(">> Starting mcperf on client-agent-a")
    execute_ssh_command(
        client_a, "cd memcache-perf-dynamic; ./mcperf -T 2 -A &")

    print(">> Starting mcperf on client-agent-b")
    execute_ssh_command(
        client_b, "cd memcache-perf-dynamic; ./mcperf -T 4 -A &")

    print(">> Starting mcperf on client-measure")
    client_measure_command = f"cd memcache-perf-dynamic; ./mcperf -s {memcached_ip} --loadonly; ./mcperf -s {memcached_ip} -a {client_agent_a_IP} -a {client_agent_b_IP} --noload -T 6 -C 4 -D 4 -Q 1000 -c 4 -t 10 --scan 30000:30500:5"
    stdout = execute_ssh_command(
        client_measure, client_measure_command)
    return stdout


def terminate_mcperf():
    print(">> Terminating mcperf on client-agent-a")
    execute_ssh_command(client_a, "pkill mcperf")

    print(">> Terminating mcperf on client-agent-b")
    execute_ssh_command(client_b, "pkill mcperf")

    print(">> Terminating mcperf on client-measure")
    execute_ssh_command(client_measure, "pkill mcperf")


def create_memcached_service():
    print(">> Creating memcached service")
    if does_service_exist("memcached"):
        print(">> Memcached service already exists")
        return
    subprocess.run(
        [
            "kubectl",
            "expose",
            "pod",
            "memcached",
            "--port=11211",
            "--name=memcached-11211",
            "--type=LoadBalancer",
            "--protocol=TCP"
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    while not does_service_exist("memcached"):
        print(
            ">> Waiting for memcached service to be created")
        sleep(10)
    print(">> Memcached service created")


def run_part_3(args):
    print(">> Running part 3")
    schedule_dir = f"{args.cca_directory}/schedules/{args.schedule}"

    print(">> Deleting all jobs")
    subprocess.run(
        ["kubectl", "delete", "jobs", "--all"], check=True, stdout=subprocess.PIPE
    )

    if args.delete_pods:
        print(">> Deleting all pods")
        subprocess.run(
            ["kubectl", "delete", "pods", "--all"], check=True, stdout=subprocess.PIPE
        )
    else:
        print(">> Skipping pod deletion")

    memcached_running = False

    json_file_path = f"{schedule_dir}/{args.schedule}.json"

    with open(json_file_path, "r") as j:
        schedule = json.loads(j.read())

    num_jobs_done = 0

    run_cursor = {}
    for node_id, node_schedule in enumerate(schedule):
        current_cursor = {}
        for run_id, run in enumerate(node_schedule['runs']):
            current_cursor[run_id] = 0
        run_cursor[node_id] = current_cursor

    N_MEMCACHED_JOBS = 1
    n_jobs = sum([len(node_schedule['runs']) for node_schedule in schedule])
    n_batch_jobs = n_jobs - N_MEMCACHED_JOBS
    dispatched_jobs = []
    mcperf_stdout = None

    while num_jobs_done != n_batch_jobs:
        print(f">> {num_jobs_done} / {n_batch_jobs} jobs done")
        print()
        for node_id, node_schedule in enumerate(schedule):
            running_jobs = []
            for run_id, run in enumerate(node_schedule['runs']):

                idx = run_cursor[node_id][run_id]
                finished_run = idx >= len(run)
                if finished_run:
                    continue
                job = run[idx]

                if does_pod_exist(job):
                    info = get_pod_info(job)

                    if info["STATUS"] == "Running":
                        if job == 'memcached' and not memcached_running:
                            memcached_running = True
                            mcperf_stdout = start_mcperf()

                        running_jobs.append(job)

                    elif info["STATUS"] == "Completed":
                        print(f">> Completed job {job} on node {node_id}")
                        run_cursor[node_id][run_id] = idx + 1
                        job = run[idx]
                        num_jobs_done += 1

                    elif info["STATUS"] == "Failed":
                        num_jobs_done += 1
                        print(f">> Job {info['NAME']} failed")

                elif job not in dispatched_jobs and (not memcached_running or job == 'memcached' or memcached_running):
                    print(f">> Starting job {job} on node {node_id}")
                    job_file = f"{schedule_dir}/{job}.yaml"
                    subprocess.run(['kubectl', 'create', '-f', job_file],
                                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    dispatched_jobs.append(job)

            print(f">> Node {node_id}: {running_jobs}")

    print(">> All batch jobs completed")

    terminate_mcperf()
    save_mcperf_logs(mcperf_stdout, schedule_dir)
    log_job_time(schedule, schedule_dir)

    print(">> Finished part 3")


def save_mcperf_logs(mcperf_stdout, schedule_dir):
    if mcperf_stdout is None:
        raise RuntimeError("mcperf stdout is None")

    print(">> Reading mcperf logs")
    output = mcperf_stdout.read().decode("utf-8")

    txt_filename = f"{schedule_dir}/mcperf-output.txt"

    print(f">> Saving mcperf logs to {txt_filename}")
    with open(txt_filename, 'w') as f:
        f.write(output)


def is_cluster_deployed(cluster_name):
    try:
        result = subprocess.run(
            ["kops", "validate", "cluster", cluster_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def parse_result_output(result):
    output = result.stdout.decode("utf-8")
    lines = [line.strip() for line in output.split("\n")]
    header = lines[0].split()
    data = []
    for line in lines[1:]:
        row = re.split(r"\s{2,}", line)
        data.append(dict(zip(header, row)))
    return data[:-1]


def does_cluster_exist(cluster_name):
    try:
        subprocess.run(
            ["kops", "get", "clusters", cluster_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def does_pod_exist(pod_name_beginning):
    try:
        return get_pod_info(pod_name_beginning) is not None
    except ValueError:
        return False


def does_service_exist(service_name_beginning):
    try:
        return get_services_info(service_name_beginning) is not None
    except ValueError:
        return False


def get_ressource_info(ressource_type, ressource_name_beginning):
    result = subprocess.run(
        ["kubectl", "get", ressource_type, "-o", "wide", "--show-labels"],
        check=True,
        stdout=subprocess.PIPE,
    )
    data = parse_result_output(result)
    ressource_infos = (ressource for ressource in data if ressource["NAME"].startswith(
        ressource_name_beginning))
    first_matching_ressource = next(ressource_infos, None)
    if first_matching_ressource is None:
        raise ValueError(
            f"No matching ressource found for name beginning with {ressource_name_beginning}")
    return first_matching_ressource


def get_node_info(node_name_beginning):
    return get_ressource_info("nodes", node_name_beginning)


def get_services_info(service_name_beginning):
    return get_ressource_info("services", service_name_beginning)


def get_pod_info(pod_name_beginning):
    return get_ressource_info("pods", pod_name_beginning)


def parse_execution_times(result):
    output = result.stdout.decode("utf-8")
    lines = [line.strip() for line in output.split("\n")]
    real, user, sys = None, None, None
    for line in lines:
        if line.startswith("real"):
            real = line.split()[1]
        elif line.startswith("user"):
            user = line.split()[1]
        elif line.startswith("sys"):
            sys = line.split()[1]
    return get_total_ms(real), get_total_ms(user), get_total_ms(sys)


def get_total_ms(execution_time):
    mins, seconds_fraction = execution_time.split("m")
    seconds, fraction = seconds_fraction.split(".")
    total_seconds = int(mins) * 60 + int(seconds) + \
        float(fraction.rstrip("s")) / 1000
    total_ms = int(total_seconds * 1000)
    return total_ms


def create_csv_file(args):
    if args.task == "3":
        header = (
            "timestamp,cluster_name,node,job,real_ms,user_ms,sys_ms\n"
        )
    else:
        raise ValueError(f"Invalid task: {args.task}")
    if not os.path.exists(args.output):
        with open(args.output, "w") as f:
            f.write(header)


def create_part3_yaml(args):
    if os.path.exists(args.userYaml):
        return

    REPLACE_MAP = {
        '<user>': args.user,
    }

    with fileinput.FileInput(args.sourceYaml) as file, open(args.userYaml, 'w') as output_file:
        for line in file:
            for placeholder, substitution in REPLACE_MAP.items():
                line = line.replace(placeholder, substitution)
            output_file.write(line)

    print(f">> File '{args.userYaml}' has been created.")


def delete_part3_yaml(args):
    if os.path.exists(args.userYaml):
        os.remove(args.userYaml)
        print(f">> File '{args.userYaml}' has been removed.")


def append_result_to_csv(
    args, benchmark, real, user, sys, interference=None, n_threads=None
):
    now = datetime.now()
    if args.task == "2a":
        line = f"{now},{args.cluster_name},{benchmark},{interference},{real},{user},{sys}\n"
    elif args.task == "2b":
        line = (
            f"{now},{args.cluster_name},{benchmark},{n_threads},{real},{user},{sys}\n"
        )
    else:
        raise ValueError(f"Invalid task: {args.task}")
    with open(args.output, "a") as f:
        f.write(line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run part 3 of the project",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-u",
        "--user",
        type=str,
        help="ETHZ user id",
        required=True,
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "-t",
        "--task",
        type=str,
        choices=["3"],
        help="Task to run",
        required=True,
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "-p",
        "--project",
        type=str,
        default="cca-eth-2023-group-29",
        help="GCP project id",
    )
    parser.add_argument(
        "-d",
        "--cca-directory",
        type=str,
        default="cloud-comp-arch-project",
        help="Directory containing the project files",
    )
    parser.add_argument(
        "--ssh-key-file",
        type=str,
        default="C:/Users/User/.ssh/cloud-computing",
        help="The path to the ssh key for cloud computing",
    )

    parser.add_argument("-c", "--cluster-name", type=str,
                        default="part3.k8s.local")
    parser.add_argument(
        "-k",
        "--keep-alive",
        action="store_true",
        help="Keep cluster alive after running the task",
    )
    parser.add_argument(
        "-w",
        "--wait-timeout",
        type=int,
        help="Timeout for running benchmarks in seconds",
        default=600,
    )
    parser.add_argument(
        "-s",
        "--schedule",
        type=str,
        choices=["scheduleA", "scheduleB", "scheduleC", "scheduleD"],
        help="Schedule to run",
        default="scheduleA",
    )
    parser.add_argument(
        "--deploy-cluster",
        action="store_true",
        help="Deploy the cluster",
        default=True
    )
    parser.add_argument(
        "--compile-mcperf",
        action="store_true",
        help="Compile mcperf on the client and measure nodes",
        default=True
    )
    parser.add_argument(
        "--delete-pods",
        action="store_true",
        help="Delete pods before running the benchmark",
        default=False
    )

    args = parser.parse_args()
    args.cluster_name = f"part{args.task}.k8s.local"
    args.output = f"results-{args.task}.csv"
    args.sourceYaml = f"{args.cca_directory}/part{args.task}.yaml"
    args.userYaml = f"{args.cca_directory}/part{args.task}-{args.user}.yaml"
    if not os.path.isdir(parser.parse_args().cca_directory):
        print(f"Directory {parser.parse_args().cca_directory} does not exist")
        sys.exit(1)
    if args.task == "3":
        create_part3_yaml(args)
        spin_up_cluster(args)
        run_part_3(args)
        tear_down_cluster(args)
        delete_part3_yaml(args)
    else:
        raise ValueError(f"Unknown task {args.task}")


# python CCA-23/run-part-3.py --cca-directory CCA-23  --user mertugrul --task 3
