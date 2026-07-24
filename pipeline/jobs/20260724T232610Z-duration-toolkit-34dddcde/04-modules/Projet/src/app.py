from __future__ import annotations


SOFTWARE_NAME = "duration-toolkit"
SOFTWARE_PURPOSE = (
    "convert human duration labels to milliseconds for scheduling software"
)


def describe_software() -> dict[str, str]:
    return {"name": SOFTWARE_NAME, "purpose": SOFTWARE_PURPOSE}


def main() -> None:
    info = describe_software()
    print(info["name"])
    print(info["purpose"])


if __name__ == "__main__":
    main()
