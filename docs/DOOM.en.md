# DOOM: the model decides, the controller executes

[English](DOOM.en.md) · [Русский](DOOM.md) — this file is the English version.

Current launch commands and the contract live in [README.md](../README.en.md).

The `Executor` must not add combat priority, item utility,
weapon preference, independent door opening or independent
movement-to-exit choices. You may change how the model's chosen command is executed:
aim precision, traversable-path search, stuck detection and feedback.

For new behavior, the negative case is checked first: a `wait`
or `exit` command with a visible monster must not allow ATTACK; `exit` in front of a door must not
allow USE on that door; a missing response must not allow movement.
`tests/test_authority.py` and `tools/check_authority.py` guard this boundary.

The same client and motor-executor code is mandatory for comparing models.
Exact questions, answers, sources and hashes are stored with every run.
The fine-tuned Laya is labelled separately; a successful old heuristic controller
does not prove that the original Laya can finish the level.

The door sensor cross-checks a sector against manual door specials in the WAD. Zero sector
height alone is not enough: in MAP01 sector 208 is a wall. It must not be
offered to the model as a door. Approaching the chosen enemy follows a route,
not a straight walk into a wall. While the weapon is switching, the executor does not fire
the previous weapon.
