from fastapi import APIRouter
from app.api.v1.endpoints import auth, businesses, sales, inventory, iot

# Este router agrupa todos los endpoints bajo /api/v1
api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(businesses.router)
api_router.include_router(sales.products_router)
api_router.include_router(sales.sales_router)
api_router.include_router(inventory.router)
api_router.include_router(iot.router)
