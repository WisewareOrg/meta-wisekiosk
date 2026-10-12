"""TST007: the layout-floor check, judged by `verdicts.layout`."""

from verdicts.layout import verdict

_LAUNCHER_PATH = "/usr/bin/kiosk-launch"


def _configured_mode(driver):
    """The mode `kiosk-launch`'s own `--mode` argument configures.

    Args:
        driver: A labgrid SSHDriver.

    Returns:
        str: The configured "<w>x<h>" mode.

    Raises:
        RuntimeError: the launcher's configured mode could not be read.
    """
    stdout, stderr, rc = driver.run(
        f"grep -o -- '--mode [0-9]*x[0-9]*' {_LAUNCHER_PATH} | head -n 1 | cut -d' ' -f2"
    )
    joined = "\n".join(stdout).strip()
    if rc != 0 or not joined:
        raise RuntimeError(f"could not read the configured mode from {_LAUNCHER_PATH}: {stderr}")
    return joined


def test_layout_floor(target):
    """TST007: the display's current mode clears the 720p floor and matches the launcher's own.

    Args:
        target: labgrid Target fixture, bound to the `main` target `bench.yaml` names.
    """
    driver = target.get_driver("SSHDriver")
    stdout, stderr, rc = driver.run("DISPLAY=:0 xrandr")
    if rc != 0:
        raise RuntimeError(f"could not read xrandr: {stderr}")
    configured_mode = _configured_mode(driver)
    outcome, reason = verdict("\n".join(stdout), configured_mode)
    if outcome == "error":
        raise RuntimeError(reason)
    assert outcome == "ok", reason
