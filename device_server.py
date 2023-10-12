from collections import namedtuple

import asyncio
from typing import Any, Coroutine

import reactivex as rx

from reactivex.abc import (
    ObserverBase,
    SchedulerBase,
    DisposableBase,
    # ObservableBase,
)

import reactivex.operators as ops

from reactivex import (
    # Observer,
    Observable,
)
from reactivex.disposable          import Disposable
# from reactivex.scheduler.scheduler import Scheduler
from reactivex.subject             import Subject
from reactivex.scheduler.eventloop import AsyncIOScheduler


# # Abbreviations:
# - `dev`  device       interface to baryon or a machine or belex-libs
# - `svr`  server       responds to requests from a telnet client.
# - `obr`  observer     exposes `on_next`, `on_completed`, `on_error`
# - `obl`  observable   exposes `subscribe`
# - `sbj`  subject      both an observer and observable
# - `obn`  observation  notification, event, data packet, item


# Echo a command received from the client, often `telnet`.
EchoItem = namedtuple(
    typename='EchoItem',
    field_names=['future', 'data'])


def tcp_device_server() -> None:
    """Fields requests from clients wanting to use the device.
    Called from entry point, often pytest."""

    def tcp_dev_svr_obl(
            sbj     : Subject,
            aioloop : Any,
            ) -> Observable[EchoItem]:
        """Make an observable from a Subject and an asyncio loop.

        `sbj` is a `Subject`, both an observer and an observable. As an
        observer, it exposes `on_next`, `on_completed`, `on_error`. As an
        observable, it exposes `subscribe(some_other_observer)`.

        This routine, itself, becomes an observable via `rx.create`, which this
        routine calls on the `on_subscribe` function below, returning the
        result.

                        +-----------------+
        sbj:Subject --> |                 |
        aioloop:Any --> | tcp_dev_svr_obl | --> obl: Observable[Item]
                        |                 |
                        +-----------------+
        """
        def on_subscribe(obr : ObserverBase[EchoItem],
                         _   : SchedulerBase) -> DisposableBase:
            """Subscribe some observer 'obr' to this observable on this
            Scheduler. This observer is a wrapped version of the observer
            interface of my_sbj, thought that fact is not readily or lexically
            lexically evident.
            """

            async def asyncio_client_connected_callback(
                    reader: asyncio.StreamReader,
                    writer: asyncio.StreamWriter):
                """Passed to asyncio.start_server, which passes here a
                StreamReader and a StreamWriter. See
                https://docs.python.org/3.5/library/asyncio-stream.html
                """

                print("Device server is now listening to the model-client.")
                # initial, one-time message to the client:
                writer.write('Any command beginning with "q" '
                'will terminate the session\n'.encode('utf-8'))
                while True:
                    # Text arrives from client here:
                    data = await reader.readline()
                    data = data.decode("utf-8")

                    if not data or data[0] == 'q':
                        break

                    future = asyncio.Future()

                    # Percolate the observation `value`; eventually ends up
                    # in the `on_next` of `my_subj`.
                    obr.on_next(value=EchoItem(
                        future=future,
                        data=data
                    ))

                    await future

                    # When the aioloop is ready, write the `EchoItem` data
                    # back to the client.

                    writer.write(future.result().encode("utf-8"))

                # `break` above jumps here:
                print("Close the model-client socket's writer.")
                writer.close()
                # The reader cannot be closed.
                print("Complete the subject.")
                sbj.on_completed()
                print("Complete the observer.")
                obr.on_completed()

            def sink_on_next(obn: EchoItem):
                """
                Eventually called via the above `obr.on_next`."""
                obn.future.set_result(obn.data)

            def sink_on_completed():
                """Because I can't define a lambda with two statements."""
                print("Stop the Async-IO loop.")
                aioloop.stop()
                print("observer.on_completed()")
                obr.on_completed()
                return

            # `on_subscribe` starts executing here:
            print()
            print("OnSubscribe: start device-side asyncio server"
            "on localhost:8888.")
            server : Coroutine[Any, Any, asyncio.Server] = \
                asyncio.start_server(
                client_connected_cb=asyncio_client_connected_callback,
                host='127.0.0.1',
                port=8888)
            print("Server now running as as asyncio task.")
            aioloop.create_task(server)

            # Subscribe an anonymous observer to `my_sbj`. That observer
            # forwards to the `on_next` above and `on_completed` to
            # `sink_completed` above. See below for the full diagram.
            #
            #       \_/
            #        | obr
            #        |
            #        |   +---------------------+
            #        `---| anonymous observer  |
            #            | - sink_on_next      |
            #            | - sink_on_completed |
            #            +---------------------+

            sbj.subscribe(
                on_next=sink_on_next,
                on_error=obr.on_error,
                on_completed=sink_on_completed
                # on_completed=lambda: aioloop() or obr.on_completed()
                # lambda above doesn't work; reason unknown
              )

            # The following un-hooked Disposable is here just to satisfy the
            # type-checker. Actual resources are shut down and released in
            # `sink_completed` above.

            return Disposable()

        # The `on_subscribe` routine above is invoked later.

        result : Observable[EchoItem] = rx.create(on_subscribe)

        return result

    #              _                   _      _
    #   _ __  __ _(_)_ _    ___ __ _ _(_)_ __| |_
    #  | '  \/ _` | | ' \  (_-</ _| '_| | '_ \  _|
    #  |_|_|_\__,_|_|_||_| /__/\__|_| |_| .__/\__|
    #                                   |_|

    # main script, invoked by pytest, for example

    # Create a `Subject`, which is both an observer and an observable. Its
    # observer starts off with `noop` for its on_next and on_completed methods.
    # Its observable starts off with `subscribe` for its subscribe method,
    # which dispatches to `on_subscribe` above.

    my_sbj = Subject()

    # Make an asyncio loop to feed and an observable, but don't run them yet.
    # `source_obl` takes `my_sbj` as its argument and hooks up its observer
    # interface in

    my_loop = asyncio.new_event_loop()

    source_obl = tcp_dev_svr_obl(
        sbj=my_sbj,
        aioloop=my_loop)
    aio_scheduler = AsyncIOScheduler(loop=my_loop)

    # Make a new, anonymous observable and subscribe `my_sbj` to it.
    # Internally, `subscribe` wraps `my_sbj` with another Observer that retains
    # on_* methods that have not been overridden. The chain ends up looking
    # like this:
    #
    #    ,-- anonymous observable chain ------------------------.
    #               event            event         event
    #   +---------+       +--------+       +-----+       +-------+ obl  \ obr
    #   | asyncio |---,   | source |---,   | map |---,   | delay |-----o |---.
    #   |  loop   |   `-->|  obl   |   `-->|     |   `-->|       |      /    |
    #   +---------+       +--------|       +-----+       +-------+           |
    #                                                                        |
    #            observable interface    +--------+    observer interface    |
    #        o---------------------------| my_sbj |--------------------------'
    #       \_/                          +--------+
    #        | obr
    #        |
    #        |   +---------------------+
    #        `---| anonymous observer  |
    #            | - sink_on_next      |
    #            | - sink_on_completed |
    #            +---------------------+

    source_obl.pipe(
        # _replace is a protected method in named-tuple
        ops.map(lambda obn: obn._replace(data="echo: {}".format(obn.data))),
        ops.delay(0.5)
    ).subscribe(my_sbj, scheduler=aio_scheduler)

    # Start feeding events into the chain.

    my_loop.run_forever()
    print("Async-IO loop ended by 'stop.'")
    my_loop.close()
