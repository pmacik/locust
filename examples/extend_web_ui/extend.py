"""
This is an example of a locustfile that uses Locust's built in event and web
UI extension hooks to track the sum of the content-length header in all
successful HTTP responses and display them in the web UI.
"""

from locust import HttpUser, TaskSet, between, events, task, web

import os
from html import escape
from time import time
from warnings import warn

from flask import Blueprint, jsonify, make_response, render_template

warn(
    "This UI example is deprecated, please downgrade to Locust 2.21.0 or use --legacy-ui flag ; version=2.22.0",
    DeprecationWarning,
    stacklevel=2,
)


class MyTaskSet(TaskSet):
    @task(2)
    def index(l):
        l.client.get("/")

    @task(1)
    def stats(l):
        l.client.get("/stats/requests")


class WebsiteUser(HttpUser):
    host = "http://127.0.0.1:8089"
    wait_time = between(2, 5)
    tasks = [MyTaskSet]


stats = {}
path = os.path.dirname(os.path.abspath(__file__))
extend = Blueprint(
    "extend",
    "extend_web_ui",
    static_folder=f"{path}/static/",
    static_url_path="/extend/static/",
    template_folder=f"{path}/templates/",
)


@events.init.add_listener
def locust_init(environment, **kwargs):
    """
    We need somewhere to store the stats.

    On the master node stats will contain the aggregated sum of all content-lengths,
    while on the worker nodes this will be the sum of the content-lengths since the
    last stats report was sent to the master
    """
    if environment.web_ui:
        # this code is only run on the master node (the web_ui instance doesn't exist on workers)
        @extend.route("/content-length")
        def total_content_length():
            """
            Add a route to the Locust web app where we can see the total content-length for each
            endpoint Locust users are hitting. This is also used by the Content Length tab in the
            extended web UI to show the stats. See `updateContentLengthStats()` and
            `renderContentLengthTable()` in extend.js.
            """
            report = {"stats": []}
            if stats:
                stats_tmp = []

                for name, inner_stats in stats.items():
                    content_length = inner_stats["content-length"]

                    stats_tmp.append(
                        {"name": name, "safe_name": escape(name, quote=False), "content_length": content_length}
                    )

                    # Truncate the total number of stats and errors displayed since a large number of rows will cause the app
                    # to render extremely slowly.
                    report = {"stats": stats_tmp[:500]}
                return jsonify(report)
            return jsonify(stats)

        @extend.route("/extend")
        def extend_web_ui():
            """
            Add route to access the extended web UI with our new tab.
            """
            # ensure the template_args are up to date before using them
            environment.web_ui.update_template_args()
            return render_template("extend.html", **environment.web_ui.template_args)

        @extend.route("/content-length/csv")
        def request_content_length_csv():
            """
            Add route to enable downloading of content-length stats as CSV
            """
            response = make_response(content_length_csv())
            file_name = f"content_length{time()}.csv"
            disposition = f"attachment;filename={file_name}"
            response.headers["Content-type"] = "text/csv"
            response.headers["Content-disposition"] = disposition
            return response

        def content_length_csv():
            """Returns the content-length stats as CSV."""
            rows = [
                ",".join(
                    [
                        '"Name"',
                        '"Total content-length"',
                    ]
                )
            ]

            if stats:
                for url, inner_stats in stats.items():
                    rows.append(f"\"{url}\",{inner_stats['content-length']:.2f}")
            return "\n".join(rows)

        # register our new routes and extended UI with the Locust web UI
        environment.web_ui.app.register_blueprint(extend)


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    """
    Event handler that get triggered on every request
    """
    stats.setdefault(name, {"content-length": 0})
    stats[name]["content-length"] += response_length


@events.reset_stats.add_listener
def on_reset_stats():
    """
    Event handler that get triggered on click of web UI Reset Stats button
    """
    global stats
    stats = {}
