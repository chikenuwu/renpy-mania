define config.developer = True

# --- PUT THESE IN SCREENS.RPY FOR ADJUSTABLE SETTINGS ---
default fps = 60.0
default rg_approach_ms = 500
# --------------------- 


# game variables
default rg_score = 0
default rg_combo = 0
default rg_max_combo = 0
default rg_last = ""

default rg_notes = [] # list of notes
default rg_fx = [] # list[{lane,start_ms,end_ms,color}]
default rg_song_started = False
default rg_tick = False
#default rg_approach_ms = 500 # ms notes travel on screen
default rg_travel_px = 620
default rg_hitline_y = 620 # inside a 660px play area
default rg_lane_w = 120
default rg_lane_gap = 12
default rg_lanes = 4
default rg_keys = ["d", "f", "j", "k"]
default default_rg_clock_ms = 0 # fallback "song clock" if music pos is None (i usually just used this for testing when i didnt import a song)
default rg_held = [False, False, False, False] # lane press/hold state
default rg_chart_text = "" # generated output (for popup/copy)
default rg_last_song_time_ms = 0

# note colors n shi (we dont use the ones for hold, but yk uhhh good reference ig)
image rg_note_rect = Solid("#51befc")
image rg_hold_long = Solid("#51befc")
image rg_note_rect_1_4 = Solid("#fd4bb3")
image rg_hold_long_1_4 = Solid("#fd4bb3")

style monospace:
    size 18
style combo_style:
    font "fonts/BoldPixels.ttf"
    size 75

style keys:
    font "fonts/BoldPixels.ttf"
    size 25

style score_style:
    font "fonts/BoldPixels.ttf"
    size 28

# logic stuff and qol for me
init 10 python:
    from renpy.audio import music as RMusic
    import renpy.store as store
    from renpy.display.layout import DynamicDisplayable
    from renpy.display.transform import Transform
    from renpy.easy import displayable
    import os, time, subprocess
    
    PERFECT_MS = 90
    GOOD_MS = 160
    MISS_MS = GOOD_MS
    RELEASE_PERFECT_MS = 90
    RELEASE_GOOD_MS = 160
    HIT_MAX_MS = GOOD_MS #ghost tap
    GHOST_FX_MS = 80

