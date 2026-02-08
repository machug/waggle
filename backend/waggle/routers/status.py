from fastapi import APIRouter


def create_router():
    router = APIRouter(tags=["status"])
    return router
