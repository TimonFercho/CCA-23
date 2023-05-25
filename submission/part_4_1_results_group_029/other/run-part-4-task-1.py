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
.txt
client_agent = paramiko.SSHClient().txt
client_measure = paramiko.SSHClient().txt
memcache_server = paramiko.SSHClient().txt
.txt
client_agent_info = memcache_server_info = client_measure_info = {}.txt
.txt
# this is for compiling mcperf.txt
client_command = "sudo sh -c 'echo deb-src http://europe-west3.gce.archive.ubuntu.com/ubuntu/ bionic main restricted >> /etc/apt/sources.list' ".txt
client_command += "sudo apt-get update \n".txt
client_command += "sudo apt-get install libevent-dev libzmq3-dev git make g++ --yes \n".txt
client_command += "sudo apt-get build-dep memcached --yes \n".txt
client_command += "git clone https://github.com/eth-easl/memcache-perf-dynamic.git \n".txt
client_command += "cd memcache-perf-dynamic \n".txt
client_command += "make".txt
.txt
# this is to load memcached on the server, then make the necessary changes.txt
memcache_command = "sudo apt update".txt
memcache_command += "sudo apt install -y memcached libmemcached-tools".txt
memcache_command += "sudo systemctl status memcached".txt
.txt
memcache_command += "sudo sed -i '23s/.*/-m 1024/' /etc/memcached.conf".txt
.txt
.txt
# done for part 4 task 1.txt
def connect_mcperfs():.txt
    print(">>> Setting up SSH connection to compile mcperf").txt
.txt
    client_agent_info = get_node_info("client-agent").txt
    client_agent_name = client_agent_info["NAME"].txt
    client_agent_IP = client_agent_info["EXTERNAL-IP"].txt
.txt
    client_measure_info = get_node_info("client-measure").txt
    client_measure_name = client_measure_info["NAME"].txt
    client_measure_IP = client_measure_info["EXTERNAL-IP"].txt
.txt
    memcache_server_info = get_node_info("memcache-server").txt
    memcache_server_name = memcache_server_info["NAME"].txt
    memcache_server_IP = memcache_server_info["EXTERNAL-IP"].txt
    memcache_server_internal_IP = memcache_server_info["INTERNAL-IP"].txt
.txt
    # Connecting to client A.txt
    client_agent.set_missing_host_key_policy(.txt
        paramiko.AutoAddPolicy().txt
    )  # no known_hosts error.txt
    client_agent.connect(client_agent_IP, 22, username="ubuntu")  # no passwd needed.txt
.txt
    # Connecting to client B.txt
    memcache_server.set_missing_host_key_policy(.txt
        paramiko.AutoAddPolicy().txt
    )  # no known_hosts error.txt
    memcache_server.connect(.txt
        memcache_server_IP, 22, username="ubuntu".txt
    )  # no passwd needed.txt
.txt
    # Connecting to client measure.txt
    client_measure.set_missing_host_key_policy(.txt
        paramiko.AutoAddPolicy().txt
    )  # no known_hosts error.txt
    client_measure.connect(client_measure_IP, 22, username="ubuntu")  # no passwd needed.txt
.txt
    # add internal IP.txt
    memcache_command += (.txt
        f"sudo sed -i '35s/.*/-l {memcache_server_internal_IP}/' /etc/memcached.conf".txt
    ).txt
.txt
    # TODO: change number of threads for memcached here.txt
    memcached_threads = 2.txt
    memcache_command += "sudo echo ' ' >> /etc/memcached.conf".txt
    memcache_command += (.txt
        "sudo echo '# specifying the number of threads' | sudo tee -a /etc/memcached.conf".txt
    ).txt
    memcache_command += (.txt
        f"sudo echo '-t {memcached_threads}' | sudo tee -a /etc/memcached.conf".txt
    ).txt
    memcache_command += "sudo systemctl restart memcached".txt
