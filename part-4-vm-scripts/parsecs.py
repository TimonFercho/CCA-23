import functools
import docker
import scheduler_logger
import time

schedule_logger = scheduler_logger.SchedulerLogger()

ALL_BENCHMARKS = [
    "blackscholes",
    "canneal",
    "dedup",
    "ferret",
    "freqmine",
    "radix",
    "vips",
]

blackscholes_dict = {"name":"blackscholes",
                     "docker_img":"anakli/cca:parsec_blackscholes",
                     "command": "./run -a run -S parsec -p blackscholes -i native -n 2",
                     "max_cores": 2,
                     "runtime": 0,
                     "interference": "something"
                     }

canneal_dict = {"name":"canneal",
                     "docker_img":"anakli/cca:parsec_canneal",
                     "command": "./run -a run -S parsec -p canneal -i native -n 3",
                     "max_cores": 3,
                     "runtime": 0,
                     "interference": "something"
                     }

dedup_dict = {"name":"dedup",
                     "docker_img":"anakli/cca:parsec_dedup",
                     "command": "./run -a run -S parsec -p dedup -i native -n 1",
                     "max_cores": 1,
                     "runtime": 0,
                     "interference": "something"
                     }

ferret_dict = {"name":"ferret",
                     "docker_img":"anakli/cca:parsec_ferret",
                     "command": "./run -a run -S parsec -p ferret -i native -n 2",
                     "max_cores": 2,
                     "runtime": 0,
                     "interference": "something"
                     }

freqmine_dict = {"name":"freqmine",
                     "docker_img":"anakli/cca:parsec_freqmine",
                     "command": "./run -a run -S parsec -p freqmine -i native -n 3",
                     "max_cores": 3,
                     "runtime": 0,
                     "interference": "something"
                     }

radix_dict = {"name":" radix",
                     "docker_img":"anakli/cca:splash2x_radix",
                     "command": "./run -a run -S splash2x -p radix -i native -n 1",
                     "max_cores": 1,
                     "runtime": 0,
                     "interference": "something"
                     }

vips_dict = {"name":"vips",
                     "docker_img":"anakli/cca:parsec_vips",
                     "command": "./run -a run -S parsec -p vips -i native -n 1",
                     "max_cores": 1,
                     "runtime": 0,
                     "interference": "something"
                     }

parsec_list = [blackscholes_dict, canneal_dict, dedup_dict, ferret_dict,freqmine_dict,radix_dict,vips_dict]


@functools.total_ordering
class ParsecJob:
    def __init__(self, name, docker_img, max_cores, runtime, interference):
        self.name = name 
        self.docker_img = docker_img
        self.max_cores = max_cores
        self.runtime = runtime
        self.interference = interference
        self.started = False
        self.paused = False
        self.accum_runtime = 0
        self.init_time = 0
        self.container = None
        self.cores = []

    # schedule list priority comparison
    def __eq__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return ((self.runtime, self.max_cores, self.paused) ==
                (other.runtime, other.max_cores, other.paused))
    
    def __gt__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return  (self.runtime >  other.runtime and self.max_cores > other.max_cores ) or (self.runtime ==  other.runtime and self.max_cores > other.max_cores ) 

    def set_container(self, container):
        self.container = container

    def pause(self):
        self.container.reload()
        if self.container.status in ["running", "restarting"]:
            self.container.pause()
            self.paused =True
            schedule_logger.job_pause(self.name)

            self.accum_runtime = self.accum_runtime + time.time() - self.init_time

    def start(self):
        self.container.reload()
        self.container.start()
        self.started =True
        schedule_logger.job_start(self.name)
        self.init_time = time.time()

    def update_cores(self, cpu_set):
        cpu_set_str = ','.join(cpu_set)
        self.container.update(cpuset_cpus=cpu_set)
        schedule_logger.update_cores(self.name, cores=cpu_set)
        self.cores = cpu_set

    def remove_core(self, core_num):
        self.cores.remove(core_num)
        paused = False
        if not self.cores:
            self.pause()
            paused = True
        self.update_cores(self.cores)
        return paused
    
    def add_core(self, new_core):
        self.cores.append(new_core)
        self.cores.sort()
        self.update_cores(self.cores)


    def unpause(self):
        self.container.reload()
        self.container.unpause()
        self.init_time = time.time()
        schedule_logger.job_unpause(self.name)

    def remove(self):
        if self.container.status == "exited":
            self.accum_runtime = self.accum_runtime + time.time() - self.init_time
        try:
            self.container.remove()
        except:
            self.container.reload()
            if self.container.status == "paused":
                self.container.unpause()

            if self.container.status == "running":
                self.container.kill()
                self.container.remove()
        
        schedule_logger.job_end(self.name)
        

