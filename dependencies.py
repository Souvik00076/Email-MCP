
from typing import Annotated

from fastapi import Depends

from middlewares.require_auth import require_auth
from middlewares.user_info import UserInfo


AuthDep = Annotated[UserInfo, Depends(require_auth)]
