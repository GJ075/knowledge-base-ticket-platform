from fastapi import APIRouter

from app.api.v1 import (
    auth,
    chat,
    conversations,
    document_changes,
    documents,
    tickets,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(documents.router)
api_router.include_router(document_changes.router)
api_router.include_router(chat.router)
api_router.include_router(conversations.router)
api_router.include_router(tickets.router)
