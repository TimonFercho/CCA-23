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


MEMCACHED_N_THREADS = 2


client_agent = paramiko.SSHClient()
client_measure = paramiko.SSHClient()
memcached_server = paramiko.SSHClient()

memcached_server_name = ""

client_agent_info = memcached_server_info = client_measure_info = {}


def connect_mcperfs(args):
    print(">> Setting up SSH connection to compile mcperf")

    client_agent_info = get_node_info("client-agent")
    client_agent_IP = client_agent_info["EXTERNAL-IP"]

    client_measure_info = get_node_info("client-measure")
    client_measure_IP = client_measure_info["EXTERNAL-IP"]

    memcached_server_info = get_node_info("memcache-server")
    memcached_server_IP = memcached_server_info["EXTERNAL-IP"]

    client_agent.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )
    client_agent.connect(client_agent_IP, 22,
                         username="ubuntu",key_filename=args.ssh_key_file)

    memcached_server.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )
    memcached_server.connect(
        memcached_server_IP, 22, username="ubuntu",key_filename=args.ssh_key_file
    )
    client_measure.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )
    client_measure.connect(client_measure_IP, 22,
                           username="ubuntu",key_filename=args.ssh_key_file)


def setup_memcached():
    memcached_server_info = get_node_info("memcache-server")
    memcached_server_internal_IP = memcached_server_info["INTERNAL-IP"]

    install_and_configure_memcached_cmd = "sudo apt update \n"
    install_and_configure_memcached_cmd += "sudo apt install -y memcached libmemcached-tools \n"
    install_and_configure_memcached_cmd += "sudo systemctl status memcached \n"
    install_and_configure_memcached_cmd += "sudo sed -i '23s/.*/-m 1024/' /etc/memcached.conf \n"
    install_and_configure_memcached_cmd += (
        f"sudo sed -i '35s/.*/-l {memcached_server_internal_IP}/' /etc/memcached.conf \n"
    )

    install_and_configure_memcached_cmd += (
        f"echo '-t {MEMCACHED_N_THREADS}' | sudo tee -a /etc/memcached.conf \n"
    )
    install_and_configure_memcached_cmd += "sudo systemctl restart memcached \n"
    install_and_configure_memcached_cmd += "sudo systemctl status memcached"

    (stdin, stdout, stderr) = memcached_server.exec_command(
        install_and_configure_memcached_cmd)
    # print("Setup log for memcached server: ",
    #   install_and_configure_memcached_cmd, stdout.read(), stderr.read())


def setup_mcperf():

    client_command = "sudo sh -c 'echo deb-src http://europe-west3.gce.archive.ubuntu.com/ubuntu/ bionic main restricted >> /etc/apt/sources.list' \n"
    client_command += "sudo apt-get update \n"
    client_command += "sudo apt-get install libevent-dev libzmq3-dev git make g++ --yes \n"
    client_command += "sudo apt-get build-dep memcached --yes \n"
    client_command += "git clone https://github.com/eth-easl/memcache-perf-dynamic.git \n"
    client_command += "cd memcache-perf-dynamic \n"
    client_command += "make"

    print(">> Compiling mcperf")
    # print(">> Command: ", client_command)
    (stdin, stdout, stderr) = client_agent.exec_command(client_command)
    client_agent_stdout = stdout.read()
    client_agent_stderr = stderr.read()
    print(
        f">> Setup log for client agent:\n{client_agent_stdout} \n\n {client_agent_stderr}")

    (stdin, stdout, stderr) = client_measure.exec_command(client_command)
    client_measure_stdout = stdout.read()
    client_measure_stderr = stderr.read()
    print(
        f">> Setup log for client measure:\n{client_measure_stdout} \n\n {client_measure_stderr}")


def terminate_mcperf():
    print(">> Terminating mcperf on client-measure")
    client_measure.exec_command("pkill -TERM mcperf")

    print(">> Terminating mcperf on client-agent")
    client_agent.exec_command("pkill -TERM mcperf")


