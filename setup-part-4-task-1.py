import os
import subprocess
import sys
import argparse
import re
from datetime import datetime
import json
import get_time
import paramiko
import time
import pandas as pd
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


client_agent = paramiko.SSHClient()
client_measure = paramiko.SSHClient()
memcache_server = paramiko.SSHClient()

memcache_server_name = ""

client_agent_info = memcache_server_info = client_measure_info = {}

# this is for compiling mcperf
client_command = "sudo sh -c 'echo deb-src http://europe-west3.gce.archive.ubuntu.com/ubuntu/ bionic main restricted >> /etc/apt/sources.list' "
client_command += "sudo apt-get update \n"
client_command += "sudo apt-get install libevent-dev libzmq3-dev git make g++ --yes \n"
client_command += "sudo apt-get build-dep memcached --yes \n"
client_command += "git clone https://github.com/eth-easl/memcache-perf-dynamic.git \n"
client_command += "cd memcache-perf-dynamic \n"
client_command += "make"

# this is to load memcached on the server, then make the necessary changes
memcache_command = "sudo apt update \n"
memcache_command += "sudo apt install -y memcached libmemcached-tools \n"
memcache_command += "sudo systemctl status memcached \n"

memcache_command += "sudo sed -i '23s/.*/-m 1024/' /etc/memcached.conf \n"


# done for part 4 task 1
def connect_mcperfs():
    print(">>> Setting up SSH connection to compile mcperf")

    client_agent_info = get_node_info("client-agent")
    client_agent_name = client_agent_info["NAME"]
    client_agent_IP = client_agent_info["EXTERNAL-IP"]

    client_measure_info = get_node_info("client-measure")
    client_measure_name = client_measure_info["NAME"]
    client_measure_IP = client_measure_info["EXTERNAL-IP"]

    memcache_server_info = get_node_info("memcache-server")
    memcache_server_name = memcache_server_info["NAME"]
    memcache_server_IP = memcache_server_info["EXTERNAL-IP"]
    memcache_server_internal_IP = memcache_server_info["INTERNAL-IP"]

    # Connecting to client A
    client_agent.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )  # no known_hosts error
    client_agent.connect(client_agent_IP, 22, username="ubuntu")  # no passwd needed

    # Connecting to client B
    memcache_server.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )  # no known_hosts error
    memcache_server.connect(
        memcache_server_IP, 22, username="ubuntu"
    )  # no passwd needed

    # Connecting to client measure
    client_measure.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )  # no known_hosts error
    client_measure.connect(client_measure_IP, 22, username="ubuntu")  # no passwd needed

    # add internal IP
    memcache_command += (
        f"sudo sed -i '35s/.*/-l {memcache_server_internal_IP}/' /etc/memcached.conf"
    )

    # TODO: change number of threads for memcached here
    memcached_threads = 2
    memcache_command += "sudo echo ' ' >> /etc/memcached.conf"
    #memcache_command += (
    #    "sudo echo '# specifying the number of threads' | sudo tee -a /etc/memcached.conf"
    #)
    memcache_command += (
        f"sudo echo '-t {memcached_threads}' | sudo tee -a /etc/memcached.conf"
    )
    memcache_command += "sudo systemctl restart memcached"


