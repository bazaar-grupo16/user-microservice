from fastapi import HTTPException, status
import httpx

from src.core.config import get_settings
from src.core.observability import build_observability_headers

async def block_seller_products(seller_id: str, admin_id: str) -> dict:
    settings = get_settings()
    catalog_url = f"{settings.CATALOG_SERVICE_URL.rstrip('/')}/internal/sellers/{seller_id}/block"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                catalog_url,
                json={"admin_id": admin_id},
                headers=build_observability_headers(),
                timeout=5.0,
            )
            response.raise_for_status()
            return response.json() if response.text else {}
            
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"El usuario fue suspendido, pero falló la inhabilitación de sus productos en el catálogo: {str(e)}"
        )

async def unblock_seller_products(seller_id: str, admin_id: str) -> dict:
    settings = get_settings()
    catalog_url = f"{settings.CATALOG_SERVICE_URL.rstrip('/')}/internal/sellers/{seller_id}/unblock"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                catalog_url,
                json={"admin_id": admin_id},
                headers=build_observability_headers(),
                timeout=5.0,
            )
            response.raise_for_status()
            return response.json() if response.text else {}
            
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"El usuario fue restaurado, pero falló la rehabilitación de sus productos en el catálogo: {str(e)}"
        )