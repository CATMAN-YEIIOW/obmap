from app.routers.buoy import router as buoy_router
from app.routers.data import router as data_router
from app.routers.alert import router as alert_router
from app.routers.statistics import router as statistics_router

__all__ = ["buoy_router", "data_router", "alert_router", "statistics_router"]