def spin_up_cluster(args, create_cluster=True, setup_mcperf=True):
    if create_cluster:
        print(f">> Setting up part {args.task}")
        os.environ["KOPS_STATE_STORE"] = f"gs://{args.project}-{args.user}"
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


    connect_mcperfs()

    if setup_mcperf:
        (stdin, stdout, stderr) = client_agent.exec_command(client_command)
        stderr = stdout.read()
        print("Setup log for client agent: ", client_command, stderr)

        (stdin, stdout, stderr) = memcache_server.exec_command(memcache_command)
        stderr = stdout.read()
        print("Setup log for memcached server: ", memcache_command, stderr)

        (stdin, stdout, stderr) = client_measure.exec_command(client_command)
        stderr = stdout.read()
        print("Setup log for client measure: ", client_command, stderr)


    print(f">> mcperf and memcached setup complete, copying benchmarking script to the memcached vm")
    
    memcache_server_name = memcache_server_info["NAME"]
    #f"gcloud compute scp --scp-flag=-r part-4-vm-scripts/ ubuntu@{memcache_server_name}:/home/ubuntu/ --zone europe-west3-a"

    result = subprocess.run(
        f"gcloud compute scp --scp-flag=-r part-4-vm-scripts/ ubuntu@{memcache_server_name}:/home/ubuntu/ --zone europe-west3-a".split(" "),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    print(f">> Finished setting up part {args.task}")


def run_part_4(args):

    memcached_server_ip = memcache_server_info["INTERNAL-IP"]

    # Num cores = 1, beginning CPU measurement script, measuring fro 20 seconds to let mcperf start and end within measruement period

    print(">> Creating remote log folder")

    # Creating output folder
    run_benchmark_cmd = "sudo mkdir /home/ubuntu/part-4-logs"
    (stdin, stdout, stderr) = memcache_server.exec_command(run_benchmark_cmd)
    print(stdout)

    # ------------ Running for 1 core ---------------

    run_benchmark(memcached_server_ip,cores=1)

    sleep(5)

    # ------------ Running for 2 cores ---------------

    run_benchmark(memcached_server_ip,cores=2)

    #print(f">> Real: {real_ms} ms, User: {user_ms} ms, Sys: {sys_ms} ms")
    #print(">> Appending benchmark results to csv file")
    #append_result_to_csv(args, real_ms, user_ms, sys_ms, n_threads, n_cores)


def run_benchmark(memcached_server_ip, cores=1):
    print(f">> Running benchmarking script on memcached vm with {cores} cores")

    run_benchmark_cmd = f"sudo python3 /home/ubuntu/part-4-vm-scripts/cpu-benchmark.py --cores {cores} --time 20 --log-path /home/ubuntu/part-4-logs"
    (stdin, stdout, stderr) = memcache_server.exec_command(run_benchmark_cmd)

    print(">> Starting mcperf agent and measure")
    stdout_mcperf = start_mcperf(memcached_server_ip)

    # waiting for mcperf to complete
    sleep(11)

    output_mcperf = stdout_mcperf.read()
    output_cpu = stdout.read()

    print(">> Saving benchmark results to text file")
    save_memcached_logs(output_cpu)

    print(f">> Collecting output from mcperf measure")
    save_mcperf_logs(output_mcperf)

    # attempting to copy remote log folder to local file system as a n alterantive logging method

    result = subprocess.run(
        f"gcloud compute scp --scp-flag=-r ubuntu@{memcache_server_name}:/home/ubuntu/part-4-logs ./ --zone europe-west3-a".split(" "),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    



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


# executes the necessary mcperf methods on the client_agent and memcache_server
def start_mcperf(memcached_ip):
    client_agent_name = client_agent["NAME"]
    client_agent_IP = client_agent["INTERNAL-IP"]

    memcache_server = memcache_server_info["NAME"]
    memcache_server_IP = memcache_server_info["INTERNAL-IP"]

    client_measure_name = client_measure_info["NAME"]
    client_measure_IP = client_measure_info["INTERNAL-IP"]

    (stdin, stdout, stderr) = client_agent.exec_command("./mcperf -T 16 -A")
    cmd_output = stdout.read()

    # ========== THIS IS FOR THE MAIN PART OF 4 ===============
    # client_measure_command = f"./mcperf -s {memcached_ip} --loadonly /n"
    # +f"./mcperf -s {memcached_ip} -a {client_agent_IP} "
    # +"noload -T 16 -C 4 -D 4 -Q 1000 -c 4 -t 10"
    # +"--qps_interval 2 --qps_min 5000 --qps_max 100000"

    client_measure_command_benchmarking = f"./mcperf -s {memcached_ip} --loadonly /n"
    +f"./mcperf -s {memcached_ip} -a {client_agent_IP} "
    +"--noload -T 16 -C 4 -D 4 -Q 1000 -c 4 -t 5"
    +"--scan 5000:125000:5000"

    (stdin, stdout, stderr) = client_measure.exec_command(client_measure_command_benchmarking)
    return stdout



# timestamp,cluster_name,real_ms,user_ms,sys_ms,throughput
def append_result_to_csv(args, real, user, sys, n_threads, n_cores):
    now = datetime.now()
    line = f"{now},{args.cluster_name},{real},{user},{sys},20"

    title = f"memcached_{n_threads}threads_{n_cores}cores.csv"
    with open(title, "a") as f:
        f.write(line)

# writing full mcperf log output
def save_mcperf_logs(stdout_mcperf):
    output = stdout_mcperf.decode("utf-8")
    print(output)
    print(">> Saving to txt file")

    txt_filename = f"mcperf-part{args.task}.txt"

    with open(txt_filename, "w") as f:
        f.write(output)

def save_memcached_logs(stdout_mcperf, cores=2, threads=2):
    output = stdout_mcperf.decode("utf-8")
    #print(output)
    print(">> Saving memcached logs to txt file")

    txt_filename = f"memcached-cores{cores}-threads{threads}.txt"

    with open(txt_filename, "w") as f:
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
        header = "timestamp,cluster_name,node,job,real_ms,user_ms,sys_ms\n"
    else:
        raise ValueError(f"Invalid task: {args.task}")
    if not os.path.exists(args.output):
        with open(args.output, "w") as f:
            f.write(header)


def create_part4_yaml(args):
    import fileinput

    if os.path.exists(args.userYaml):
        return

    REPLACE_MAP = {
        "<user>": args.user,
    }

    # Define the variable to replace '<user>'
    replacement_variable = "John Doe"

    # Copy and rewrite the file
    with fileinput.FileInput(args.sourceYaml) as file, open(
        args.userYaml, "w"
    ) as output_file:
        for line in file:
            for placeholder, substitution in REPLACE_MAP.items():
                line = line.replace(placeholder, substitution)
            output_file.write(line)

    print(f"File '{args.userYaml}' has been created.")


def delete_part4_yaml(args):
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
        description="Run part 4, task 1 of the project",
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
        choices=["4"],
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

    parser.add_argument("-c", "--cluster-name", type=str, default="part4.k8s.local")
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

    args = parser.parse_args()
    args.cluster_name = f"part{args.task}.k8s.local"
    args.output = f"results-{args.task}.csv"
    args.sourceYaml = f"{args.cca_directory}/part{args.task}.yaml"
    args.userYaml = f"{args.cca_directory}/part{args.task}-{args.user}.yaml"
    if not os.path.isdir(parser.parse_args().cca_directory):
        print(f"Directory {parser.parse_args().cca_directory} does not exist")
        sys.exit(1)
    if args.task == "4":
        create_part4_yaml(args)
        spin_up_cluster(args)
        run_part_4(args)
        tear_down_cluster(args)
        delete_part4_yaml(args)
    else:
        raise ValueError(f"Unknown task {args.task}")


# python CCA-23/run-part-3.py --cca-directory CCA-23  --user mertugrul --task 3
