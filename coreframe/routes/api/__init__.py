"""HTTP API routes, grouped by domain.

Each group lives in its own module and exposes register_<group>_routes(app,
socketio). register_api_routes() below wires them all in one pass, so a new
group is one import and one call.
"""
from coreframe.routes.api.actions import register_actions_routes
from coreframe.routes.api.debug import register_debug_routes
from coreframe.routes.api.lifecycle import register_lifecycle_routes
from coreframe.routes.api.permissions import register_permissions_routes
from coreframe.routes.api.serving import register_serving_routes
from coreframe.routes.api.status import register_status_routes

GROUPS = (
    register_status_routes,
    register_actions_routes,
    register_permissions_routes,
    register_lifecycle_routes,
    register_serving_routes,
    register_debug_routes,
)


def register_api_routes(app, socketio):
    for register in GROUPS:
        register(app, socketio)