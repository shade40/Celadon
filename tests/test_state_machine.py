from celadon import StateMachine


def get_state_machine():
    return StateMachine(
        states=(
            "idle",
            "hover",
            "selected",
            "active",
        ),
        transitions={
            "/": {
                "SUBSTATE_ENTER_BLUR": "/blur",
            },
            "/blur": {
                "SUBSTATE_EXIT_BLUR": "/",
            },
            "idle": {
                "HOVERED": "hover",
                "SELECTED": "selected",
                "CLICKED": "active",
                "SINK": "sinkhole",
            },
            "hover": {
                "UNHOVERED": "idle",
                "SELECTED": "selected",
                "CLICKED": "active",
            },
            "selected": {
                "UNSELECTED": "idle",
                "CLICKED": "active",
            },
            "active": {
                "RELEASED": "idle",
            },
            "sinkhole": {},
        },
    )


def test_state_machine_action_changes_state():
    state = get_state_machine()

    assert state() == "idle"

    state.apply_action("HOVERED")
    assert state() == "hover"

    state.apply_action("UNHOVERED")
    assert state() == "idle"

    assert not state.apply_action("NOT_AN_ACTION")

    state.apply_action("SINK")
    assert state() == "sinkhole"
    assert not state.apply_action("CLICKED")


def test_state_machine_contains():
    state = get_state_machine()

    assert "idle" in state
    assert "not in state" not in state


def test_state_machine_getitem():
    state = get_state_machine()

    assert state[0] == "idle"
    assert state[2] == "selected"


def test_state_machine_copy():
    og = get_state_machine()

    # Add transitions, keep states
    state = og.copy(
        add_transitions={
            "/": {
                "CLICKED": "/checked",
            },
            "/checked": {
                "CLICKED": "/",
            },
        },
    )
    assert state.states == state.states
    assert state._transitions == {
        **og._transitions,
        **{
            "/": {
                "CLICKED": "/checked",
                "SUBSTATE_ENTER_BLUR": "/blur",
            },
            "/checked": {
                "CLICKED": "/",
            },
            "/blur": {
                "SUBSTATE_EXIT_BLUR": "/",
            },
        },
    }

    # Overwrite transitions, keep states
    state = og.copy(
        transitions={
            "/": {
                "CLICKED": "/checked",
            },
            "/checked": {
                "CLICKED": "/",
            },
        },
    )
    assert state.states == state.states
    assert state._transitions == {
        "/": {
            "CLICKED": "/checked",
        },
        "/checked": {
            "CLICKED": "/",
        },
    }

    # Keep transitions, add states
    state = og.copy(
        add_states=("test",),
    )
    assert state.states == tuple((*og.states, "test"))
    assert state._transitions == og._transitions

    # Keep transitions, overwrite states
    state = og.copy(
        states=("test",),
    )
    assert state.states == ("test",)
    assert state._transitions == og._transitions


def test_state_machine_substates():
    state = get_state_machine()

    state.apply_action("SUBSTATE_ENTER_BLUR")
    assert state() == "idle/blur"

    state.apply_action("HOVERED")
    assert state() == "hover/blur"

    state.apply_action("CLICKED")
    assert state() == "active/blur"

    state.apply_action("SUBSTATE_EXIT_BLUR")
    assert state() == "active"

    assert not state.apply_action("SUBSTATE_THIS_WONT_WORK")


def test_state_machine_eq():
    state = get_state_machine()

    assert state().startswith("idle")

    state.apply_action("SUBSTATE_ENTER_BLUR")
    assert state().endswith("/blur")
