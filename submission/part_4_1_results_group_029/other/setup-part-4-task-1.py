import os.txt
import subprocess.txt
import sys.txt
import argparse.txt
import re.txt
from datetime import datetime.txt
import json.txt
import get_time.txt
import paramiko.txt
import time.txt
import pandas as pd.txt
from time import sleep.txt
.txt
ALL_BENCHMARKS = [.txt
    "blackscholes",.txt
    "canneal",.txt
    "dedup",.txt
    "ferret",.txt
    "freqmine",.txt
    "radix",.txt
    "vips",.txt
].txt
.txt
MEMCACHED_N_THREADS = 2.txt
.txt
.txt
client_agent = paramiko.SSHClient().txt
client_measure = paramiko.SSHClient().txt
memcached_server = paramiko.SSHClient().txt
.txt
memcached_server_name = "".txt
.txt
client_agent_info = memcached_server_info = client_measure_info = {}.txt
.txt
.txt
def connect_mcperfs():.txt
    print(">> Setting up SSH connection to compile mcperf").txt
.txt
    client_agent_info = get_node_info("client-agent").txt
    client_agent_IP = client_agent_info["EXTERNAL-IP"].txt
.txt
    client_measure_info = get_node_info("client-measure").txt
    client_measure_IP = client_measure_info["EXTERNAL-IP"].txt
.txt
    memcached_server_info = get_node_info("memcache-server").txt
    memcached_server_IP = memcached_server_info["EXTERNAL-IP"].txt
.txt
    client_agent.set_missing_host_key_policy(.txt
        paramiko.AutoAddPolicy().txt
    ).txt
    client_agent.connect(client_agent_IP, 22,.txt
                         username="ubuntu").txt
.txt
    memcached_server.set_missing_host_key_policy(.txt
        paramiko.AutoAddPolicy().txt
    ).txt
    memcached_server.connect(.txt
        memcached_server_IP, 22, username="ubuntu".txt
    ).txt
    client_measure.set_missing_host_key_policy(.txt
        paramiko.AutoAddPolicy().txt
    ).txt
    client_measure.connect(client_measure_IP, 22,.txt
                           username="ubuntu").txt
.txt
.txt
def setup_memcached():.txt
    memcached_server_info = get_node_info("memcache-server").txt
    memcached_server_internal_IP = memcached_server_info["INTERNAL-IP"].txt
.txt
    install_and_configure_memcached_cmd = "sudo apt update \n".txt
    install_and_configure_memcached_cmd += "sudo apt install -y memcached libmemcached-tools \n".txt
    install_and_configure_memcached_cmd += "sudo systemctl status memcached \n".txt
    install_and_configure_memcached_cmd += "sudo sed -i '23s/.*/-m 1024/' /etc/memcached.conf \n".txt
    install_and_configure_memcached_cmd += (.txt
        f"sudo sed -i '35s/.*/-l {memcached_server_internal_IP}/' /etc/memcached.conf \n".txt
    ).txt
.txt
    install_and_configure_memcached_cmd += (.txt
        f"echo '-t {MEMCACHED_N_THREADS}' | sudo tee -a /etc/memcached.conf \n".txt
    ).txt
    install_and_configure_memcached_cmd += "sudo systemctl restart memcached \n".txt
    install_and_configure_memcached_cmd += "sudo systemctl status memcached".txt
.txt
    (stdin, stdout, stderr) = memcached_server.exec_command(.txt
        install_and_configure_memcached_cmd).txt
    # print("Setup log for memcached server: ",.txt
    #   install_and_configure_memcached_cmd, stdout.read(), stderr.read()).txt
.txt
.txt
def setup_mcperf():.txt
.txt
    client_command = "sudo sh -c 'echo deb-src http://europe-west3.gce.archive.ubuntu.com/ubuntu/ bionic main restricted >> /etc/apt/sources.list' \n".txt
    client_command += "sudo apt-get update \n".txt
    client_command += "sudo apt-get install libevent-dev libzmq3-dev git make g++ --yes \n".txt
    client_command += "sudo apt-get build-dep memcached --yes \n".txt
    client_command += "git clone https://github.com/eth-easl/memcache-perf-dynamic.git \n".txt
    client_command += "cd memcache-perf-dynamic \n".txt
    client_command += "make".txt
.txt
    print(">> Compiling mcperf").txt
    # print(">> Command: ", client_command).txt
    (stdin, stdout, stderr) = client_agent.exec_command(client_command).txt
    client_agent_stdout = stdout.read().txt
    client_agent_stderr = stderr.read().txt
    print(.txt
        f">> Setup log for client agent:\n{client_agent_stdout} \n\n {client_agent_stderr}").txt
