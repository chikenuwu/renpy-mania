init python:
    import renpy.exports as renpyx
    from renpy.display.transform import Transform

    def set_layer_blur(layer_name="master", radius=0, dur=0.25):
        """
        Smoothly animate the given layer's blur to `radius` over `dur` seconds.
        """
        if radius and radius > 0:
            renpyx.show_layer_at([ renpy.store.layer_blur_in(radius, dur) ], layer=layer_name)
        else:
            renpyx.show_layer_at([ renpy.store.layer_blur_out(0, dur) ], layer=layer_name)


transform dim_fade_in(strength=0.60, dur=0.25):
    alpha 0.0
    linear dur alpha strength
    on hide:
        linear dur alpha 0.0
screen rhythm_dim(strength=0.60, dur=0.25):
    add Solid("#000") at dim_fade_in(strength, dur)

label play_rhythm_game(song="audio/songs/pacchu.mp3", chart=None, minscore = 0):
    # Ease in blur + dim
    $ set_layer_blur("master", 12, dur=0.25)
    show screen rhythm_dim(strength=0.65, dur=0.25)


    show has_screen onlayer screens at slide_pop_to(yp = -0.05)
    $ renpy.pause(0.43, hard=True)   # let the slide finish before stacking the rest

    $ RMusic.play(song, channel="music", loop=False, synchro_start=True, fadein=0.0)
    $ rg_song_started = True
    $ renpy.pause(0.05, hard=True)

    $ base = rg_song_time_ms() + rg_approach_ms + 800
    if chart is None:
        $ rg_notes = build_notes(rg_chart1)
    else:
        $ rg_notes = build_notes(chart)

    $ rg_score = 0
    $ rg_combo = 0
    $ rg_max_combo = 0
    show screen rhythm_game
    show no_screen onlayer screens:
        zoom 0.95
        xpos 0.14
        ypos -0.05
    window hide
    $ song_len = RMusic.get_duration("music")
    # $ renpy.fix_rollback()
    # $ renpy.block_rollback()
    $ renpy.pause(song_len + 0.5, 
    # hard = True
    )
    $ min_scored = rg_score >= minscore

    hide screen rhythm_game
    window show
    hide has_screen onlayer screens
    hide no_screen onlayer screens
    hide screen rhythm_dim  # fades out via on hide
    $ set_layer_blur("master", 0, dur=0.25)
    return min_scored
