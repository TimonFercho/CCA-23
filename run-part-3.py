import os
import subprocess
import sys
import argparse
import re
from datetime import datetime
import json
import get_time
import paramiko

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

#client_a = client_b = client_measure = None
client_agent_a_info = client_agent_b_info = client_measure_info = {}


client_command = "sudo sh -c 'echo deb-src http://europe-west3.gce.archive.ubuntu.com/ubuntu/ bionic main restricted >> /etc/apt/sources.list' "
client_command += "sudo apt-get update \n" 
client_command += "sudo apt-get install libevent-dev libzmq3-dev git make g++ --yes \n"
client_command += "sudo apt-get build-dep memcached --yes \n"
client_command += "git clone https://github.com/eth-easl/memcache-perf-dynamic.git \n"
client_command += "cd memcache-perf-dynamic \n"
client_command += "make"



def connect_mcperfs():

    print(">>> Setting up SSH connection to compile mcperf")

    client_agent_a_info= get_node_info("client-agent-a")
    client_agent_a_name=client_agent_a_info["NAME"]
    client_agent_a_IP=client_agent_a_info["EXTERNAL-IP"]

    client_agent_b_info= get_node_info("client-agent-b")
    client_agent_b_name=client_agent_b_info["NAME"]
    client_agent_b_IP=client_agent_b_info["EXTERNAL-IP"]
    
    client_measure_info= get_node_info("client-measure")
    client_measure_name=client_measure_info["NAME"]
    client_measure_IP=client_measure_info["EXTERNAL-IP"]

    # Connecting to client A
    #client_a.load_system_host_keys()
    client_a.set_missing_host_key_policy(paramiko.AutoAddPolicy()) # no known_hosts error
    client_a.connect(client_agent_a_IP, 22, username="ubuntu") # no passwd needed

    # Connecting to client B
    #client_b.load_system_host_keys()
    client_b.set_missing_host_key_policy(paramiko.AutoAddPolicy()) # no known_hosts error
    client_b.connect(client_agent_b_IP, 22, username="ubuntu") # no passwd needed


    # Connecting to client measure
    #client_measure.load_system_host_keys()
    client_measure.set_missing_host_key_policy(paramiko.AutoAddPolicy()) # no known_hosts error
    client_measure.connect(client_measure_IP, 22, username="ubuntu") # no passwd needed