# --- NOTES + ACCURACY LOGIC ---
    #For building notes based off chart script (chart1.rpy)
    def build_notes(seq):
        out = []
        for item in seq:
            kind = item[0]
            if kind == "tap":
                _, t, lane = item
                out.append(Note(t, lane))
            elif kind == "hold":
                _, t0, t1, lane = item
                out.append(HoldNote(t0, t1, lane))
        return out

    def rg_song_time_ms():
        """
        Return current song time in ms
        Go do default if music pos is None
        """
        pos = RMusic.get_pos("music")
        if pos is not None:
            return int(pos * 1000) #convert to milliseconds
        # If we've already seen real music time once, just freeze there
        if store.rg_last_song_time_ms > 0:
            return store.rg_last_song_time_ms
    def rg_note_y(note, song_ms):
        """
        Map time -> y so that:
        delta == rg_approach_ms -> y = 0 (top)
        delta == 0 -> y = hitline
        """
        delta = note.time_ms - song_ms
        if delta >= rg_approach_ms:
            return 0.0
        if delta <= 0:
            return float(rg_hitline_y - 18)
        frac = 1.0 - (delta / float(rg_approach_ms))
        return frac * float(rg_hitline_y - 18)
    def rg_add_fx(lane, kind):
        now = rg_song_time_ms()
        dur = 160 if kind == "perfect" else 120
        if kind == "perfect":
            dur, color = 160, "#8cf"
        elif kind == "good":
            dur, color = 120, "#6bf"
        else: #ghost tap
            dur, color = GHOST_FX_MS, "#9aa" 
        store.rg_fx.append(dict(lane=lane, start_ms=now, end_ms=now + dur, color=color))
    def rg_auto_miss_pass():
        """
        Mark overdue notes as MISS and clear expired FX
        """
        t = rg_song_time_ms()
        missed = False

        for n in rg_notes:
            if rg_is_hold(n):
                # Only judge once!
                if (not n.judged) and (not n.head_judged) and (t - rg_hold_head_time(n) > MISS_MS):
                    n.judged = True
                    n.result = "miss"
                    n.done = True
                    missed = True
                elif (not n.judged) and n.started and (not n.tail_judged) and (t - rg_hold_tail_time(n) > MISS_MS):
                    n.judged = True
                    n.result = "miss"
                    n.done = True
                    missed = True
            else:
                if (not n.judged) and (t - n.time_ms > MISS_MS):
                    n.judged = True
                    n.result = "miss"
                    missed = True

        if missed:
            global rg_combo, rg_last
            rg_combo = 0
            rg_last = "MISS"

        # clear expired FX
        store.rg_fx[:] = [fx for fx in store.rg_fx if fx["end_ms"] > t]
    def rg_cleanup_notes():
        """
        Remove notes that are fully judged and no longer visible
        to keep rg_notes small and efficient.
        """
        now = rg_song_time_ms()
        keep = []
        for n in rg_notes:
            if rg_is_hold(n):
                # Keep if not finished or still visible
                if not n.done or rg_visible_hold(n, now):
                    keep.append(n)
            else:
                # Keep if not judged yet or still visible (for miss fade)
                if not n.judged or rg_visible_tap(n, now):
                    keep.append(n)
        store.rg_notes[:] = keep

    #BASIC NOTE LOGIC
    class Note:
        def __init__(self, time_ms, lane):
            self.time_ms = int(time_ms)
            self.lane = int(lane)
            self.judged = False
            self.result = None  # "perfect"/"good"/"miss"

    def rg_try_hit(lane):
        """
        Attempt to judge a note hit in the given lane (tap or hold head).
        If no candidate is within HIT_MAX_MS do nothing.
        If both early and late notes are in range, prioritize the late note.
        """
        global rg_score, rg_combo, rg_max_combo, rg_last
        t = rg_song_time_ms()

        candidates = []
        for n in rg_notes:
            if n.lane != lane:
                continue

            if rg_is_hold(n):
                # only the head is hittable before it's started
                if (not n.judged) and (not n.head_judged):
                    target = rg_hold_head_time(n)
                    signed_dt = t - target          # >0 = late, <0 = early
                    abs_dt = abs(signed_dt)
                    candidates.append((abs_dt, signed_dt, n, "hold_head"))
            else:
                if not n.judged:
                    target = n.time_ms
                    signed_dt = t - target          # >0 = late, <0 = early
                    abs_dt = abs(signed_dt)
                    candidates.append((abs_dt, signed_dt, n, "tap"))

        # ghost tap (no notes in this lane at all)
        if not candidates:
            rg_last = ""
            rg_add_fx(lane, "ghost")
            return

        # Sort by:
        # 1) smallest absolute distance
        # 2) for ties, prefer late notes (signed_dt >= 0) over early (signed_dt < 0)
        # x rn looks like this (abs_dt, signed_dt, n, type)
        candidates.sort(key=lambda x: (x[1] < 0, x[0])) #prioritizes positive(late) times first
        # for sorts, false comes before true bc 0<1
        # avfter that... 
        #Among all late notes: choose the closest
        #Among all early notes: choose the closest

        abs_dt, signed_dt, n, kind = candidates[0]
        dt = abs_dt

        # ghost tap (closest note is still outside hit window)
        if dt > HIT_MAX_MS:
            rg_last = ""
            rg_add_fx(lane, "ghost")
            return

        # normal judgement for when inside the window
        if kind == "tap":
            if dt <= PERFECT_MS:
                n.judged = True; n.result = "perfect"
                rg_score += 1000; rg_combo += 1
                rg_max_combo = max(rg_max_combo, rg_combo)
                rg_last = "PERFECT"; rg_add_fx(lane, "perfect")
            elif dt <= GOOD_MS:
                n.judged = True; n.result = "good"
                rg_score += 500; rg_combo += 1
                rg_max_combo = max(rg_max_combo, rg_combo)
                rg_last = "GOOD"; rg_add_fx(lane, "good")
            return

        # hold head:
        if dt <= PERFECT_MS:
            n.head_judged = True; n.started = True
            rg_score += 500; rg_combo += 1
            rg_max_combo = max(rg_max_combo, rg_combo)
            rg_last = "PERFECT"; rg_add_fx(lane, "perfect")
        elif dt <= GOOD_MS:
            n.head_judged = True; n.started = True
            rg_score += 250; rg_combo += 1
            rg_max_combo = max(rg_max_combo, rg_combo)
            rg_last = "GOOD"; rg_add_fx(lane, "good")

    def rg_spawn_note(lane, at_ms=None):
        """
        Spawn a note in lane (0..3) that hits at at_ms (or 1s from now but why wouldnt u have a parameter there)
        """
        now = rg_song_time_ms()
        hit_at = int(at_ms) if at_ms is not None else (now + 1000)
        store.rg_notes.append(Note(hit_at, lane))

    def rg_visible_tap(note, now_ms):
        """
        Show a tap note only when it's within the approach window ahead of hit time,
        and until just past the miss window after.
        """
        d = note.time_ms - now_ms
        return (-MISS_MS <= d <= rg_approach_ms)

    #HOLD NOTE LOGIC
    class HoldNote(Note):
        def __init__(self, start_ms, end_ms, lane):
            super().__init__(start_ms, lane)
            self.end_ms = int(end_ms)
            self.duration = int(end_ms-start_ms)
            self.head_judged = False
            self.tail_judged = False
            self.started = False   # became “held” after head was hit
            self.done = False      # both ends judged

    def rg_is_hold(n):
        """
        see if the note is a hold note to apply logic
        """
        return isinstance(n, HoldNote)

    def rg_hold_head_time(n):
        """
        return the timestamp when a hold note should begin being pressed
        """
        return n.time_ms

    def rg_hold_tail_time(n):
        """
        return the timestamp when a hold note should be released
        """
        return n.end_ms

    def rg_spawn_hold(lane, length_ms=600, at_ms=None):
        """
        Spawn a hold note starting at at_ms (from now) and lasting length_ms
        """
        now = rg_song_time_ms()
        start = int(at_ms) if at_ms is not None else (now + 1000)
        end = start + int(length_ms)
        store.rg_notes.append(HoldNote(start, end, lane))

    def rg_visible_hold(note, now_ms):
        """
        Show a hold note when any part of it is in-range:
        - head is within approach window, OR
        - body overlaps the playfield, OR
        - tail hasn't gone past miss window yet.
        """
        head_d = note.time_ms - now_ms
        tail_d = note.end_ms - now_ms
        return (head_d <= rg_approach_ms) and (tail_d >= -MISS_MS)

    def rg_release(lane):
        """
        function is called whenever the player releases a key in the given lane
        """
        #print("DOES THIS SHIT EVEN WORK")
        global rg_score, rg_combo, rg_max_combo, rg_last
        t = rg_song_time_ms()

        # find started but unfinished hold in lane
        active = [n for n in rg_notes
                if rg_is_hold(n) and n.lane == lane and n.started and (not n.tail_judged)]
        if not active:
            return

        #among all unfinished holds in this lane, find the one whose tail time is closest to the current song time (t)
        n = min(active, key=lambda hn: abs(rg_hold_tail_time(hn) - t))
        #compute the absolute time difference (in ms) between now and when this hold’s tail should be hit.
        dt = abs(rg_hold_tail_time(n) - t)

        if dt <= RELEASE_PERFECT_MS:
            n.tail_judged = True; n.done = True; n.judged = True; n.result = "perfect"
            rg_score += 1000; rg_combo += 1
            rg_max_combo = max(rg_max_combo, rg_combo)
            rg_last = "PERFECT"; rg_add_fx(lane, "perfect")
        elif dt <= RELEASE_GOOD_MS:
            n.tail_judged = True; n.done = True; n.judged = True; n.result = "good"
            rg_score += 500; rg_combo += 1
            rg_max_combo = max(rg_max_combo, rg_combo)
            rg_last = "GOOD"; rg_add_fx(lane, "good")
        else:
            # finalize as miss so it can’t be retried
            n.tail_judged = True; n.done = True; n.judged = True; n.result = "miss"
            rg_combo = 0; rg_last = "MISS"

    def rg_set_hold(lane, is_down):
        # Update the 'held' state for a specific lane
        store.rg_held[lane] = bool(is_down)



    # Notes that epositions every ~10ms
    # keep in mind our accuracy scores and stuff are based off musictiming, NOT visually
    def dd_note(st, at, note):
        now = rg_song_time_ms()
        y = rg_note_y(note, now)
        lane_x = note.lane * (rg_lane_w + rg_lane_gap) + 10
        if note.lane in (0,3):
            base = displayable("rg_note_rect_1_4")
        else:
            base = displayable("rg_note_rect")
        disp = Transform(base, xsize=rg_lane_w - 20, ysize=36, xoffset=lane_x, yoffset=y)
        return disp, 1.0/fps # update every 10 ms for animation until it is no longer rendered
    def dd_hold(st, at, note):
        now = rg_song_time_ms()
        TOP_CLIP = 0.0
        BOT_CLIP = float(rg_hitline_y - 18)

        # start and end that i called head and tail
        y_head = rg_note_y(note, now)
        class _Tail: ... #create a throwaway class that just lets us use some methods for the tail(treat it as anotehr note)
        _t = _Tail(); _t.time_ms = note.end_ms; _t.lane = note.lane
        y_tail = rg_note_y(_t, now)

        # clamp the long notes to INSIDE the playing field
        y0 = max(TOP_CLIP, min(y_tail, BOT_CLIP))  # top
        y1 = max(TOP_CLIP, min(y_head, BOT_CLIP))  # bottom

        #ITS SUPPOSED TO BE AN INTEGER AHAHAHHA I MADE IT A FLOAT FOR PRECISON AND THAT MADE IT TWEAK THE FUCK OUT AND I THOUGHT IT WAS A VISUAL BUG BUT NOOOOOOOOOO THIS ENGINES JUST ASS
        y0_i = int(round(y0))
        y1_i = int(round(y1))
        height = max(0, y1_i - y0_i)

        # lane geometry
        lane_x = int(note.lane * (rg_lane_w + rg_lane_gap) + 10)
        lane_w = int(rg_lane_w - 20)

        # make lane chaneg color
        try: # see if we're holding the lane/note
            is_held_now = store.rg_held[note.lane]
        except Exception:
            is_held_now = False

        #choose what color to render
        if not note.started:
            if note.lane in (0,3):
                body_color = "#fd4bb3"
            else:
                body_color = "#51befc" #base color
            body_alpha = 1
        else:
            if is_held_now and not note.done:
                if note.lane in (0,3):
                    body_color = "#fc9fec"
                else:
                    body_color = "#8becfe" #base color
                body_alpha = 1
            else:
                if note.lane in (0,3):
                    body_color = "#a8719f" #not holding :( color
                else:
                    body_color = "#82b8c2" #not holding :( color
                body_alpha = 1

        group = renpy.display.layout.Fixed()

        if height >= 1:
            group.add(Transform(
                Solid(body_color), alpha=body_alpha,
                xsize=lane_w, ysize=height+32,
                xoffset=lane_x, yoffset=y0_i
            ))

        return group, 1.0/fps




