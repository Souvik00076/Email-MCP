
from typing import Annotated

from fastapi import Depends

from main import require_auth


AuthDep = Annotated[str, Depends(require_auth)]
