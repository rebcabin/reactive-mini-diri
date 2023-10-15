"""By Brian Beckman, October 2023

Adapted and clarified from the sample in the RxPy docs:
https://rxpy.readthedocs.io/en/latest/get_started.html
This preamble does not include information about 'the device.'

This file is MIT-licensed, like RxPy.

1. Create a `Subject` -- both observable and observer -- named `proxy`. Pass it
   to `tcp_dev_svr_obl` for later manipulation. Inside `tcp_dev_svr_obl`,
   `proxy` is named `chain_sink`. Also pass a new AsyncIO loop to
   `tcp_dev_svr_obl`, which saves the loop for later manipulation.

2. `tcp_dev_svr_obl` creates and returns an observable by calling
   `reactivex.create` on an internal procedure, `on_subscribe`. `on_subscribe`
   has the proxy and the AsyncIO loop in scope in the closed-over variables
   `chain_sink` and `aioloop`. `reactivex.create` registers `on_subscribe` as a
   hook to call when any chain of observables containing the created observable
   is subscribed. `on_subscribe` is invoked later in Step 5.

3. Bind the observable returned by `tcp_dev_svr_obl` to the variable
   `source_obl`.

4. Create an anonymous observable chain with a _map_ and a _delay_ (and
   possibly more, as this example grows) piped after `source_obl`. Subscribe an
   observer to the anonymous observable. That observer is the `Observer`
   interface of our self-same `proxy` -- a `Subject`, therefore both an
   observer and an observable. That observer receives events from the end of
   the chain.

5. As a side-effect of subscribing to the chain, `on_subscribe` of
   `tcp_observable` is invoked with an observer argument. Though `proxy` was
   passed to `subscribe`, `on_subscribe` receives an observer that feeds events
   only to the first element of the chain from the AsyncIO reader.

6. Bind the observer argument of `on_subscribe` to the variable named `source`.
   There are now two observers in scope, `chain_sink` -- the original `proxy` --
   and `source`. Post events from the client via the AsyncIO reader to the front
   of the chain by calling `on_next` of `source`. Receive events from the end of
   the chain by subscribing an observer to `chain_sink` whose `on_next` posts
   them to the AsyncIO writer and back to the client.

7. Subscribe an anonymous observer to `chain_sink` -- not to `source`.
   `chain_sink`, as an observable, delivering events from the tail of the
   observable pipeline, aka chain. The anonymous observer forwards chain output
   to the AsyncIO writer, and thus to the client, through its `on_next` method.
   The anonymous observer forwards errors to the system-supplied `on_error` of
   `source`. Finally, the `on_completed` of that observer stop the AsyncIO loop
   and then completes `source` to shut down the observable chain.

"""

from collections import namedtuple

import asyncio
from typing import Any, Coroutine

import reactivex as rx

from reactivex.abc import (
    ObserverBase,
    SchedulerBase,
    DisposableBase,
)

import reactivex.operators as ops

from reactivex import (
    Observable,
)

from reactivex.disposable          import Disposable
from reactivex.subject             import Subject
from reactivex.scheduler.eventloop import AsyncIOScheduler


# # Abbreviations:
# - `dev`  device       interface to baryon or a machine or belex-libs
# - `obl`  Observable   exposes `subscribe`
# - `obn`  observation  notification, event, data packet, item
# - `obr`  Observer     exposes `on_next`, `on_completed`, `on_error`
# - `sbj`  Subject      both an Observer and Observable
# - `svr`  server       responds to requests from a telnet client.


# Echo a command received from the client, often `telnet`. Include a
# future for synchronizing writes to the loop and thus to the client.
EchoItem = namedtuple(
    typename='EchoItem',
    field_names=['future', 'data'])


