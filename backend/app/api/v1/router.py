from fastapi import APIRouter

from app.modules.academic.router import (
    courses_router,
    departments_router,
    faculties_router,
    programs_router,
)
from app.modules.admin.router import admin_router, dashboard_router
from app.modules.advertising.router import ads_router, analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.files.router import router as downloads_router
from app.modules.health.router import router as health_router
from app.modules.institutions.router import router as institutions_router
from app.modules.notifications.router import router as notifications_router
from app.modules.payments.router import router as payments_router
from app.modules.printing.router import operator_router, print_router, shops_router
from app.modules.resources.router import (
    bookmarks_router,
    categories_router,
    resources_router,
    search_router,
)
from app.modules.users.router import me_router, users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(me_router)
api_router.include_router(users_router)
api_router.include_router(institutions_router)
for _router in (faculties_router, departments_router, programs_router, courses_router):
    api_router.include_router(_router)
api_router.include_router(categories_router)
api_router.include_router(resources_router)
api_router.include_router(search_router)
api_router.include_router(bookmarks_router)
api_router.include_router(downloads_router)
for _router in (shops_router, print_router, operator_router, payments_router):
    api_router.include_router(_router)
# Phase 10: dashboard
api_router.include_router(dashboard_router)
# Phase 11: notifications, admin
api_router.include_router(notifications_router)
api_router.include_router(admin_router)
# Phase 12: advertising, analytics
api_router.include_router(ads_router)
api_router.include_router(analytics_router)