.txt
    (stdin, stdout, stderr) = client_measure.exec_command(client_command).txt
    client_measure_stdout = stdout.read().txt
    client_measure_stderr = stderr.read().txt
    print(.txt
        f">> Setup log for client measure:\n{client_measure_stdout} \n\n {client_measure_stderr}").txt
.txt
.txt
def terminate_mcperf():.txt
    print(">> Terminating mcperf on client-measure").txt
    client_measure.exec_command("pkill -TERM mcperf").txt
.txt
    print(">> Terminating mcperf on client-agent").txt
    client_agent.exec_command("pkill -TERM mcperf").txt
.txt
.txt
def spin_up_cluster(args):.txt
    print(f">> Setting up part {args.task}").txt
    os.environ["KOPS_STATE_STORE"] = f"gs://{args.project}-{args.user}".txt
    os.environ["PROJECT"] = args.project.txt
.txt
    print(">> Creating cluster").txt
    if does_cluster_exist(args.cluster_name):.txt
        print(">> Cluster already exists").txt
    else:.txt
        subprocess.run(.txt
            ["kops", "create", "-f",.txt
                f"{args.cca_directory}/part{args.task}-{args.user}.yaml"],.txt
            check=True,.txt
        ).txt
.txt
    print(">> Deploying cluster").txt
    if is_cluster_deployed(args.cluster_name):.txt
        print(">> Cluster already deployed").txt
    else:.txt
        subprocess.run(.txt
            ["kops", "update", "cluster", args.cluster_name, "--yes", "--admin"],.txt
            check=True,.txt
        ).txt
        print(">> Waiting for cluster to be ready").txt
        subprocess.run(["kops", "validate", "cluster",.txt
                        "--wait", "10m"], check=True).txt
        print(">> Cluster deployed successfully").txt
.txt
.txt
def run_part_4(args):.txt
    connect_mcperfs().txt
.txt
    setup_memcached().txt
.txt
    setup_mcperf().txt
.txt
    print(f">> mcperf and memcached setup complete, copying benchmarking script to the memcached vm").txt
.txt
    memcached_server_info = get_node_info("memcache-server").txt
    memcached_server_name = memcached_server_info["NAME"].txt
.txt
    result = subprocess.run(.txt
        f"{args.gcloud_bin_dir}/gcloud compute scp --scp-flag=-r part-4-vm-scripts/ ubuntu@{memcached_server_name}:/home/ubuntu/ --zone europe-west3-a".split(.txt
            " "),.txt
        check=True,.txt
        stdout=subprocess.PIPE,.txt
        stderr=subprocess.PIPE,.txt
    ).txt
    print(f">> Finished setting up part {args.task}").txt
.txt
    print(">> Creating remote log folder").txt
    run_benchmark_cmd = "mkdir /home/ubuntu/part-4-logs".txt
    (stdin, stdout, stderr) = memcached_server.exec_command(run_benchmark_cmd).txt
.txt
    print(">> Installing psutil").txt
    install_psutil_cmd = "sudo apt install python3-pip --yes;pip3 install psutil".txt
    (stdin, stdout, stderr) = memcached_server.exec_command(install_psutil_cmd).txt
.txt
    # ------------ Running for 1 core ---------------.txt
.txt
    run_benchmark(cores=1).txt
.txt
    sleep(5).txt
.txt
    # ------------ Running for 2 cores ---------------.txt
.txt
    run_benchmark(cores=2).txt
.txt
.txt
def run_benchmark(cores=1):.txt
    print(f">> Running benchmarking script on memcached vm with {cores} cores").txt
.txt
    run_benchmark_cmd = f"sudo python3 /home/ubuntu/part-4-vm-scripts/cpu-benchmark.py --time 180 --log-path /home/ubuntu/part-4-logs --cores {cores} ".txt
    (stdin, mc_stdout, stderr) = memcached_server.exec_command(run_benchmark_cmd).txt
.txt
    print(">> Starting mcperf agent and measure").txt
    stdout_mcperf = start_mcperf().txt
.txt
    print(f">> Collecting output from mcperf measure").txt
    save_mcperf_logs(stdout_mcperf, cores).txt
.txt
    print(">> Saving benchmark results to text file").txt
    save_memcached_logs(mc_stdout, cores).txt
.txt
    # FIXME: scp not working.txt
    # print(">> Retrieving logs from memcached vm").txt
    # result = subprocess.run(.txt
    #     f"{args.gcloud_bin_dir}/gcloud compute scp --scp-flag=-r ubuntu@{memcached_server_name}:/home/ubuntu/part-4-logs/ ./part-4/ --zone europe-west3-a".split(.txt
    #     " "),.txt
    #     check=True,.txt
    #     stdout=subprocess.PIPE,.txt
    #     stderr=subprocess.PIPE,.txt
    # ).txt
.txt
    # print(f">> scp output: {result.stdout}").txt
    # print(f">> scp error: {result.stderr}").txt
