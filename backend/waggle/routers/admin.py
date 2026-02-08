"""Admin router for camera node registration."""

import bcrypt
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import CameraNode, Hive
from waggle.schemas import CameraNodeCreate, CameraNodeOut
from waggle.utils.timestamps import utc_now


def create_router(verify_admin) -> APIRouter:
    router = APIRouter(dependencies=[verify_admin])

    @router.post("/admin/camera-nodes", status_code=201, response_model=CameraNodeOut)
    async def register_camera_node(body: CameraNodeCreate, request: Request):
        async with AsyncSession(request.app.state.engine) as session:
            # Validate hive exists
            hive = await session.get(Hive, body.hive_id)
            if not hive:
                raise HTTPException(status_code=404, detail="Hive not found")

            # Check for duplicate device
            existing = await session.get(CameraNode, body.device_id)
            if existing:
                raise HTTPException(status_code=409, detail="Device already registered")

            # Hash the API key with bcrypt (cost 12)
            api_key_hash = bcrypt.hashpw(
                body.api_key.encode("utf-8"), bcrypt.gensalt(rounds=12)
            ).decode("utf-8")

            now = utc_now()
            node = CameraNode(
                device_id=body.device_id,
                hive_id=body.hive_id,
                api_key_hash=api_key_hash,
                created_at=now,
            )
            session.add(node)
            await session.commit()
            await session.refresh(node)

            return CameraNodeOut(
                device_id=node.device_id,
                hive_id=node.hive_id,
                created_at=node.created_at,
                last_seen_at=node.last_seen_at,
            )

    return router
