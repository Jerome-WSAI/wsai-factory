from __future__ import annotations

SOFTWARE_NAME = "agents-room-pass1b"
SOFTWARE_PURPOSE = "Agents-Room DEMAND_LOOP pass1 smoke fixture"

def describe_software() -> dict[str, str]:
    return {"name": SOFTWARE_NAME, "purpose": SOFTWARE_PURPOSE}

if __name__ == "__main__":
    print(describe_software())
