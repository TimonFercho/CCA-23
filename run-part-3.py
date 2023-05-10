import os
import subprocess
import sys
import argparse
import re
from datetime import datetime

ALL_BENCHMARKS = ['blackscholes', 'canneal', 'dedup', 'ferret', 'freqmine', 'radix', 'vips']


def spin_up_cluster(args):
    print(f">> Setting up part {args.task}")
    os.environ['KOPS_STATE_STORE'] = f'gs://{args.project}-{args.user}'
    os.environ['PROJECT'] = args.project

    print(">> Creating cluster")
    if does_cluster_exist(args.cluster_name):
        print(">> Cluster already exists")
    else:
        subprocess.run(['kops', 'create', '-f', f'{args.cca_directory}/part{args.task}.yaml'], check=True)

    print(">> Deploying cluster")
    if is_cluster_deployed(args.cluster_name):
        print(">> Cluster already deployed")
    else:
        subprocess.run(['kops', 'update', 'cluster', args.cluster_name, '--yes', '--admin'], check=True)
        print(">> Waiting for cluster to be ready")
        subprocess.run(['kops', 'validate', 'cluster', '--wait', '10m'], check=True)
        print(">> Cluster deployed successfully")

    print(">> Labeling parsec server node")
    parsec_node_name = get_node_info('parsec-server')['NAME']
    subprocess.run(['kubectl', 'label', 'nodes', parsec_node_name, 'cca-project-nodetype=parsec'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    parsec_node = get_node_info('parsec-server')
    parsec_node_labels = get_node_info('parsec-server')['LABELS']
    if not 'cca-project-nodetype=parsec' in parsec_node_labels:
        print(">> Failed to add label")
        return

    print(f">> Finished setting up part {args.task}")


def run_benchmark_with_threads(args, benchmark_short, n_threads):
    benchmark = f"parsec-{benchmark_short}"
    print(f">> Running benchmark {benchmark} with {n_threads} threads")

    print(">> Creating csv file for results")   
    create_csv_file(args)

    print(">> Creating modified config file")
    create_modified_config_file(args, benchmark, n_threads)

    print(">> Creating benchmark")
    subprocess.run(['kubectl', 'create', '-f', f'{args.cca_directory}/parsec-benchmarks/part2b/{benchmark}_{n_threads}.yaml'], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not does_pod_exist(benchmark):
        print("!! Benchmark creation failed")
        return
    
    print(">> Waiting for benchmark job to complete")
    subprocess.run(['kubectl', 'wait', '--for=condition=complete', 'job', benchmark, f'--timeout={args.wait_timeout}s'], check=True, stdout=subprocess.PIPE)
    print(">> Benchmark completed")

    print(">> Collecting benchmark results")
    benchmark_pod = get_pod_info(benchmark)
    pod_name = benchmark_pod['NAME']
    result = subprocess.run(['kubectl', 'logs', pod_name], check=True, stdout=subprocess.PIPE)
    real_ms, user_ms, sys_ms = parse_execution_times(result)

    print(f">> Real: {real_ms} ms, User: {user_ms} ms, Sys: {sys_ms} ms")

    print(">> Appending benchmark results to csv file")
    append_result_to_csv(args, benchmark_short, real_ms, user_ms, sys_ms, n_threads=n_threads)

    print(">> Deleting all benchmarking jobs")
    subprocess.run(['kubectl', 'delete', 'jobs', '--all'], check=True, stdout=subprocess.PIPE)

    print(">> Deleting modified config file")
    subprocess.run(['rm', f'{args.cca_directory}/parsec-benchmarks/part2b/{benchmark}_{n_threads}.yaml'], check=True, stdout=subprocess.PIPE)


def create_modified_config_file(args, benchmark, n_threads):
    with open(f'{args.cca_directory}/parsec-benchmarks/part2b/{benchmark}.yaml', 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if '-n 1' in line:
                lines[i] = line.replace('-n 1', f'-n {n_threads}')
        with open(f'{args.cca_directory}/parsec-benchmarks/part2b/{benchmark}_{n_threads}.yaml', 'w') as f:
            f.writelines(lines)

def tear_down_cluster(args):
    if not is_cluster_deployed(args.cluster_name):
        print(">> Cluster already deleted")
        return

    if args.keep_alive:
        print(">> Cluster will be kept alive")
        return

    print(">> Deleting cluster")
    subprocess.run(['kops', 'delete', 'cluster', args.cluster_name, '--yes'], check=True)
    print(">> Cluster deleted successfully")

def run_part_2b(args):
    print(">> Running part 2b")
    benchmarks = args.benchmarks
    if 'all' in args.benchmarks:
        benchmarks = ALL_BENCHMARKS
    for benchmark in benchmarks:
        for n_threads in args.n_threads:
            run_benchmark_with_threads(args, benchmark, n_threads)
    print(">> Part 2b completed")

def does_cluster_exist(cluster_name):
    try:
        result = subprocess.run(['kops', 'get', 'clusters', cluster_name], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError:
        return False

def is_cluster_deployed(cluster_name):
    try:
        result = subprocess.run(['kops', 'validate', 'cluster', cluster_name], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError:
        return False

def parse_result_output(result):
    output = result.stdout.decode('utf-8')
    lines = [line.strip() for line in output.split("\n")]
    header = lines[0].split()
    data = []
    for line in lines[1:]:
        row = re.split(r'\s{2,}', line)
        data.append(dict(zip(header, row)))
    return data[:-1]

def does_pod_exist(pod_name_beginning):
    return get_pod_info(pod_name_beginning) is not None

def get_node_info(node_name_beginning):
    result = subprocess.run(['kubectl', 'get', 'nodes', '-o', 'wide', '--show-labels'], check=True, stdout=subprocess.PIPE)
    data = parse_result_output(result)
    node_info = [node for node in data if node['NAME'].startswith(node_name_beginning)][0]
    return node_info

def get_pod_info(pod_name_beginning):
    result = subprocess.run(['kubectl', 'get', 'pods', '-o', 'wide', '--show-labels'], check=True, stdout=subprocess.PIPE)
    data = parse_result_output(result)
    pod_info = [pod for pod in data if pod['NAME'].startswith(pod_name_beginning)]
    if len(pod_info) == 0:
        return None
    return pod_info[0]

def parse_execution_times(result):
    output = result.stdout.decode('utf-8')
    lines = [line.strip() for line in output.split("\n")]
    real, user, sys = None, None, None
    for line in lines:
        if line.startswith('real'):
            real = line.split()[1]
        elif line.startswith('user'):
            user = line.split()[1]
        elif line.startswith('sys'):
            sys = line.split()[1]
    return get_total_ms(real), get_total_ms(user), get_total_ms(sys)

def get_total_ms(execution_time):
    mins, seconds_fraction = execution_time.split("m")
    seconds, fraction = seconds_fraction.split(".")
    total_seconds = int(mins) * 60 + int(seconds) + float(fraction.rstrip('s')) / 1000
    total_ms = int(total_seconds * 1000)
    return total_ms

def create_csv_file(args):
    if args.task == '2a':
        header = 'timestamp,cluster_name,benchmark,interference,real_ms,user_ms,sys_ms\n'
    elif args.task == '2b':
        header = 'timestamp,cluster_name,benchmark,n_threads,real_ms,user_ms,sys_ms\n'
    else:
        raise ValueError(f'Invalid task: {args.task}')
    if not os.path.exists(args.output):
        with open(args.output, 'w') as f:
            f.write(header)

def append_result_to_csv(args, benchmark, real, user, sys, interference=None, n_threads=None):
    now = datetime.now()
    if args.task == '2a':
        line = f'{now},{args.cluster_name},{benchmark},{interference},{real},{user},{sys}\n'
    elif args.task == '2b':
        line = f'{now},{args.cluster_name},{benchmark},{n_threads},{real},{user},{sys}\n'
    else:
        raise ValueError(f'Invalid task: {args.task}')
    with open(args.output, 'a') as f:
        f.write(line)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run part 2 of the project', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-u', '--user', type=str, help='ETHZ user id', required=True, default=argparse.SUPPRESS)
    parser.add_argument('-t', '--task', type=str, choices=['2a', '2b'], help='Task to run', required=True, default=argparse.SUPPRESS)
    parser.add_argument('-p', '--project', type=str, default='cca-eth-2023-group-29', help='GCP project id')
    parser.add_argument('-d', '--cca-directory', type=str, default='cloud-comp-arch-project', help='Directory containing the project files')
    parser.add_argument('-c', '--cluster-name', type=str, default='part2a.k8s.local')
    parser.add_argument('-k', '--keep-alive', action='store_true', help='Keep cluster alive after running the task')
    parser.add_argument('-b', '--benchmarks', type=str, help='Benchmark to run', choices=['all'] + ALL_BENCHMARKS, nargs='+', required=False, default='all')
    parser.add_argument('-i', '--interferences', type=str, help='Interferences to create', choices=['all'] + ALL_INTERFERENCES, nargs='+', required=False, default='all')
    parser.add_argument('-w', '--wait-timeout', type=int, help='Timeout for running benchmarks in seconds', default=600)
    parser.add_argument('-n', '--n-threads', type=int, help='Number of threads to run the benchmarks with', choices=[1, 2, 4, 8], nargs='+', required=False, default=[1, 2, 4, 8])

    args = parser.parse_args()
    args.cluster_name = f'part{args.task}.k8s.local'
    args.output = f'results-{args.task}.csv'
    if not os.path.isdir(parser.parse_args().cca_directory):
        print(f"Directory {parser.parse_args().cca_directory} does not exist")
        sys.exit(1)
    if args.task == '2a':
        spin_up_cluster(args)
        run_part_2a(args)
        tear_down_cluster(args)
    elif args.task == '2b':
        spin_up_cluster(args)
        run_part_2b(args)
        tear_down_cluster(args)
    else:
        raise ValueError(f"Unknown task {args.task}")