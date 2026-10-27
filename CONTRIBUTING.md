# Contributing

Thanks for your interest in this project. Issues and pull requests are welcome, in English or in French.

## Commit messages

New commits are written in **English** (older commits stay in French; history is never rewritten).

- Imperative mood, capitalised verb, no final full stop: `Add …`, `Fix …`, `Update …`, `Remove …`, `Translate …`, `Document …`.
- Subject line of 72 characters or less; add a body after a blank line if the "why" is not obvious.
- One logical change per commit.

Examples:

```
Add stall detection to the firmware
Fix QRZ session renewal after expiry
Document the 6-point calibration
```

## Before submitting a change

- Do not rename files, folders or variables: external links depend on them.
- Firmware: check that it still compiles for **Arduino Nano, ATmega328P (Old Bootloader)**.
- Python: `python3 -m py_compile scripts/*.py tools/*.py`.
- Never commit `scripts/rotor_config.ini` or any credentials.
- Any change touching relay control must be tested in small steps, eyes on the control box needle (see the **Safety** section of the README).

73 de ON5AM
