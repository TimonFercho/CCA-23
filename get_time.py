import json
import sys
from datetime import datetime
import pandas as pd

ALL_BENCHMARKS = [
    "blackscholes",
    "canneal",
    "dedup",
    "ferret",
    "freqmine",
    "radix",
    "vips",
]

parsec_df = pd.DataFrame({'name': ALL_BENCHMARKS,
                            "start_time": [0]*len(ALL_BENCHMARKS),
                            "end_time": [0]*len(ALL_BENCHMARKS)})


def get_time(filepath):
    time_format = '%Y-%m-%dT%H:%M:%SZ'
    file = open(filepath, 'r')
    json_file = json.load(file)

    start_times = []
    completion_times = []
    names = []
    for item in json_file['items']:
        name = item['status']['containerStatuses'][0]['name']
        print("Job: ", str(name))
        if str(name) != "memcached":
            try:
                start_time = datetime.strptime(
                        item['status']['containerStatuses'][0]['state']['terminated']['startedAt'],
                        time_format)
                completion_time = datetime.strptime(
                        item['status']['containerStatuses'][0]['state']['terminated']['finishedAt'],
                        time_format)
                print("Job time: ", completion_time - start_time)
                start_times.append(start_time)
                completion_times.append(completion_time)
                names.append(name)
            except KeyError:
                print("Job {0} has not completed....".format(name))
                sys.exit(0)

    if len(start_times) != 7 and len(completion_times) != 7:
        print("You haven't run all the PARSEC jobs. Exiting...")
        sys.exit(0)


    ref_time = min(start_times)

    #parsec_df.to_csv('parsec_times.csv')

    print("Total time: {0}".format(max(completion_times) - min(start_times)))
    file.close()

    return  pd.DataFrame({'name': names,
                            "start": [t - ref_time for t in start_times],
                            "end": [t - ref_time for t in completion_time]  })
if __name__ == '__main__':
    get_time(sys.argv[1])