# RENDERING + UI
screen rhythm_game():

    key "game_menu" action ShowMenu("preferences", rhythm_pause=True)
    
    fixed:
        xalign 0.5
        yalign 0.5
        xsize (rg_lanes * rg_lane_w + (rg_lanes - 1) * rg_lane_gap)
        ysize 660
        clipping True

    # top hud
    hbox:
        xpos 0.7
        yalign 0.55
        spacing 24
        xanchor 0.5
        # text at the top with fixed width
        text ("[rg_last]")style "score_style"


    hbox:
        xpos 0.71
        yalign 0.135
        xanchor 0.5
        text ("[rg_score]")style "score_style"

    vbox:
        xpos 0.7
        yalign 0.5
        spacing 24
        xanchor 0.5
        text ("[rg_combo]") size 75 style "combo_style"

    # heartbeat
    timer 1.0/fps repeat True action [
        #these are important bc theyre "screen" vaiables
        # basically what that means is it forces renpy to check the screen to see what to update
        # tldr: rg_tick forces renpy to update its screen
        SetVariable("rg_tick", not rg_tick),
        SetVariable("default_rg_clock_ms", default_rg_clock_ms + 1000.0/fps), #every 16.66ms ish)
        Function(rg_auto_miss_pass), #checks what notes to flag as a miss
        Function(rg_cleanup_notes), #clears up the array while ur playing to reduce lag a lil
    ]

    # Press = set held -> log -> try_hit
    key "d" action [ Function(rg_set_hold, 0, True), Function(rg_try_hit, 0) ]
    key "f" action [ Function(rg_set_hold, 1, True), Function(rg_try_hit, 1) ]
    key "j" action [ Function(rg_set_hold, 2, True), Function(rg_try_hit, 2) ]
    key "k" action [ Function(rg_set_hold, 3, True), Function(rg_try_hit, 3) ]

    # Key-up = judge release -> log -> clear held bool
    key "keyup_K_d" action [ Function(rg_release, 0), Function(rg_set_hold, 0, False) ]
    key "keyup_K_f" action [ Function(rg_release, 1), Function(rg_set_hold, 1, False) ]
    key "keyup_K_j" action [ Function(rg_release, 2), Function(rg_set_hold, 2, False) ]
    key "keyup_K_k" action [ Function(rg_release, 3), Function(rg_set_hold, 3, False) ]

    key "mouseup_1" action NullAction()

    # playing rectangle
    frame:
        xalign 0.5
        yalign 0.5
        xsize (rg_lanes * rg_lane_w + (rg_lanes ) * rg_lane_gap)
        ysize 700
        has vbox

        null height 8  # small spacer

        fixed:
            xalign 0.5
            yalign 0.5
            xsize (rg_lanes * rg_lane_w + (rg_lanes - 1) * rg_lane_gap)
            ysize 680

            # lanes (4k only sry mania bros)
            for i in range(rg_lanes):
                frame:
                    xpos i * (rg_lane_w + rg_lane_gap)
                    ypos 0
                    xsize rg_lane_w
                    ysize 680
                    background "#2228"
                    text rg_keys[i].upper() xalign 0.5 ypos (rg_hitline_y + 8) style "keys"

            # judgement hints (i need them for hitbox testing rn)
            $ px_per_ms = float(rg_hitline_y - 18) / float(rg_approach_ms)
            $ perf_px = int(round(PERFECT_MS * px_per_ms))
            $ good_px = int(round(GOOD_MS * px_per_ms))
            $ total_w = (rg_lanes * rg_lane_w + (rg_lanes - 1)*rg_lane_gap)

            # # GOOD hint
            # add Solid("#ffff0040"):  # translucent yellow
            #     xpos 0
            #     ypos rg_hitline_y - good_px
            #     xsize total_w
            #     ysize (2 * good_px)

            # PERFECT hint
            # add Solid("#00ff0044"):  # translucent green
            #     xpos 0
            #     ypos rg_hitline_y - perf_px
            #     xsize total_w
            #     ysize (2 * perf_px)

            # hit line (if this is at center of note yk its at perfect)
            add Solid("#f05078") xpos 0 ypos rg_hitline_y - 14 xsize total_w ysize 5



            # vfx for notes
            $ now = rg_song_time_ms()
            for fx in rg_fx:
                $ lane = fx["lane"]
                $ dur = fx["end_ms"] - fx["start_ms"]
                $ rem = max(0, fx["end_ms"] - now)
                $ a = float(rem) / float(dur) if dur > 0 else 0.0
                add Transform(Solid(fx["color"]), alpha=a):
                    xpos lane * (rg_lane_w + rg_lane_gap)
                    ypos rg_hitline_y - 38
                    xsize rg_lane_w
                    ysize 48

            # spawning notes
            for n in rg_notes:
                if isinstance(n, HoldNote):
                    # keep drawing if it was a miss and hide when done
                    if n.done and n.result != "miss":
                        continue
                    if not rg_visible_hold(n, now): #hide if its not its turn
                        continue
                    add DynamicDisplayable(dd_hold, n)
                else:
                    if n.judged:
                        continue # doesnt count already hit notes(aka doesnt render them)
                    if not rg_visible_tap(n, now): #hide if its not its turn
                        continue
                    add DynamicDisplayable(dd_note, n)
