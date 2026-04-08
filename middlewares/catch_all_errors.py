

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
import logging

logger=logging.getLogger(__name__)

class CatchAllErrorsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next:RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as e:
            #handle the error here
            logger.error(f"Unhandled exception : {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "success":False,
                    "error":"Internal Server error",
                    "detail":""
                }
            )

