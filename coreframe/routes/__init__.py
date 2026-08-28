from coreframe.routes.api import register_api_routes
from coreframe.routes.install import register_install_routes
from coreframe.routes.marketplace import register_marketplace_routes
from coreframe.routes.scenes import register_scene_routes
from coreframe.routes.widgets import register_widget_routes, load_widget_state, save_widget_state
from coreframe.routes.static import register_static_routes

__all__ = [
    'register_api_routes', 'register_install_routes', 'register_marketplace_routes',
    'register_scene_routes', 'register_widget_routes', 'register_static_routes',
    'load_widget_state', 'save_widget_state',
]
