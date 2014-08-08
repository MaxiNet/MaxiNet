import sys

# Make Mininets classes import on OS X
if sys.platform == "darwin":
    class DarwinMiniNetHack:
        pass

    import select
    select.poll = DarwinMiniNetHack
    select.POLLIN =1
    select.POLLHUP = 16