class Schedule:
    def __init__(self, mc_cores, logger):

        self.mc_cores = mc_cores

        self.parsec_cores = range(mc_cores, 4)

        self.docker_client = docker.from_env()

        # stores the actual list of job wrapper object in sorted order according to job attributes
        self.job_list = [ParsecJob(job["name"], 
                                   job["docker_img"], 
                                   job["max_cores"], 
                                   job["runtime"],
                                   job["interference"]) for job in parsec_list]
        self.job_list.sort(reverse=True)

        for i , job in enumerate(self.job_list): 
            self.job_list[i].set_container( self.docker_client.containers.create(cpuset_cpus="1,2,3", name=job.name, detach=True,
                                                 auto_remove=False, image=job.docker_img,
                                                 command=job.command) )
            self.job_list[i].container.reload()

        # these lists store idx s mapping to locations of jobs in job_list
        self.running_jobs = [[],[],[]]
        self.paused_jobs = []
        # stores idx s mapping to locations of jobs in job_list
        self.completed_jobs = []

        self.job_priority_queue = range(len(self.job_list))


    def is_complete(self):
        if len(self.completed_jobs) == len(self.job_list):
            schedule_logger.end()
            return True
        return False

    def remove_all_containers(self):
        for i , job in enumerate(self.job_list): 
            self.job_list[i].remove()

    def clear_parsecs_on_core(self,core_num):

        core_int = int(core_num)
        for idx, job_id in enumerate(self.running_jobs[core_int]):
            paused = self.job_list[job_id].remove_core(core_num)
            #paused = self.job_list[idx].remove_core(core_num)
            if paused:
                self.paused_jobs.append(job_id)
                self.running_jobs[core_int].remove(job_id)

    def update_state(self):
        for core_int in range(self.running_jobs):
            for idx, job_id in enumerate(self.running_jobs[core_int]):
                if self.job_list[job_id].container.status == "exited":
                    self.job_list[job_id].remove()
                    #schedule_logger.job_end(self.job_list[job_id].container.name)
                    self.running_jobs[core_int].remove(job_id)
                    self.completed_jobs.add(job_id)


    # let parsec scheduling know whether memcached expanded to or retracted from core 1
    def update_for_memcached(self, mc_cores=1):

        if self.mc_cores < mc_cores:
            self.clear_parsecs_on_core("1")
            self.mc_cores = mc_cores
            self.parsec_cores = range(mc_cores, 4)
            return True

        elif self.mc_cores > mc_cores:
            self.mc_cores = mc_cores
            # map(str, range(mc_cores, 4))
            self.parsec_cores = range(mc_cores, 4)
            # new core freed up

            return False
        
        # memcached cores remained the same
        return False


    def update_internal_parsec(self, all_cpus_util):

        # cpu utilizations
        cpu_1, cpu_2, cpu_3 = all_cpus_util[1], all_cpus_util[2], all_cpus_util[3]

        cpu_1_free = self.mc_cores == 1 and ( not self.running_jobs[1] or cpu_1 < 50 )
        cpu_2_free = not self.running_jobs[2] or cpu_2 < 50
        cpu_3_free = not self.running_jobs[3] or cpu_3 < 50

        cpu_1_overloaded = cpu_1 > 85 and self.mc_cores == 1 # we dont touch it if its reserved for memcached
        cpu_2_overloaded = cpu_2 > 85
        cpu_3_overloaded = cpu_3 > 85

        free_core_set = []
        if cpu_1_free: free_core_set.append("1")
        if cpu_2_free: free_core_set.append("2")
        if cpu_3_free: free_core_set.append("3")

        # when we assign a new job to a core, we set it as altered and dont assign something else 
        # in the same round
        altered_cores = []

        # ------------------------------- REDUCING LOAD ON OVERLOADED CORES --------------------------------------
        # we only deschedule a job from an overloaded core if there are multile jobs on it

        for idx, overloaded in [cpu_1_overloaded, cpu_2_overloaded, cpu_3_overloaded]:
            if overloaded:
                core_num = idx + 1
                if len(self.running_jobs[core_num]) > 1:

                    last_running_id = len(self.running_jobs[core_num]) - 1
                    job_id = self.running_jobs[core_num][last_running_id]

                    allocated_cores = self.job_list[job_id].cores

                    # find potential cores to switch the job to 
                    remaining_cores = list(set(free_core_set) - set(allocated_cores))
                    remaining_cores = list(set(remaining_cores) - set(altered_cores))

                    # if no other ocres present to switch the job to, we pause it
                    if not remaining_cores:
                        self.job_list[job_id].pause()
                        self.paused_jobs.append(job_id)
                        self.running_jobs[core_num].remove(job_id)
                    # there are cores to switch to!
                    else:
                        # remove overloaded core
                        new_cores_set = set(allocated_cores) - str(core_num) 
                        # add new available core
                        new_cores_set.add(remaining_cores[0])
                        new_cores_list = list(new_cores_set)

                        self.job_list[job_id].update_cores(new_cores_list)
                        self.running_jobs[core_num].remove(job_id)
                        self.running_jobs[remaining_cores[0]].remove(job_id)

                        altered_cores.append(remaining_cores[0])

                    altered_cores.append(core_num)

                    if len(altered_cores) == len(free_core_set):
                        return




        # ------------------------------- UNPAUSING STAGE ---------------------------------------------------------
        # if there are paused jobs
        if self.paused_jobs:
            job_ids_to_remove = []
            for job_id in self.paused_jobs:

                # get remaining unassigned cores - maybe some cores were filled in previous iterations of the loop
                remaining_cores = list(set(free_core_set) - set(altered_cores))
                remaining_cores.sort()

                resource_demand =  self.job_list[job_id].max_cores
                # if job works with high core numbers, we require high core numbers to unpause it
                if resource_demand >= 2 and len(remaining_cores) >= 2:
                    self.job_list[job_id].update_cores(remaining_cores)
                    self.job_list[job_id].unpause()

                    # avoid modifying list while iterating
                    #self.paused_jobs.remove(job_id)
                    job_ids_to_remove.append(job_id)

                    altered_cores.extend(remaining_cores)

                    # adding job to running jobs of selected cores
                    for core_str in remaining_cores:
                        self.running_jobs[int(core_str)].append(job_id)
                    
                elif resource_demand == 1 and len(remaining_cores) >= 1:
                    # get remaining unassigned cores
                    self.job_list[job_id].update_cores(remaining_cores)

                    # avoid modifying list while iterating
                    #self.paused_jobs.remove(job_id)
                    job_ids_to_remove.append(job_id)

                    altered_cores.extend(remaining_cores) 

                    # adding job to running jobs of selected cores
                    for core_str in remaining_cores:
                        self.running_jobs[int(core_str)].append(job_id)

                if len(altered_cores) == len(free_core_set):
                    for id in job_ids_to_remove:
                        self.paused_jobs.remove(id)
                    return
                
            for id in job_ids_to_remove:
                self.paused_jobs.remove(id)

        
        # ------------------------------- EXPANDING LARGE JOBS STAGE ------------------------------------------------

        # if a job that needs 2 or 3 cores is left with 1 core, and there is a free core, we expand it

        remaining_cores = list(set(free_core_set) - set(altered_cores))

        for core_int in range(self.running_jobs):
            for idx, job_id in enumerate(self.running_jobs[core_int]):
                # if job wants 2 or 3 cores but only has one 
                if (len(self.job_list[job_id].cores) == 1 and self.job_list[job_id].max_cores >= 2) and remaining_cores:
                    #cores that the job can expand to, that are not already being used by the same job
                    expandable_cores = list(set(remaining_cores) - set(self.job_list[job_id].cores))
                    if expandable_cores:
                        self.job_list[job_id].add_core(expandable_cores[0])
                        self.running_jobs[expandable_cores[0]].append(job_id)
                        altered_cores.append(expandable_cores[0])

                        if len(altered_cores) == len(free_core_set):
                            return
                        # we altered this core, now we only look at other cores
                        break


        # ------------------------------- SCHEDULING NEW JOBS STAGE ----------------------------------------------------

        # if there are jobs yet to be scheduled for the first time
        if self.job_priority_queue:
            job_ids_to_remove = []
            for job_id in self.job_priority_queue:
                # get remaining unassigned cores - maybe some cores were filled in previous iterations of the loop
                remaining_cores = list(set(free_core_set) - set(altered_cores))
                remaining_cores.sort()

                resource_demand =  self.job_list[job_id].max_cores
                # if job works with high core numbers, we require high core numbers to unpause it
                if resource_demand >= 2 and len(remaining_cores) >= 2:
                    self.job_list[job_id].update_cores(remaining_cores)
                    self.job_list[job_id].start()

                    # avoid modifying list while iterating
                    #self.job_priority_queue.remove(job_id)
                    job_ids_to_remove.append(job_id)

                    altered_cores.extend(remaining_cores)

                    # adding job to running jobs of selected cores
                    for core_str in remaining_cores:
                        self.running_jobs[int(core_str)].append(job_id)
                    
                elif resource_demand == 1 and len(remaining_cores) >= 1:
                    # get remaining unassigned cores
                    self.job_list[job_id].update_cores(remaining_cores)

                    # avoid modifying list while iterating
                    #self.job_priority_queue.remove(job_id)
                    job_ids_to_remove.append(job_id)

                    altered_cores.extend(remaining_cores) 

                    # adding job to running jobs of selected cores
                    for core_str in remaining_cores:
                        self.running_jobs[int(core_str)].append(job_id)

                if len(altered_cores) == len(free_core_set):
                    for id in job_ids_to_remove:
                        self.job_priority_queue.remove(id)
                    return
            for id in job_ids_to_remove:
                self.job_priority_queue.remove(id)

        # ------------------------------- EXPANDING SMALL JOBS STAGE ------------------------------------------------

        # if after all other opreations of unpausing, expanidng, new job scheduling etc, there is still a free core
        #and there are no large jobs le

        remaining_cores = list(set(free_core_set) - set(altered_cores))

        for core_int in range(self.running_jobs):
            for idx, job_id in enumerate(self.running_jobs[core_int]):
                # if job wants 2 or 3 cores but only has one 
                if (len(self.job_list[job_id].cores) == 1 and self.job_list[job_id].max_cores >= 2) and remaining_cores:
                    #cores that the job can expand to, that are not already being used by the same job
                    expandable_cores = list(set(remaining_cores) - set(self.job_list[job_id].cores))
                    if expandable_cores:
                        self.job_list[job_id].add_core(expandable_cores[0])
                        self.running_jobs[expandable_cores[0]].append(job_id)
                        altered_cores.append(expandable_cores[0])

                        if len(altered_cores) == len(free_core_set):
                            return
                        # we altered this core, now we only look at other cores
                        break