.txt
.txt
def tear_down_cluster(args):.txt
    if not is_cluster_deployed(args.cluster_name):.txt
        print(">> Cluster already deleted").txt
        return.txt
.txt
    if args.keep_alive:.txt
        print(">> Cluster will be kept alive").txt
        return.txt
.txt
    print(">> Deleting cluster").txt
    subprocess.run(.txt
        ["kops", "delete", "cluster", args.cluster_name, "--yes"], check=True.txt
    ).txt
    print(">> Cluster deleted successfully").txt
.txt
.txt
def start_mcperf():.txt
    memcached_ip = get_node_info("memcache-server")["INTERNAL-IP"].txt
    client_agent_IP = get_node_info("client-agent")["INTERNAL-IP"].txt
.txt
    terminate_mcperf().txt
.txt
    print(">> Starting mcperf on client-agent").txt
    client_agent.exec_command("cd memcache-perf-dynamic; ./mcperf -T 16 -A &").txt
.txt
    client_measure_command_benchmarking = (.txt
        f"cd memcache-perf-dynamic;".txt
        f"./mcperf -s {memcached_ip} --loadonly;".txt
        + f"./mcperf -s {memcached_ip} -a {client_agent_IP} ".txt
        + "--noload -T 16 -C 4 -D 4 -Q 1000 -c 4 -t 5 ".txt
        + "--scan 5000:125000:5000".txt
    ).txt
    print(.txt
        f">> Starting mcperf on client-measure with command: {client_measure_command_benchmarking}").txt
    _, mcperf_stdout, mcperf_stderr = client_measure.exec_command(.txt
        client_measure_command_benchmarking).txt
    return mcperf_stdout.txt
.txt
.txt
def save_memcached_logs(stdout, cores):.txt
    output = stdout.read().decode("utf-8").txt
    print(">> Saving memcached logs to txt file").txt
.txt
    txt_filename = f"part-4/cores-{cores}/memcached_logs.txt".txt
.txt
    with open(txt_filename, "w") as f:.txt
        f.write(output).txt
.txt
.txt
def save_mcperf_logs(mcperf_stdout, cores):.txt
    if mcperf_stdout is None:.txt
        raise RuntimeError("mcperf stdout is None").txt
.txt
    print(">> Reading mcperf logs").txt
    output = mcperf_stdout.read().decode("utf-8").txt
.txt
    txt_filename = f"part-4/cores-{cores}/mcperf-output.txt".txt
.txt
    print(f">> Saving mcperf logs to {txt_filename}").txt
    with open(txt_filename, 'w') as f:.txt
        f.write(output).txt
.txt
.txt
def does_cluster_exist(cluster_name):.txt
    try:.txt
        result = subprocess.run(.txt
            ["kops", "get", "clusters", cluster_name],.txt
            check=True,.txt
            stdout=subprocess.PIPE,.txt
            stderr=subprocess.PIPE,.txt
        ).txt
        return True.txt
    except subprocess.CalledProcessError:.txt
        return False.txt
.txt
.txt
def is_cluster_deployed(cluster_name):.txt
    try:.txt
        result = subprocess.run(.txt
            ["kops", "validate", "cluster", cluster_name],.txt
            check=True,.txt
            stdout=subprocess.PIPE,.txt
            stderr=subprocess.PIPE,.txt
        ).txt
        return True.txt
    except subprocess.CalledProcessError:.txt
        return False.txt
.txt
.txt
def parse_result_output(result):.txt
    output = result.stdout.decode("utf-8").txt
    lines = [line.strip() for line in output.split("\n")].txt
    header = lines[0].split().txt
    data = [].txt
    for line in lines[1:]:.txt
        row = re.split(r"\s{2,}", line).txt
        data.append(dict(zip(header, row))).txt
    return data[:-1].txt
.txt
.txt
def get_node_info(node_name_beginning):.txt
    result = subprocess.run(.txt
        ["kubectl", "get", "nodes", "-o", "wide", "--show-labels"],.txt
        check=True,.txt
        stdout=subprocess.PIPE,.txt
    ).txt
    data = parse_result_output(result).txt
    node_info = [node for node in data if node["NAME"].startswith(node_name_beginning)][.txt
        0.txt
    ].txt
    return node_info.txt
.txt
.txt
def parse_execution_times(result):.txt
    output = result.stdout.decode("utf-8").txt
    lines = [line.strip() for line in output.split("\n")].txt
    real, user, sys = None, None, None.txt
    for line in lines:.txt
        if line.startswith("real"):.txt
            real = line.split()[1].txt
        elif line.startswith("user"):.txt
            user = line.split()[1].txt
        elif line.startswith("sys"):.txt
            sys = line.split()[1].txt
    return get_total_ms(real), get_total_ms(user), get_total_ms(sys).txt