.txt
.txt
def spin_up_cluster(args, create_cluster=True, setup_mcperf=True):.txt
    if create_cluster:.txt
        print(f">> Setting up part {args.task}").txt
        os.environ["KOPS_STATE_STORE"] = f"gs://{args.project}-{args.user}".txt
        os.environ["PROJECT"] = args.project.txt
.txt
        print(">> Creating cluster").txt
        if does_cluster_exist(args.cluster_name):.txt
            print(">> Cluster already exists").txt
        else:.txt
            subprocess.run(.txt
                ["kops", "create", "-f", f"{args.cca_directory}/part{args.task}.yaml"],.txt
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
            subprocess.run(["kops", "validate", "cluster", "--wait", "10m"], check=True).txt
            print(">> Cluster deployed successfully").txt
.txt
    # Setup for mcperf clients.txt
.txt
    # TODO: validate the correctess of this approach.txt
    # - what will the username be? can we test whether this works without running everything?.txt
.txt
    connect_mcperfs().txt
.txt
    if setup_mcperf:.txt
        (stdin, stdout, stderr) = client_agent.exec_command(client_command).txt
        stderr = stdout.read().txt
        print("Setup log for client agent: ", client_command, stderr).txt
.txt
        (stdin, stdout, stderr) = memcache_server.exec_command(memcache_command).txt
        stderr = stdout.read().txt
        print("Setup log for memcached server: ", memcache_command, stderr).txt
.txt
        (stdin, stdout, stderr) = client_measure.exec_command(client_command).txt
        stderr = stdout.read().txt
        print("Setup log for client measure: ", client_command, stderr).txt
.txt
    print(f">> Finished setting up part {args.task}").txt
.txt
.txt
def run_benchmark_with_threads(args, benchmark_short, n_threads):.txt
    benchmark = f"parsec-{benchmark_short}".txt
    print(f">> Running benchmark {benchmark} with {n_threads} threads").txt
.txt
    print(">> Creating csv file for results").txt
    create_csv_file(args).txt
.txt
    print(">> Creating benchmark").txt
    subprocess.run(.txt
        [.txt
            "kubectl",.txt
            "create",.txt
            "-f",.txt
            f"{args.cca_directory}/parsec-benchmarks/part2b/{benchmark}_{n_threads}.yaml",.txt
        ],.txt
        check=False,.txt
        stdout=subprocess.PIPE,.txt
        stderr=subprocess.PIPE,.txt
    ).txt
    if not does_pod_exist(benchmark):.txt
        print("!! Benchmark creation failed").txt
        return.txt
.txt
    print(">> Waiting for benchmark job to complete").txt
    subprocess.run(.txt
        [.txt
            "kubectl",.txt
            "wait",.txt
            "--for=condition=complete",.txt
            "job",.txt
            benchmark,.txt
            f"--timeout={args.wait_timeout}s",.txt
        ],.txt
        check=True,.txt
        stdout=subprocess.PIPE,.txt
    ).txt
    print(">> Benchmark completed").txt
.txt
    print(">> Collecting benchmark results").txt
    benchmark_pod = get_pod_info(benchmark).txt
    pod_name = benchmark_pod["NAME"].txt
    result = subprocess.run(.txt
        ["kubectl", "logs", pod_name], check=True, stdout=subprocess.PIPE.txt
    ).txt
    real_ms, user_ms, sys_ms = parse_execution_times(result).txt
.txt
    print(f">> Real: {real_ms} ms, User: {user_ms} ms, Sys: {sys_ms} ms").txt
.txt
    print(">> Appending benchmark results to csv file").txt
    append_result_to_csv(.txt
        args, benchmark_short, real_ms, user_ms, sys_ms, n_threads=n_threads.txt
    ).txt
.txt
    print(">> Deleting all benchmarking jobs").txt
    subprocess.run(.txt
        ["kubectl", "delete", "jobs", "--all"], check=True, stdout=subprocess.PIPE.txt
    ).txt
.txt
    print(">> Deleting modified config file").txt
    subprocess.run(.txt
        [.txt
            "rm",.txt
            f"{args.cca_directory}/parsec-benchmarks/part2b/{benchmark}_{n_threads}.yaml",.txt
        ],.txt
        check=True,.txt
        stdout=subprocess.PIPE,.txt
    ).txt
.txt
.txt
def log_job_time(schedule):.txt
    subprocess.run(["kubectl", "get", "pods", "-o", "json", ">", "results.json"]).txt
.txt
    parsec_df = get_time.get_time("results.json").txt
.txt
    for node_id, node_schedule in enumerate(schedule):.txt
        for run_id, run in enumerate(node_schedule["runs"]):.txt
            for job in run:.txt
                parsec_df.loc[job]["machine"] = node_schedule["node"].txt
.txt
    parsec_df.to_csv("parsec_times.csv").txt
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
# executes the necessary mcperf methods on the client_agent and memcache_server.txt
def start_mcperf(memcached_ip):.txt
    client_agent_name = client_agent["NAME"].txt
    client_agent_IP = client_agent["INTERNAL-IP"].txt
.txt
    memcache_server = memcache_server_info["NAME"].txt
    memcache_server_IP = memcache_server_info["INTERNAL-IP"].txt
.txt
    client_measure_name = client_measure_info["NAME"].txt
    client_measure_IP = client_measure_info["INTERNAL-IP"].txt
.txt
    (stdin, stdout, stderr) = client_agent.exec_command("./mcperf -T 16 -A").txt
    cmd_output = stdout.read().txt
.txt
    # ========== THIS IS FOR THE MAIN PART OF 4 ===============.txt
    # client_measure_command = f"./mcperf -s {memcached_ip} --loadonly /n".txt
    # +f"./mcperf -s {memcached_ip} -a {client_agent_IP} ".txt
    # +"noload -T 16 -C 4 -D 4 -Q 1000 -c 4 -t 10".txt
    # +"--qps_interval 2 --qps_min 5000 --qps_max 100000".txt
.txt
    client_measure_command = f"./mcperf -s {memcached_ip} --loadonly /n".txt
    +f"./mcperf -s {memcached_ip} -a {client_agent_IP} ".txt
    +"--noload -T 16 -C 4 -D 4 -Q 1000 -c 4 -t 5".txt
    +"--scan 5000:125000:5000".txt
.txt
    (stdin, stdout, stderr) = client_measure.exec_command(client_measure_command).txt
    return stdout.txt
.txt
.txt
def create_csv_file(args, n_threads, n_cores):.txt
    header = "timestamp,cluster_name,real_ms,user_ms,sys_ms,throughput\n".txt
    title = f"memcached_{n_threads}threads_{n_cores}cores.csv".txt
.txt
    if not os.path.exists(title):.txt
        with open("title", "w") as f:.txt
            f.write(header).txt
.txt
.txt
def run_memcached_with_threads(args, n_threads, n_cores):.txt
    print(f">> Running memcached with {n_threads} threads and {n_cores} cores").txt
.txt
    print(">> Creating csv file for results").txt
    create_csv_file(args, n_threads, n_cores).txt
.txt
    print(">> Creating benchmark").txt
    subprocess.run(.txt
        [.txt
            "kubectl",.txt
            "create",.txt
            "-f",.txt
            f"{args.cca_directory}/parsec-benchmarks/part4_t1/memcached_t{n_threads}_c{n_cores}.yaml",.txt
        ],.txt
        check=False,.txt
        stdout=subprocess.PIPE,.txt
        stderr=subprocess.PIPE,.txt
    ).txt
    if not does_pod_exist("memcached"):.txt
        print("!! Memcached creation failed").txt
        return.txt
.txt
    print(">> Waiting for benchmark job to complete").txt
    subprocess.run(.txt
        [.txt
            "kubectl",.txt
            "wait",.txt
            "--for=condition=complete",.txt
            "job",.txt
            "memcached",.txt
            f"--timeout={args.wait_timeout}s",.txt
        ],.txt
        check=True,.txt
        stdout=subprocess.PIPE,.txt
    ).txt
    print(">> Benchmark completed").txt
    print(">> Collecting memcached results").txt
    benchmark_pod = get_pod_info("memcached").txt
    pod_name = benchmark_pod["NAME"].txt
    result = subprocess.run(.txt
        ["kubectl", "logs", pod_name], check=True, stdout=subprocess.PIPE.txt
    ).txt
    real_ms, user_ms, sys_ms = parse_execution_times(result).txt
.txt
    print(f">> Real: {real_ms} ms, User: {user_ms} ms, Sys: {sys_ms} ms").txt
    print(">> Appending benchmark results to csv file").txt
    append_result_to_csv(args, real_ms, user_ms, sys_ms, n_threads, n_cores).txt
.txt
    print(">> Deleting all jobs and pods").txt
    subprocess.run(.txt
        ["kubectl", "delete", "jobs", "--all"], check=True, stdout=subprocess.PIPE.txt
    ).txt
    subprocess.run(.txt
        ["kubectl", "delete", "pods", "--all"], check=True, stdout=subprocess.PIPE.txt
    ).txt
.txt
.txt
# timestamp,cluster_name,real_ms,user_ms,sys_ms,throughput.txt
def append_result_to_csv(args, real, user, sys, n_threads, n_cores):.txt
    now = datetime.now().txt
    line = f"{now},{args.cluster_name},{real},{user},{sys},20".txt
.txt
    title = f"memcached_{n_threads}threads_{n_cores}cores.csv".txt
    with open(title, "a") as f:.txt
        f.write(line).txt
.txt
.txt
def run_part_4(args):.txt
    print(">> Running part 4").txt
.txt
    for threads in range(1, 3):.txt
        for cores in range(1, 3):.txt
            run_memcached_with_threads(args, threads, cores).txt
.txt
    # schedule_dir = f"{args.cca_directory}/schedules/{args.schedule}".txt
.txt
    # stdout_mcperf = None.txt
.txt
    # memcached_running = False.txt
.txt
    # json_file_path = f"{schedule_dir}/{args.schedule}.json".txt
.txt
    # with open(json_file_path, "r") as j:.txt
    #     schedule = json.loads(j.read()).txt
.txt
    # num_jobs_done = 0.txt
.txt
    # # instead of popping from job lists, we update an external cursor.txt
    # # to avoid changing structures while iterating through them.txt
    # run_cursor = {}.txt
    # for node_id, node_schedule in enumerate(schedule):.txt
    #     current_cursor = {}.txt
    #     for run_id, run in enumerate(node_schedule["runs"]):.txt
    #         current_cursor[run_id] = 0.txt
    #     run_cursor[node_id] = current_cursor.txt
.txt
    # N_JOBS = 8.txt
    # dispatched_jobs = [].txt
.txt
    # while num_jobs_done != N_JOBS:.txt
    #     for node_id, node_schedule in enumerate(schedule):.txt
    #         for run_id, run in enumerate(node_schedule["runs"]):.txt
    #             idx = run_cursor[node_id][run_id].txt
    #             finished_run = idx >= len(run).txt
.txt
    #             if finished_run:.txt
    #                 continue.txt
.txt
    #             job = run[idx].txt
.txt
    #             if dispatched_jobs and does_pod_exist(job):.txt
    #                 info = get_pod_info(job).txt
    #                 is_running = info["STATUS"] == "Running".txt
    #                 if is_running:.txt
    #                     print(f">> Job {job} on node {node_id} is running").txt
.txt
    #                     if job == "some-memcached" and not memcached_running:.txt
    #                         memcached_running = True.txt
    #                         # retrieving IP for memcached and starting mcperfs.txt
    #                         stdout_mcperf = start_mcperf(info["IP"]).txt
    #                         time.sleep(3).txt
    #                     continue.txt
.txt
    #                 is_complete = info["STATUS"] == "Completed".txt
.txt
    #                 if is_complete:.txt
    #                     print(f">> Job {job} on node {node_id} succeeded").txt
    #                     run_cursor[node_id][run_id] = idx + 1.txt
    #                     job = run[idx].txt
.txt
    #                     num_jobs_done += 1.txt
.txt
    #                 job_name = info["NAME"].txt
    #                 if info["STATUS"] == "Failed":.txt
    #                     num_jobs_done += 1.txt
    #                     print(f">> Job {job_name} failed").txt
.txt
    #             elif (.txt
    #                 (not memcached_running and job == "some-memcached").txt
    #                 or memcached_running.txt
    #             ) and job not in dispatched_jobs:.txt
    #                 print(f">> Starting job {job} on node {node_id}").txt
    #                 print(.txt
    #                     f">> kubectl create -f {args.cca_directory}/{schedule_dir}/{job}.yaml".txt
    #                 ).txt
    #                 subprocess.run(.txt
    #                     [.txt
    #                         "kubectl",.txt
    #                         "create",.txt
    #                         "-f",.txt
    #                         f"{args.cca_directory}/{schedule_dir}/{job}.yaml",.txt
    #                     ],.txt
    #                     check=True,.txt
    #                     stdout=subprocess.PIPE,.txt
    #                     stderr=subprocess.PIPE,.txt
    #                 ).txt
    #                 dispatched_jobs.append(job).txt
    #             else:.txt
    #                 print(f">> Job {job} is not alive (yet)").txt
.txt
    #                 # TODO: handle this somewhere else when we know memcached is running.txt
    #                 # if job == "memcache-t1-cpuset":.txt
    #                 #     # retrieving IP for memcached and starting mcperfs.txt
    #                 #     info = get_pod_info(job).txt
    #                 #     stdout_mcperf = start_mcperf(info["IP"]).txt
.txt
    #     # TODO: introduce some delay?.txt
.txt
    # if stdout_mcperf is None:.txt
    #     # raise error.txt
    #     print("No stdout for mcperf present").txt
    # else:.txt
    #     print(">> Collecting mcperf results").txt
    #     save_mcperf_logs(stdout_mcperf).txt
.txt
    # log_job_time(schedule).txt
    # print(">> Parsec job logs Saved").txt
.txt
    # print(">> Collecting mcperf results").txt
    # get_mcperf_logs(args).txt
.txt
.txt
# writing full mcperf log output.txt
def save_mcperf_logs(stdout_mcperf):.txt
    output = stdout_mcperf.decode("utf-8").txt
    print(output).txt
    print(">> Saving to txt file").txt
.txt
    txt_filename = f"mcperf-part{args.task}.txt".txt
.txt
    with open(txt_filename, "w") as f:.txt
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
def does_pod_exist(pod_name_beginning):.txt
    return get_pod_info(pod_name_beginning) is not None.txt
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
def get_pod_info(pod_name_beginning):.txt
    result = subprocess.run(.txt
        ["kubectl", "get", "pods", "-o", "wide", "--show-labels"],.txt
        check=True,.txt
        stdout=subprocess.PIPE,.txt
    ).txt
    data = parse_result_output(result).txt
    pod_info = [pod for pod in data if pod["NAME"].startswith(pod_name_beginning)].txt
    if len(pod_info) == 0:.txt
        return None.txt
    return pod_info[0].txt
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
    total_seconds = int(mins) * 60 + int(seconds) + float(fraction.rstrip("s")) / 1000.txt
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
        "<user>": args.user,.txt
    }.txt
.txt
    # Define the variable to replace '<user>'.txt
    replacement_variable = "John Doe".txt
.txt
    # Copy and rewrite the file.txt
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
def append_result_to_csv(.txt
    args, benchmark, real, user, sys, interference=None, n_threads=None.txt
):.txt
    now = datetime.now().txt
    if args.task == "2a":.txt
        line = f"{now},{args.cluster_name},{benchmark},{interference},{real},{user},{sys}\n".txt
    elif args.task == "2b":.txt
        line = (.txt
            f"{now},{args.cluster_name},{benchmark},{n_threads},{real},{user},{sys}\n".txt
        ).txt
    else:.txt
        raise ValueError(f"Invalid task: {args.task}").txt
    with open(args.output, "a") as f:.txt
        f.write(line).txt
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
    parser.add_argument("-c", "--cluster-name", type=str, default="part4.k8s.local").txt
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
