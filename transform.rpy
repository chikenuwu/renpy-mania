transform layer_blur_in(rad=28, dur=0.25):
    blur 0
    linear dur blur rad

transform layer_blur_out(rad=28, dur=0.25):
    blur rad
    linear dur blur 0

transform slide_pop_to(xp=0.14, yp=-0.05, t_in=0.35):
    subpixel True
    zoom 0.95
    xpos xp
    ypos yp
    yoffset 1200                    # start off-screen below
    linear (2*t_in)/3 yoffset -50
    linear (1*t_in)/3 yoffset -0.05

transform fade_in_overlay(t_in=0.25):
    subpixel True
    alpha 0.0
    linear t_in alpha 1.0

transform slide_pop_hide(t_out=0.25):
    subpixel True
    linear t_out alpha 0.0 yoffset 100

transform center_anchor:
    anchor (0.5, 0.5)
    align (0.75, 0.15)