def spin_up_cluster(args, create_cluster=True, setup_mcperf=True):

    if create_cluster:
        print(f">> Setting up part {args.task}")
        os.environ["KOPS_STATE_STORE"] =  f"gs://{args.project}-{args.user}"
        os.environ["PROJECT"] = args.project

        print(">> Creating cluster")
        if does_cluster_exist(args.cluster_name):
            print(">> Cluster already exists")
        else:
            subprocess.run(
                ["kops", "create", "-f", f"{args.cca_directory}/part{args.task}.yaml"],
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
            subprocess.run(["kops", "validate", "cluster", "--wait", "10m"], check=True)
            print(">> Cluster deployed successfully")

    # Setup for mcperf clients

    #TODO: validate the correctess of this approach 
    # - what will the username be? can we test whether this works without running everything?

    connect_mcperfs()

    if setup_mcperf:

        (stdin, stdout, stderr) = client_a.exec_command(client_command)
        stderr = stdout.read()
        print('Setup log for client A: ', client_command, stderr)

        (stdin, stdout, stderr) = client_b.exec_command(client_command)
        stderr = stdout.read()
        print('Setup log for client B: ', client_command, stderr)

        (stdin, stdout, stderr) = client_measure.exec_command(client_command)
        stderr = stdout.read()
        print('Setup log for client measure: ', client_command, stderr)


    #print(">> Labeling parsec server node")
    #parsec_node_name = get_node_info("parsec-server")["NAME"]
    #subprocess.run(
    #    ["kubectl", "label", "nodes", parsec_node_name, "cca-project-nodetype=parsec"],
    #    check=True,
    #    stdout=subprocess.PIPE,
    #    stderr=subprocess.PIPE,
    #)
    #parsec_node = get_node_info("parsec-server")
    #parsec_node_labels = get_node_info("parsec-server")["LABELS"]
    #if not "cca-project-nodetype=parsec" in parsec_node_labels:
    #    print(">> Failed to add label")
    #    return



    print(f">> Finished setting up part {args.task}")


def run_benchmark_with_threads(args, benchmark_short, n_threads):
    benchmark = f"parsec-{benchmark_short}"
    print(f">> Running benchmark {benchmark} with {n_threads} threads")

    print(">> Creating csv file for results")
    create_csv_file(args)

    print(">> Creating modified config file")
    create_modified_config_file(args, benchmark, n_threads)

    print(">> Creating benchmark")
    subprocess.run(
        [
            "kubectl",
            "create",
            "-f",
            f"{args.cca_directory}/parsec-benchmarks/part2b/{benchmark}_{n_threads}.yaml",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if not does_pod_exist(benchmark):
        print("!! Benchmark creation failed")
        return

    print(">> Waiting for benchmark job to complete")
    subprocess.run(
        [
            "kubectl",
            "wait",
            "--for=condition=complete",
            "job",
            benchmark,
            f"--timeout={args.wait_timeout}s",
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    print(">> Benchmark completed")

    print(">> Collecting benchmark results")
    benchmark_pod = get_pod_info(benchmark)
    pod_name = benchmark_pod["NAME"]
    result = subprocess.run(
        ["kubectl", "logs", pod_name], check=True, stdout=subprocess.PIPE
    )
    real_ms, user_ms, sys_ms = parse_execution_times(result)

    print(f">> Real: {real_ms} ms, User: {user_ms} ms, Sys: {sys_ms} ms")

    print(">> Appending benchmark results to csv file")
    append_result_to_csv(
        args, benchmark_short, real_ms, user_ms, sys_ms, n_threads=n_threads
    )

    print(">> Deleting all benchmarking jobs")
    subprocess.run(
        ["kubectl", "delete", "jobs", "--all"], check=True, stdout=subprocess.PIPE
    )

    print(">> Deleting modified config file")
    subprocess.run(
        [
            "rm",
            f"{args.cca_directory}/parsec-benchmarks/part2b/{benchmark}_{n_threads}.yaml",
        ],
        check=True,
        stdout=subprocess.PIPE,
    )


def log_job_time():
 
    subprocess.run(
        ["kubectl", "get", "pods", "-o", "json", ">", "results.json"]
    )

    get_time.get_time("results.json")
    



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



def start_mcperf(memcached_ip):
    client_agent_a_name=client_agent_a_info["NAME"]
    client_agent_a_IP=client_agent_a_info["INTERNAL-IP"]

    client_agent_b_name=client_agent_b_info["NAME"]
    client_agent_b_IP=client_agent_b_info["INTERNAL-IP"]

    client_measure_name=client_measure_info["NAME"]
    client_measure_IP=client_measure_info["INTERNAL-IP"]

    (stdin, stdout, stderr) = client_a.exec_command("./mcperf -T 2 -A")
    cmd_output = stdout.read()
    #print('client A begins mcperf: ', client_command, cmd_output)

    (stdin, stdout, stderr) = client_b.exec_command("./mcperf -T 4 -A")
    cmd_output = stdout.read()
    #print('client B begins mcperf: ', client_command, cmd_output)  

    client_measure_command = f"./mcperf -s {memcached_ip} --loadonly /n"
    +  f"./mcperf -s {memcached_ip} -a {client_agent_a_IP} -a {client_agent_b_IP} "
    +   "--noload -T 6 -C 4 -D 4 -Q 1000 -c 4 -t 10 --scan 30000:30500:5"

    (stdin, stdout, stderr) = client_measure.exec_command(client_measure_command)
    #cmd_output = stdout.read()
    #print('client measure begins mcperf: ', client_measure_command, cmd_output) 

    # return client measure stdout for later logging to file
    return stdout



def run_part_3(args):
    print(">> Running part 3")
    schedule_dir = f"{args.cca_directory}/schedules/{args.schedule}"

    stdout_mcperf = None

    json_file_path = f"{schedule_dir}/{args.schedule}.json"

    with open(json_file_path, "r") as j:
        schedule = json.loads(j.read())

    num_jobs_done = 0

    # instead of popping from job lists, we update an external cursor 
    # to avoid cahnging structures while iterating through them
    run_cursor = {}
    for node_id, node_schedule in enumerate(schedule):
        current_cursor = {}
        for run_id, run in enumerate(node_schedule['runs']):
            current_cursor[run_id] = 0
        run_cursor[node_id] = current_cursor

    N_JOBS = 8
    dispatched_jobs = []

    while num_jobs_done != N_JOBS:
        for node_id, node_schedule in enumerate(schedule):
            for run_id, run in enumerate(node_schedule['runs']):

                idx = run_cursor[node_id][run_id]
                finished_run = idx >= len(run)

                if finished_run:
                    continue

                job = run[idx]

                if dispatched_jobs and does_pod_exist(job):
                    info = get_pod_info(job)
                    is_running = (
                        info["STATUS"] == "Running"
                    ) 
                    if is_running:
                        print(f">> Job {job} on node {node_id} is running")
                        continue

                    is_complete = (
                        info["STATUS"] == "Completed"
                    ) 

                    if is_complete:
                        print(f">> Job {job} on node {node_id} succeeded")
                        run_cursor[node_id][run_id] = idx + 1
                        job = run[idx]

                        num_jobs_done += 1

                    job_name = info["NAME"]
                    if info["STATUS"] == "Failed":
                        num_jobs_done += 1
                        print(f">> Job {job_name} failed")

                elif job not in dispatched_jobs:
                    print(f">> Starting job {job} on node {node_id}")
                    print(f">> kubectl create -f {args.cca_directory}/{schedule_dir}/{job}.yaml")
                    subprocess.run(['kubectl', 'create', '-f', f'{args.cca_directory}/{schedule_dir}/{job}.yaml'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    dispatched_jobs.append(job)
                else:
                    print(f">> Job {job} is not alive (yet)")

                    # TODO: handle this somewhere else when we know memcached is running
                    # if job == "memcache-t1-cpuset":
                    #     # retrieving IP for memcached and starting mcperfs
                    #     info = get_pod_info(job)
                    #     stdout_mcperf = start_mcperf(info["IP"])

        # TODO: introduce some delay?
    
    if stdout_mcperf is None:
        # raise error
        print("No stdout for mcperf present")
    else:
        print(">> Collecting mcperf results")
        save_mcperf_logs(stdout_mcperf)

    log_job_time()
    print(">> Parsec job logs Saved")

    #print(">> Collecting mcperf results")
    #get_mcperf_logs(args)


# writing full mcperf log output
def save_mcperf_logs(stdout_mcperf):

    output = stdout_mcperf.decode("utf-8") 
    print(output)
    print(">> Saving to txt file")

    txt_filename = f"mcperf-part{args.task}.txt"

    with open(txt_filename, 'w') as f:
        f.write(output)



def does_cluster_exist(cluster_name):
    try:
        result = subprocess.run(
            ["kops", "get", "clusters", cluster_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return True
    except subprocess.CalledProcessError:
        return False


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


def does_pod_exist(pod_name_beginning):
    return get_pod_info(pod_name_beginning) is not None


def get_node_info(node_name_beginning):
    result = subprocess.run(
        ["kubectl", "get", "nodes", "-o", "wide", "--show-labels"],
        check=True,
        stdout=subprocess.PIPE,
    )
    data = parse_result_output(result)
    node_info = [node for node in data if node["NAME"].startswith(node_name_beginning)][
        0
    ]
    return node_info


def get_pod_info(pod_name_beginning):
    result = subprocess.run(
        ["kubectl", "get", "pods", "-o", "wide", "--show-labels"],
        check=True,
        stdout=subprocess.PIPE,
    )
    data = parse_result_output(result)
    pod_info = [pod for pod in data if pod["NAME"].startswith(pod_name_beginning)]
    if len(pod_info) == 0:
        return None
    return pod_info[0]


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
    total_seconds = int(mins) * 60 + int(seconds) + float(fraction.rstrip("s")) / 1000
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
    import fileinput

    if os.path.exists(args.userYaml):
        return

    REPLACE_MAP = {
        '<user>': args.user,
    }

    # Define the variable to replace '<user>'
    replacement_variable = 'John Doe'

    # Copy and rewrite the file
    with fileinput.FileInput(args.sourceYaml) as file, open(args.userYaml, 'w') as output_file:
        for line in file:
            for placeholder, substitution in REPLACE_MAP.items():
                line = line.replace(placeholder, substitution)
            output_file.write(line)

    print(f"File '{args.userYaml}' has been created.")

def delete_part3_yaml(args):
    if os.path.exists(args.userYaml):
        os.remove(args.userYaml)
        print(f"File '{args.userYaml}' has been removed.")

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

    parser.add_argument("-c", "--cluster-name", type=str, default="part3.k8s.local")
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
        choices=["scheduleA", "scheduleB"],
        help="Schedule to run",
        default="scheduleA",
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
        # spin_up_cluster(args)
        # run_part_3(args)
        # tear_down_cluster(args)
        delete_part3_yaml(args)
    else:
        raise ValueError(f"Unknown task {args.task}")
    

# python CCA-23/run-part-3.py --cca-directory CCA-23  --user mertugrul --task 3
