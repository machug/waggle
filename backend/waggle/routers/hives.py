from fastapi import APIRouter


def create_router(verify_key):
    router = APIRouter(tags=["hives"], dependencies=[verify_key])

    @router.get("/hives")
    async def list_hives():
        return []  # stub — implemented in a later task

    return router