def tcp_device_server() -> None:
    """Field requests from clients wanting to use the device.

    Called from entry point, often pytest.
    """

    def tcp_dev_svr_obl(
            chain_sink : Subject,
            aioloop    : Any,
            ) -> Observable[EchoItem]:
        """Make an Observable from a Subject, `chain_sink`, and an AsyncIO
        loop, `aioloop`. Save `chain_sink` (close over it) for later
        subscribing by an anonymous observer. Save `aioloop` for later
        initialization and shutdown of the TCP reader/writer loop.

        The observable eventually becomes the head of an anonymous chain of
        observables constructed near the end of the main script below.

        A `Subject` is both an observer and an observable. As an observer, it
        exposes `on_next(event)`, `on_completed()`, `on_error()`. As an
        observable, it exposes `subscribe(some_observer)`.
        """

        def on_subscribe(
                source : ObserverBase[EchoItem],
                _      : SchedulerBase
        ) -> DisposableBase:
            """Receive an observer that can forward data to the head of a chain
            of observables. This observer is not the same as 'the anonymous
            observer,' nor is it `chain_sink`, aka `proxy`, which forwards data
            from the end of the chain to its observers.

            `Source` is an observer created by side-effect when `proxy`
            subscribes to the anonymous chain of observables.

            Ignore the Scheduler argument.
            """

            async def asyncio_client_connected_callback(
                    reader: asyncio.StreamReader,
                    writer: asyncio.StreamWriter):
                """Pass this callback to asyncio.start_server, which
                passes a StreamReader and a StreamWriter back here. See
                https://docs.python.org/3.5/library/asyncio-stream.html

                The reader feeds data from the client TCP connection to the
                `on_next` method of `source`.
                """

                await initialization_messages(writer)

                while True:
                    # Text arrives from client here:

                    data_awaited = await reader.readline()
                    data = data_awaited.decode("utf-8")

                    if not data or data[0] == 'q':
                        break

                    # Invoke some futures later with data to write back to the
                    # client.

                    chain_sink_future = asyncio.Future()
                    source_future = asyncio.Future()

                    # Bypass the processing chain.
                    chain_sink.on_next(
                        value=EchoItem(
                            data = f'received {data} Processing ...\n',
                            future = chain_sink_future,
                        ))

                    # Go through the processing chain.
                    source.on_next(value=EchoItem(
                        future=source_future,
                        data=data.upper()
                        ))

                    # When futures return control here, write the `EchoItem`
                    # data back to the client.

                    await chain_sink_future
                    writer.write(chain_sink_future.result().encode("utf-8"))

                    await source_future
                    writer.write(source_future.result().encode("utf-8"))

                # Any command beginning with `q` jumps here:
                print("Close the aioloop writer.")

                # Close the writer, here, because `writer` will be out of scope
                # when `chain_sink.on_completed` is invoked.
                writer.close()

                # The reader cannot be closed.

                # Let `chain_sink.on_completed` shut down the loop and
                # the `source`.
                print("Complete the proxy Subject, eventually completing `source`.")
                chain_sink.on_completed()

                pass  # end of `asyncio_client_connected_callback`

            # `reader` and `writer are now out of scope`.

            async def initialization_messages(writer):
                # to server console.
                print("Device server is now listening to the client.")
                # to client:
                writer.write('Any command beginning with "q"'
                             'terminates the session.\n'.encode('utf-8'))

            # `on_subscribe` with `source` observer starts executing here:
            print()
            print("OnSubscribe: start device-side asyncio server "
            "on localhost:8888.")
            server : Coroutine[Any, Any, asyncio.Server] = \
                asyncio.start_server(
                client_connected_cb=asyncio_client_connected_callback,
                host='127.0.0.1',
                port=8888)
            print("Server now running as as asyncio task.")
            aioloop.create_task(server)

            # Subscribe an anonymous Observer to `proxy`, aka `chain_sink`.
            # The `on_next` of that observer forwards events to the TCP writer,
            # which is waiting for the future saved in the event data structure
            # -- the "observation."

            chain_sink.subscribe(
                # Event data are sent to the writer of aioloop.
                on_next=lambda obn: obn.future.set_result(obn.data),
                # Forward errors to the source observer.
                on_error=source.on_error,
                # This next lambda works because both disjuncts return `None`.
                on_completed=lambda: aioloop.stop() or source.on_completed(),
              )

            # The following un-hooked Disposable is here just to satisfy the
            # type-checker. Actual resources are shut down and released in
            # `sink_completed` above.

            return Disposable()  # end of `on_subscribe`

        # `tcp_dev_svr_obl` starts executing here.

        # The `on_subscribe` routine above is invoked later by side-effect
        # when an observers subscribes to the observable chain.

        result : Observable[EchoItem] = rx.create(on_subscribe)

        return result # end of `tcp_dev_svr_obl`.

    #              _                   _      _
    #   _ __  __ _(_)_ _    ___ __ _ _(_)_ __| |_
    #  | '  \/ _` | | ' \  (_-</ _| '_| | '_ \  _|
    #  |_|_|_\__,_|_|_||_| /__/\__|_| |_| .__/\__|
    #                                   |_|

    # main script, invoked by pytest, for example

    # Make arguments to pass to `tcp_dev_svr_obl`.

    # Create a `Subject`, `proxy`, to forward data from the tail of a chain of
    # observables to its subscribers. `Proxy` is both an observable and an
    # observer. Its observable starts off with the system-default `subscribe`
    # method. That method automatically calls our hook, `on_subscribe`, above,
    # with a system-supplied observer whose `on_next` forwards data to the
    # source observable created below.

    proxy = Subject()

    # Make an asyncio loop to produce data from the client and to consumer data
    # to send back to the client. Don't run the loop yet.

    my_loop = asyncio.new_event_loop()

    source_obl = tcp_dev_svr_obl(
        chain_sink=proxy,
        aioloop=my_loop)

    # Chain `source_obl` to a few queries (observable-to-observable transforms,
    # e.g., `map` and `delay`). . Subscribe `proxy` to the tail of the chain on
    # an `AsyncIOScheduler`. The chain ends up looking like this:
    #
    #     ,------ anonymous observable chain -------------------.
    #    /                                                       \
    #
    #                                event         event
    #    /-------\       +---------+       +-----+       +-------+
    #   | reader  |>     | source  |---,   | map |---,   | delay |
    #   +-asyncio-+ \    |   obl   |   `-->| obl |   `-->|  obl  |
    #   | writer  |  \   +---------|       +-----+       +-------+
    #    \-------/    \       ^                              |
    #        ^ ^    on_next   |   created via            obl |
    #        |  \       \     |   reactivex.create           |
    #  to the|   \       V    |   of source_obl              |
    #  writer|    \       +--------+ Step 5                  o
    #        |     \      | source |          subscription  \_/
    #        |    loop.   |  obr   |                         |
    #        |     stop   +--------+                     obr |
    #        |        \      ^  ^                     Step 4 |
    #        |         ^     |  |                     +-------------+
    #        |   on_completed|  |on_error             | chain_sink  |
    #        |               |  |                     |  aka proxy  |
    #        |               |  |                     +-------------+
    #        |         +----------------------+              |
    #        \         |                      | obr        _ | obl
    #         `--------|  anonymous observer  |-----------|  o
    #          on_next |                      |            -
    #                  +----------------------+        subscription

    aio_scheduler = AsyncIOScheduler(loop=my_loop)
    # Anonymous Observable
    source_obl.pipe(
        # _replace is a protected method in named-tuple
        ops.map(lambda obn: obn._replace(data=f"echo: {obn.data}")),
        ops.delay(0.5)
    ).subscribe(proxy, scheduler=aio_scheduler)

    # Start feeding events into the chain.

    my_loop.run_forever()
    print("Async-IO loop ended by 'stop.'")
    my_loop.close()
