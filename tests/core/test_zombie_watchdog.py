from custos.core.engine_protocol import ConnectivityState
from custos.core.zombie_watchdog import ZombieWatchdog


def test_watchdog_state_and_cleanup_are_instance_keyed() -> None:
    now = [0.0]
    watchdog = ZombieWatchdog(grace_secs=10, clock=lambda: now[0])
    disconnected = ConnectivityState(
        data_connected=False,
        exec_connected=False,
        checked_at_epoch_s=0.0,
    )
    first = watchdog.observe("instance-a", disconnected)
    assert not first.is_zombie
    now[0] = 11.0
    assert watchdog.observe("instance-a", disconnected).is_zombie
    assert not watchdog.observe("instance-b", disconnected).is_zombie
    watchdog.forget("instance-a")
    assert not watchdog.observe("instance-a", disconnected).is_zombie
