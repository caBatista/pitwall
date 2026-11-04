from pitwall.simwindow import HOLD, KEYUP, Watch, press_alt_enter

OTHER, SIM = 1, 2


def rig(windowed=True, start=OTHER):
    s = {"front": start, "windowed": windowed, "presses": 0}

    def press():
        s["presses"] += 1

    return s, Watch(lambda: s["front"], lambda h: h == SIM, lambda h: s["windowed"], press, wait=lambda _: None)


def test_presses_once_when_the_sim_in_a_window_takes_the_focus():
    s, w = rig()
    s["front"] = SIM
    w.step(); w.step(); w.step()
    assert s["presses"] == 1


def test_full_screen_is_left_alone():
    s, w = rig(windowed=False)
    s["front"] = SIM
    w.step()
    assert s["presses"] == 0


def test_a_window_asked_for_stays_until_the_focus_comes_back():
    s, w = rig(windowed=False)
    s["front"] = SIM
    w.step()
    s["windowed"] = True   # Alt+Enter do piloto, com o sim em foco
    w.step(); w.step()
    assert s["presses"] == 0
    s["front"] = OTHER
    w.step()
    s["front"] = SIM
    w.step()
    assert s["presses"] == 1


def test_already_in_front_when_the_app_opens():
    s, w = rig(start=SIM)
    w.step()
    assert s["presses"] == 0


def test_alt_tabbing_past_it_does_nothing():
    s, w = rig()
    s["front"] = SIM
    w.wait = lambda _: s.update(front=OTHER)
    w.step()
    assert s["presses"] == 0


def test_the_keys_go_one_at_a_time():
    """Tudo de uma vez o iRacing nao ve; com intervalo entre as teclas, sim."""
    log = []
    press_alt_enter(lambda k: log.append((k.vk, bool(k.flags & KEYUP))), lambda s: log.append(s))
    assert log == [(0x12, False), HOLD, (0x0D, False), HOLD, (0x0D, True), HOLD, (0x12, True), HOLD]
