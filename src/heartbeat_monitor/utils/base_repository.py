from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from heartbeat_monitor.database import Base


class BaseRepository[ModelType: Base]:
    model: type[ModelType]

    def __init__(self, session: AsyncSession, model: type[ModelType]) -> None:
        self.session = session
        self.model = model

    async def get_by_id(self, obj_id: int) -> ModelType | None:
        return await self.session.get(self.model, obj_id)

    async def list_all(self, skip: int = 0, limit: int = 100) -> Sequence[ModelType]:
        statement = (
            select(self.model)
            .offset(skip)
            .limit(limit)
            .order_by(self.model.id)
        )
        result = await self.session.execute(statement)
        return result.scalars().all()

    def add(self, db_obj: ModelType) -> None:
        self.session.add(db_obj)

    async def delete_by_id(self, obj_id: int) -> int | None:
        statement = (
            delete(self.model)
            .where(self.model.id == obj_id)
            .returning(self.model.id)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()
