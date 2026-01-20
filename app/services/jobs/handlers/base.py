"""
Base Job Handler Interface
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob


class BaseJobHandler(ABC):
    """
    Abstract base class for all background job handlers.
    Each handler implementation should reside in its own module.
    """
    
    @abstractmethod
    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        """
        Execute the job logic.
        
        Args:
            job: The BackgroundJob model instance.
            db: Scoped database session for the job.
            
        Returns:
            A dictionary containing the job result metadata.
        """
        pass
