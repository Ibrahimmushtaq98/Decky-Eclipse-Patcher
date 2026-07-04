from eclipse_patcher import launch_options as lo


def test_single_proxy():
    assert lo.build_managed_launch_options(["dxgi.dll"]) == "WINEDLLOVERRIDES=dxgi=n,b %command%"


def test_multiple_proxies():
    assert (
        lo.build_managed_launch_options(["dxgi.dll", "version.dll"])
        == "WINEDLLOVERRIDES=dxgi,version=n,b %command%"
    )


def test_no_proxies():
    assert lo.build_managed_launch_options([]) == ""


def test_is_managed():
    assert lo.is_managed_launch_options("WINEDLLOVERRIDES=dxgi=n,b %command%")
    assert lo.is_managed_launch_options("  WINEDLLOVERRIDES=dxgi,version=n,b   %command%  ")
    assert not lo.is_managed_launch_options("")
    assert not lo.is_managed_launch_options("PROTON_LOG=1 %command%")
    assert not lo.is_managed_launch_options("gamemoderun %command%")
