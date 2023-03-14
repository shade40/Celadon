from __future__ import annotations

from copy import deepcopy

from gunmetal import Event

__all__ = [
    "StateMachine",
]


class StateMachine:
    on_change: Event
    """Called when the state changes.

    Args:
        state: The new (changed-to) state.
    """

    def __init__(self, states: str, *, transitions: dict[str, dict[str, str]]) -> None:
        self.on_change = Event("State Changed")

        self._states = states
        self._transitions = transitions

        self._state = states[0]
        self._substate = ">"

    def __call__(self) -> str:
        """Returns the current state, including substate."""

        return self._state + (self._substate if self._substate != ">" else "")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} state: {self()!r}>"

    def __contains__(self, item: object) -> bool:
        return item in self._states

    def __getitem__(self, index: int) -> str:
        return self._states[index]

    def copy(
        self,
        states: tuple[str, ...] | None = None,
        add_states: tuple[str, ...] | None = None,
        transitions: dict[str, dict[str, str]] | None = None,
        add_transitions: dict[str, dict[str, str]] | None = None,
    ) -> StateMachine:
        """Creates a copy of the state machine and modifies it according to the args.

        Args:
            states: Overwrites the original machine's states.
            add_states: Adds to the original machine's states.
            transitions: Overwrites the original machine's transitions.
            add_transitions: Adds to the original machine's transitions.
        """

        if states is not None:
            new_states = states

        elif add_states is not None:
            new_states = tuple((*self._states, *add_states))

        else:
            new_states = self._states

        if transitions is not None:
            new_transitions = transitions

        elif add_transitions is not None:
            new_transitions = self._transitions | add_transitions

        else:
            new_transitions = deepcopy(self._transitions)

        return StateMachine(new_states, transitions=new_transitions)

    def apply_action(self, action: str) -> bool:
        """Applies some action to the state manager.

        Actions are strings that are used for updating state.

        Returns:
            Whether the given action resulted in a state change.

        Args:
            action: An action name.
        """

        if action.startswith("SUBSTATE_"):
            transitions = self._transitions[self._substate]

            substate = transitions.get(action)

            if substate is None:
                return False

            self._substate = substate
            return True

        transitions = self._transitions.get(self._state)

        state = transitions.get(action)

        # No defined transition from the current state by the action
        if state is None:
            return False

        self._state = state

        self.on_change(state)
        return True
