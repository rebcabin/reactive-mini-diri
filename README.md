# reactive-mini-diri

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

