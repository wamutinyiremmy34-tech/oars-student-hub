"""Single import point that makes every model visible to Alembic autogenerate.

Add `import app.modules.<name>.models  # noqa: F401` lines here when a module gains tables.
"""

import app.modules.academic.models  # noqa: F401
import app.modules.advertising.models  # noqa: F401
import app.modules.audit.models  # noqa: F401
import app.modules.auth.models  # noqa: F401
import app.modules.files.models  # noqa: F401
import app.modules.institutions.models  # noqa: F401
import app.modules.notifications.models  # noqa: F401
import app.modules.payments.models  # noqa: F401
import app.modules.printing.models  # noqa: F401
import app.modules.rbac.models  # noqa: F401
import app.modules.resources.models  # noqa: F401
import app.modules.users.models  # noqa: F401
from app.db.base import Base

__all__ = ["Base"]