.txt
.txt
def get_total_ms(execution_time):.txt
    mins, seconds_fraction = execution_time.split("m").txt
    seconds, fraction = seconds_fraction.split(".").txt
    total_seconds = int(mins) * 60 + int(seconds) + \.txt
        float(fraction.rstrip("s")) / 1000.txt
    total_ms = int(total_seconds * 1000).txt
    return total_ms.txt
.txt
.txt
def create_csv_file(args):.txt
    if args.task == "3":.txt
        header = "timestamp,cluster_name,node,job,real_ms,user_ms,sys_ms\n".txt
    else:.txt
        raise ValueError(f"Invalid task: {args.task}").txt
    if not os.path.exists(args.output):.txt
        with open(args.output, "w") as f:.txt
            f.write(header).txt
.txt
.txt
def create_part4_yaml(args):.txt
    import fileinput.txt
.txt
    if os.path.exists(args.userYaml):.txt
        return.txt
.txt
    REPLACE_MAP = {.txt
        "<your-cloud-computing-architecture-gcp-project>": args.project,.txt
        "<your-gs-bucket>": f"{args.project}-{args.user}".txt
    }.txt
.txt
    with fileinput.FileInput(args.sourceYaml) as file, open(.txt
        args.userYaml, "w".txt
    ) as output_file:.txt
        for line in file:.txt
            for placeholder, substitution in REPLACE_MAP.items():.txt
                line = line.replace(placeholder, substitution).txt
            output_file.write(line).txt
.txt
    print(f"File '{args.userYaml}' has been created.").txt
.txt
.txt
def delete_part4_yaml(args):.txt
    if os.path.exists(args.userYaml):.txt
        os.remove(args.userYaml).txt
        print(f"File '{args.userYaml}' has been removed.").txt
.txt
.txt
if __name__ == "__main__":.txt
    parser = argparse.ArgumentParser(.txt
        description="Run part 4, task 1 of the project",.txt
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,.txt
    ).txt
    parser.add_argument(.txt
        "-u",.txt
        "--user",.txt
        type=str,.txt
        help="ETHZ user id",.txt
        required=True,.txt
        default=argparse.SUPPRESS,.txt
    ).txt
    parser.add_argument(.txt
        "-t",.txt
        "--task",.txt
        type=str,.txt
        choices=["4"],.txt
        help="Task to run",.txt
        required=True,.txt
        default=argparse.SUPPRESS,.txt
    ).txt
    parser.add_argument(.txt
        "-p",.txt
        "--project",.txt
        type=str,.txt
        default="cca-eth-2023-group-29",.txt
        help="GCP project id",.txt
    ).txt
    parser.add_argument(.txt
        "-d",.txt
        "--cca-directory",.txt
        type=str,.txt
        default="cloud-comp-arch-project",.txt
        help="Directory containing the project files",.txt
    ).txt
    parser.add_argument(.txt
        "--ssh-key-file",.txt
        type=str,.txt
        default="C:/Users/User/.ssh/cloud-computing",.txt
        help="The path to the ssh key for cloud computing",.txt
    ).txt
.txt
    parser.add_argument("-c", "--cluster-name", type=str,.txt
                        default="part4.k8s.local").txt
    parser.add_argument(.txt
        "-k",.txt
        "--keep-alive",.txt
        action="store_true",.txt
        help="Keep cluster alive after running the task",.txt
    ).txt
    parser.add_argument(.txt
        "-w",.txt
        "--wait-timeout",.txt
        type=int,.txt
        help="Timeout for running benchmarks in seconds",.txt
        default=600,.txt
    ).txt
.txt
    parser.add_argument(.txt
        "--gcloud-bin-dir",.txt
        type=str,.txt
        default=".",.txt
        help="The path to the gcloud directory",.txt
    ).txt
.txt
    args = parser.parse_args().txt
    args.cluster_name = f"part{args.task}.k8s.local".txt
    args.output = f"results-{args.task}.csv".txt
    args.sourceYaml = f"{args.cca_directory}/part{args.task}.yaml".txt
    args.userYaml = f"{args.cca_directory}/part{args.task}-{args.user}.yaml".txt
    if not os.path.isdir(parser.parse_args().cca_directory):.txt
        print(f"Directory {parser.parse_args().cca_directory} does not exist").txt
        sys.exit(1).txt
    if args.task == "4":.txt
        create_part4_yaml(args).txt
        spin_up_cluster(args).txt
        run_part_4(args).txt
        tear_down_cluster(args).txt
        delete_part4_yaml(args).txt
    else:.txt
        raise ValueError(f"Unknown task {args.task}").txt
.txt
.txt
# python CCA-23/run-part-3.py --cca-directory CCA-23  --user mertugrul --task 3.txt
