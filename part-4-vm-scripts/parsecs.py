import functools
import docker

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
                     "command":
                     "max_cores": 0,
                     "runtime": 0,
                     "interference": "something"
                     }

canneal_dict = {"name":"canneal",
                     "docker_img":"anakli/cca:parsec_canneal",
                     "command":
                     "max_cores": 0,
                     "runtime": 0,
                     "interference": "something"
                     }

dedup_dict = {"name":"dedup",
                     "docker_img":"anakli/cca:parsec_dedup",
                     "command":
                     "max_cores": 0,
                     "runtime": 0,
                     "interference": "something"
                     }

ferret_dict = {"name":"ferret",
                     "docker_img":"anakli/cca:parsec_ferret",
                     "command":
                     "max_cores": 0,
                     "runtime": 0,
                     "interference": "something"
                     }

freqmine_dict = {"name":"freqmine",
                     "docker_img":"anakli/cca:parsec_freqmine",
                     "command":
                     "max_cores": 0,
                     "runtime": 0,
                     "interference": "something"
                     }

radix_dict = {"name":" radix",
                     "docker_img":"anakli/cca:splash2x_radix",
                     "command": "./run -a run -S splash2x -p radix -i native -n 8"
                     "max_cores": 0,
                     "runtime": 0,
                     "interference": "something"
                     }

vips_dict = {"name":"vips",
                     "docker_img":"anakli/cca:parsec_vips",
                     "command":
                     "max_cores": 0,
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
        self.container = None

    # schedule list priority comparison
    def __eq__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return ((self.runtime, self.max_cores) ==
                (other.runtime, other.max_cores))
    
    def __gt__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return  (self.runtime >  other.runtime and self.max_cores > other.max_cores ) or (self.runtime ==  other.runtime and self.max_cores > other.max_cores ) 

    def set_container(self, container):
        self.container = container

class Schedule:
    def __init__(self):

        self.docker_client = docker.from_env()

        self.job_queue = [ParsecJob(job["name"], job["docker_img"], job["max_cores"], job["runtime"]) for job in parsec_list]
        self.job_queue.sort(reverse=True)

        for i , job in enumerate(self.job_queue): 
            self.job_queue[i].set_container = self.docker_client.containers.create(cpuset_cpus="0,1,2,3", name=job.name, detach=True,
                                                 auto_remove=False, image=job.docker_img,
                                                 command=job.command)


        self.running_jobs = []
        self.paused_jobs = []
        self.completed_jobs = []
        


ferret = ("0,1,2,3",
          "ferret",
          "anakli/parsec:ferret-native-reduced",
          "./bin/parsecmgmt -a run -p ferret -i native -n 3")
