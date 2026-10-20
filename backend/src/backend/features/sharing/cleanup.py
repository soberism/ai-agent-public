from sqlalchemy import delete

from backend.db.sharing_models import ItemSharing, ItemSharingMember
from backend.features.sharing.access import RESOURCE_MODELS


def delete_resource(session, row):
    kind = next(
        (kind for kind, model in RESOURCE_MODELS.items() if isinstance(row, model)),
        None,
    )
    if kind:
        session.execute(
            delete(ItemSharingMember).where(
                ItemSharingMember.kind == kind, ItemSharingMember.resource_id == row.id
            )
        )
        session.execute(
            delete(ItemSharing).where(
                ItemSharing.kind == kind, ItemSharing.resource_id == row.id
            )
        )
    session.delete(row)