def spin_up_cluster(args):
    print(f">> Setting up part {args.task}")
    os.environ["KOPS_STATE_STORE"] = f"gs://{args.project}-{args.user}"
    os.environ["PROJECT"] = args.project

    print(">> Creating cluster")
    if does_cluster_exist(args.cluster_name):
        print(">> Cluster already exists")
    else:
        subprocess.run(
            ["kops", "create", "-f",
                f"{args.cca_directory}/part{args.task}-{args.user}.yaml"],
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


def run_part_4(args, setup=True, copy_files=True):
    connect_mcperfs(args)
    
    if setup:
        setup_memcached()
        setup_mcperf()

    print(f">> mcperf and memcached setup complete, copying benchmarking script to the memcached vm")

    memcached_server_info = get_node_info("memcache-server")
    memcached_server_name = memcached_server_info["NAME"]

    print(f"gcloud compute scp --scp-flag=-r {args.cca_directory}/part-4-vm-scripts ubuntu@{memcached_server_name}:/home/ubuntu/ --zone europe-west3-a")

    if copy_files:
        result = subprocess.run(
            f"gcloud compute scp --scp-flag=-r {args.cca_directory}/part-4-vm-scripts ubuntu@{memcached_server_name}:/home/ubuntu/ --zone europe-west3-a".split(
                " "),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    print(f">> Finished setting up part {args.task}")

    # Num cores = 1, beginning CPU measurement script, measuring fro 20 seconds to let mcperf p and end within measruement period

    print(">> Creating remote log folder")
    run_benchmark_cmd = "mkdir /home/ubuntu/part-4-logs"
    (stdin, stdout, stderr) = memcached_server.exec_command(run_benchmark_cmd)
    print(stdout)
    print(stderr)

    print(">> Installing psutil")
    install_psutil_cmd = "sudo apt install python3-pip --yes"
    (stdin, stdout, stderr) = memcached_server.exec_command(install_psutil_cmd)
    print(stdout)
    print(stderr)

    install_psutil_cmd = "pip3 install psutil"
    (stdin, stdout, stderr) = memcached_server.exec_command(install_psutil_cmd)
    print(stdout)
    print(stderr)

    install_cmd = "pip3 install docker"
    (stdin, stdout, stderr) = memcached_server.exec_command(install_cmd)
    print(stdout)
    print(stderr)

    install_cmd = "sudo usermod -a -G docker User"
    (stdin, stdout, stderr) = memcached_server.exec_command(install_cmd)
    print(stdout)
    print(stderr)

    # ------------ Running for 1 core ---------------

    run_policy(cores=1)



def run_policy(cores=1):
    print(f">> Running part 4 scheduling ")

    print(">> Starting mcperf agent and measure")
    stdout_mcperf = start_mcperf()

    print(">> Starting scheduling")
    run_benchmark_cmd = f"sudo python3 /home/ubuntu/part-4-vm-scripts/controller.py --cores {cores} --log-path /home/ubuntu/part-4-logs"
    (stdin, schedule_stdout, stderr) = memcached_server.exec_command(run_benchmark_cmd)

    save_shedule_logs(schedule_stdout)
    save_shedule_logs(schedule_stdout, error=True)

    print(f">> Collecting output from mcperf measure")
    save_mcperf_logs(stdout_mcperf, cores)

    #print(">> Saving benchmark results to text file")
    #save_memcached_logs(mc_stdout, cores)

    # attempting to copy remote log folder to local file system as a n alterantive logging method

    # FIXME: this is not working
    # result = subprocess.run(
    #     f"{args.gcloud_bin_dir}/gcloud compute scp --scp-flag=-r ubuntu@{memcached_server_name}:/home/ubuntu/part-4-logs ./part-4/ --zone europe-west3-a".split(
    #         " "),
    #     check=True,
    #     stdout=subprocess.PIPE,
    #     stderr=subprocess.PIPE,
    # )
    # print(f">> scp output: {result.stdout}")
    # print(f">> scp error: {result.stderr}")


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


def start_mcperf():
    memcached_ip = get_node_info("memcache-server")["INTERNAL-IP"]
    client_agent_IP = get_node_info("client-agent")["INTERNAL-IP"]

    terminate_mcperf()

    print(">> Starting mcperf on client-agent")
    client_agent.exec_command("cd memcache-perf-dynamic; ./mcperf -T 16 -A")

    client_measure_command_benchmarking = (
        f"cd memcache-perf-dynamic;"
        f"./mcperf -s {memcached_ip} --loadonly;"
        + f"./mcperf -s {memcached_ip} -a {client_agent_IP} "
        + "--noload -T 16 -C 4 -D 4 -Q 1000 -c 4 -t 1800 "
        + "--qps_interval 10 --qps_min 5000 --qps_max 100000 --qps_seed 3274"
    )

    print(
        f">> Starting mcperf on client-measure with command: {client_measure_command_benchmarking}")
    _, mcperf_stdout, mcperf_stderr = client_measure.exec_command(
        client_measure_command_benchmarking)
    return mcperf_stdout


def save_memcached_logs(stdout, cores):
    output = stdout.read().decode("utf-8")
    print(">> Saving memcached logs to txt file")

    txt_filename = f"part-4/memcached_logs.txt"

    with open(txt_filename, "w") as f:
        f.write(output)

def save_shedule_logs(stdout, error=False):
    output = stdout.read().decode("utf-8")
    if error:
        print(">> Saving shedule error to txt file")
        txt_filename = f"part-4/schedule_errors.txt"
    else:
        print(">> Saving shedule logs to txt file")
        txt_filename = f"part-4/schedule_logs.txt"

    with open(txt_filename, "w") as f:
        f.write(output)


def save_mcperf_logs(mcperf_stdout, cores):
    if mcperf_stdout is None:
        raise RuntimeError("mcperf stdout is None")

    print(">> Reading mcperf logs")
    output = mcperf_stdout.read().decode("utf-8")

    txt_filename = f"part-4/mcperf-output.txt"

    print(f">> Saving mcperf logs to {txt_filename}")
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
        "<your-cloud-computing-architecture-gcp-project>": args.project,
        "<your-gs-bucket>": f"{args.project}-{args.user}"
    }

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

    parser.add_argument("-c", "--cluster-name", type=str,
                        default="part4.k8s.local")
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
        "--gcloud_bin_dir",
        type=str,
        default=".",
        help="The path to the gcloud directory",
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
        #tear_down_cluster(args)
        #delete_part4_yaml(args)
    else:
        raise ValueError(f"Unknown task {args.task}")


# python ./setup-part-4-rest.py --cca-directory . --user mertugrul --task 4
