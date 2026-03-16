import zipfile
import math
# pylint: skip-file
# mypy: ignore-errors

def parse_osu_to_tuples(osu_path):
    events = []
    with open(osu_path, encoding="utf-8") as f:
        lines = f.readlines()
    
    hit_objects = False
    for line in lines:
        if line.strip() == "[HitObjects]":
            hit_objects = True
            continue
        if not hit_objects or not line.strip():
            continue
        
        parts = line.strip().split(",")
        if len(parts) < 5:
            continue

        #https://osu.ppy.sh/wiki/en/Client/File_formats/osu_%28file_format%29#hit-objects 
        #ignore y for mania!!! uwu
        x, y, time, obj_type, *_ = parts
        obj_type = int(obj_type)
        time = int(time)

        #It is computed by floor(x * columnCount / 512) and clamped between 0 and columnCount - 1.
        lane = (math.floor((int(x) * 4) / 512))  # just 4k
        if lane < 0:
            lane = 0
        elif lane > 3:
            lane = 3

        if obj_type & 128:  # mania hold https://osu.ppy.sh/wiki/en/Client/File_formats/osu_%28file_format%29#type
            #last element(5) is like 6174:0:0:0:
            #split to ['6174', '0', '0', '0', '']
            # get 0th element from that which is 6174
            # https://osu.ppy.sh/wiki/en/Client/File_formats/osu_%28file_format%29#holds-(osu!mania-only) 
            end_time = int(parts[5].split(":")[0])
            events.append(("hold", time, end_time, lane))
        else:
            events.append(("tap", time, lane))
    return events

events = parse_osu_to_tuples("osu/marshmary.osu")
for e in events:
    print(e, ",")

#parse
to_save = ""
for e in events:
    if e[0] == 'tap':
        to_save += f"('{e[0]}', {e[1]}, {e[2]}),\n"
    else:
        to_save += f"('{e[0]}', {e[1]}, {e[2]}, {e[3]}),\n"

with open("output.txt", "w") as file:
    file.write(to_save)