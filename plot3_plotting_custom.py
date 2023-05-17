import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import random

# START OF DUMMY DATA CREATION
jobs = {
    "name": ["blackscholes", "dedup", "radix"],
    "start_time": [0, 1, 0],
    "end_time": [1, 3, 4],
    "machine": ["1", "1", "2"],
}
jobs_df = pd.DataFrame(data=jobs)

memcached = {"start_time": [], "end_time": [], "latency": []}

width = 1
for i in range(0, 16, width):
    memcached["start_time"].append(i / 4)
    memcached["end_time"].append((i + width) / 4)
    memcached["latency"].append(random.uniform(4, 6))

memcached_df = pd.DataFrame(data=memcached)

# END OF DUMMY DATA CREATION

"""
========= PLOTTING MEMCACHED ===========
"""
for index, row in memcached_df.iterrows():
    start_time = row["start_time"]
    end_time = row["end_time"]
    latency = row["latency"]
    wd = end_time - start_time
    plt.bar(
        start_time,
        latency,
        width=wd,
        color="#07457C",
        edgecolor="black",
        align="edge",
        alpha=0.7,
    )


"""
========= PLOTTING PARSEC BENCHMARKS ===========
"""
# dictonaries for color values
color_dictionary = {
    "blackscholes": "#CCA000",
    "canneal": "#CCCCAA",
    "dedup": "#CCACCA",
    "ferret": "#AACCCA",
    "freqmine": "#0CCA00",
    "radix": "#00CCA0",
    "vips": "#CC0A00",
}

# get minimum start and ends times from absolute
min_start_time = jobs_df.min()["start_time"]
max_end_time = jobs_df.max()["end_time"]
total_time = max_end_time - min_start_time

# keep track of current values already graphed to ensure no overlap
curr_vals = set()

for job, line_color in color_dictionary.items():
    if job in set(jobs_df["name"]):
        start_time = jobs_df.loc[jobs_df["name"] == job].iloc[0]["start_time"]
        end_time = jobs_df.loc[jobs_df["name"] == job].iloc[0]["end_time"]

        # help offset the lines in case of overlap
        while start_time in curr_vals:
            start_time += total_time / 100
        curr_vals.add(start_time)
        while end_time in curr_vals:
            end_time += total_time / 1000
        curr_vals.add(end_time)

        # plot lines
        machine = jobs_df.loc[jobs_df["name"] == job].iloc[0]["machine"]
        plt.axvline(
            x=start_time,
            label=job + f" (Machine {machine})",
            ymin=0,
            ymax=1,
            color=line_color,
            linewidth=2.5,
        )
        plt.axvline(x=end_time, ymin=0, ymax=1, color=line_color, linewidth=2.5)

# basic plot elements
plt.title(
    "p95 Latency of memcached vs Time, with Start and End Times of PARSEC Benchmarks",
    y=1.08,
)
plt.xlabel("time [s]")
plt.ylabel("p95 latency [ms]")

# creating the custom legend
md = mpatches.Patch(color="#07457C", label="memcached")
patches = [md]
for job, line_color in color_dictionary.items():
    if job in set(jobs_df["name"]):
        machine = jobs_df.loc[jobs_df["name"] == job].iloc[0]["machine"]
        temp_line = Line2D(
            [0], [0], color=line_color, label=job + f" (Machine {machine})", lw=2.5
        )
        patches.append(temp_line)
plt.legend(handles=patches, loc=3, bbox_to_anchor=(1, 0))

plt.savefig("part3_plot.png", bbox_inches="tight")
