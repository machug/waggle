from fastapi import APIRouter


def create_router(verify_key):
    router = APIRouter(tags=["readings"])
    return router
