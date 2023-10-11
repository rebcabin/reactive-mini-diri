from collections import namedtuple
import asyncio
import reactivex

import reactivex.operators as ops

from reactivex.subject import Subject
from reactivex.scheduler.eventloop import AsyncIOScheduler


# Abbreviations: "obr"   observer
#                "obl"   observable
#                "sbj"   both an observer and observable
#                "obn"   observation, event, data packet, item


def tcp_example():

    EchoItem = namedtuple(
        'EchoItem', ['future', 'data'])

    def my_tcp_server_obl(sbj, aioloop):
        def on_subscribe(obr, _unused_scheduler):
            async def client_connected_callback(reader, writer):
                """Passed to asyncio.start_server."""
                print("New client connected.")
                while True:
                    data = await reader.readline()
                    data = data.decode("utf-8")
                    if not data or data[0] == 'q':
                        break

                    future = asyncio.Future()
                    obr.on_next(value=EchoItem(
                        future=future,
                        data=data
                    ))
                    await future
                    writer.write(future.result().encode("utf-8"))
                print("Close the client socket's writer.")
                writer.close()
                print("Complete the subject.")
                sbj.on_completed()
                print("Complete the observer.")
                obr.on_completed()

            def on_next(nm_tup):
                nm_tup.future.set_result(nm_tup.data)

            print()
            print("Start server.")
            server = asyncio.start_server(
                client_connected_cb=client_connected_callback,
                host='127.0.0.1',
                port=8888)
            aioloop.create_task(server)

            def sink_completed():
                """Because I can't define a lambda with two statements."""
                print("Stop the asyncio loop.")
                aioloop.stop()
                obr.on_completed()
                return

            sbj.subscribe(
                on_next=on_next,
                on_error=obr.on_error,
                on_completed=sink_completed  # lambda doesn't work
            )

        return reactivex.create(on_subscribe)

    my_loop = asyncio.new_event_loop()
    my_sbj = Subject()
    source_obl = my_tcp_server_obl(
        sbj=my_sbj,
        aioloop=my_loop)
    aio_scheduler = AsyncIOScheduler(loop=my_loop)

    source_obl.pipe(
        # _replace is a method in named-tuple
        ops.map(lambda i: i._replace(data="echo: {}".format(i.data))),
        ops.delay(1.5)
    ).subscribe(my_sbj, scheduler=aio_scheduler)

    my_loop.run_forever()
    print("Loop ended by 'stop.'")
    my_loop.close()
