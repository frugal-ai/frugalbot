import platform


def get_platform_info() -> str:
    system = platform.system()
    machine = platform.machine().lower()

    arch = "x64" if any(x in machine for x in ["amd64", "x86_64", "64"]) else "x86"

    if system == "Windows":
        release = platform.release()
        return f"Windows {release} {arch}"

    if system == "Linux":
        try:
            info = platform.freedesktop_os_release()
            name = info.get("PRETTY_NAME", "Linux")
            return f"{name} {arch}"
        except AttributeError, OSError:
            return f"Linux {platform.release()} {arch}"

    if system == "Darwin":
        version = platform.mac_ver()[0]
        return f"macOS {version} {arch}"

    return f"{system} {platform.release()} {arch}"
