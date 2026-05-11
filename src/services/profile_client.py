from fastapi import HTTPException, status
import httpx

from src.core.config import get_settings


def create_profile(user_id: str, name: str) -> dict:
    """
    Envía una petición al microservicio de Perfiles para crear el perfil
    asociado a un nuevo usuario.
    """
    settings = get_settings()
    profile_url = settings.PROFILE_SERVICE_URL  
    
    profile_payload = {
        "user_id": user_id,
        "name": name
    }

    try:
        with httpx.Client() as client:
            response = client.post(profile_url, json=profile_payload, timeout=5.0)
            response.raise_for_status() 
            
            # Si la API de perfil devuelve JSON, lo retornamos (opcional pero útil)
            return response.json() if response.text else {}
            
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Usuario creado en Auth, pero falló la creación del perfil: {str(e)}"
        )